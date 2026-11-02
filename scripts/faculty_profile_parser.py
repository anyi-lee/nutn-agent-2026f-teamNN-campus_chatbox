"""Read explicitly labelled public faculty tables, never footer email guesses."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urljoin, urlparse

EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
NAME = re.compile(r'[\u4e00-\u9fff]{2,4}')


class ProfileHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.stack, self.links = [], [], []
        self.anchor = None
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style'):
            self.ignored += 1
        if self.ignored:
            return
        if tag == 'table':
            self.stack.append({'rows': [], 'row': [], 'cell': None})
        elif tag == 'tr' and self.stack:
            self.stack[-1]['row'] = []
        elif tag in ('th', 'td') and self.stack:
            self.stack[-1]['cell'] = []
        if tag == 'a':
            self.anchor = {'href': attrs.get('href', ''), 'names': []}
            if self.stack and self.stack[-1]['cell'] is not None and attrs.get('href', '').strip().lower().startswith('mailto:'):
                self.stack[-1]['cell'].append(unquote(attrs['href']))
        elif tag == 'img' and self.anchor and NAME.fullmatch(attrs.get('alt', '').strip()):
            self.anchor['names'].append(attrs['alt'].strip())

    def handle_data(self, data):
        if self.ignored:
            return
        if self.stack and self.stack[-1]['cell'] is not None:
            self.stack[-1]['cell'].append(data)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.ignored = max(0, self.ignored - 1)
            return
        if self.ignored:
            return
        if tag == 'a' and self.anchor:
            if len(set(self.anchor['names'])) == 1:
                self.links.append((self.anchor['href'], self.anchor['names'][0]))
            self.anchor = None
        if not self.stack:
            return
        current = self.stack[-1]
        if tag in ('th', 'td') and current['cell'] is not None:
            current['row'].append(re.sub(r'\s+', ' ', ' '.join(current['cell'])).strip())
            current['cell'] = None
        elif tag == 'tr':
            current['rows'].append(current['row'])
            current['row'] = []
        elif tag == 'table':
            self.tables.append(self.stack.pop()['rows'])


def parse_profile_tables(markup, expected_name=None, allow_missing_title=False):
    parser = ProfileHTML()
    parser.feed(markup)
    result = []
    for table in parser.tables:
        fields = {}
        conflict = False
        for row in table:
            if len(row) != 2:
                continue
            label = row[0].strip(' ：:').lower()
            if label in fields and fields[label] != row[1]:
                conflict = True
            fields[label] = row[1]
        name, title = fields.get('姓名', ''), fields.get('職稱', '')
        emails = set(EMAIL.findall(' '.join(fields.get(label, '') for label in ('電子信箱', 'email', 'e-mail', '信箱'))))
        if conflict or not NAME.fullmatch(name) or (not re.search('教授|講師|研究員', title) and not (allow_missing_title and not title)) or len(emails) != 1:
            continue
        if expected_name and name != expected_name:
            continue
        areas = fields.get('專業領域') or fields.get('研究專長') or fields.get('學術專長') or fields.get('專長/研究領域') or fields.get('專長／研究領域', '')
        result.append({'teacher_name': name, 'title': title or '教師（官網未列職稱）', 'public_email': emails.pop(),
                       'research_areas': [area.strip() for area in re.split('[、，,；;]', areas) if area.strip()]})
    return result


def profile_links(markup, directory_url):
    parser = ProfileHTML()
    parser.feed(markup)
    result = []
    host = urlparse(directory_url).hostname
    for href, name in parser.links:
        url = urljoin(directory_url, href).split('#')[0]
        parsed = urlparse(url)
        if (parsed.scheme == 'https' and parsed.hostname == host
                and parse_qs(parsed.query).get('task') == ['pageinfo'] and (url, name) not in result):
            result.append((url, name))
    return result
