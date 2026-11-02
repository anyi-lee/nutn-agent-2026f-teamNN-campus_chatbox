#!/usr/bin/env python3
"""Build a bounded public NUTN directory snapshot. Requires lxml for refresh only.

No login, private directory, arbitrary user URL, or model-generated contact data
is used. Website failures are recorded rather than treated as empty success.
"""
from __future__ import annotations

import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from lxml import html
from faculty_profile_parser import parse_profile_tables, profile_links

ROOT = Path(__file__).resolve().parents[1]
TEACHING = 'https://web.nutn.edu.tw/teaching.html'
ADMIN = 'https://web.nutn.edu.tw/administrative.html'
PHONE_ACADEMIC = 'https://personnel.nutn.edu.tw/mode02.asp?m=20220221163310133&t=list'
PHONE_ADMIN = 'https://personnel.nutn.edu.tw/mode02.asp?m=20220221163409511&t=list'
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
DATE = datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')


def official(url):
    parsed = urlparse(url)
    return parsed.scheme in ('https', 'http') and parsed.hostname and (
        parsed.hostname == 'nutn.edu.tw' or parsed.hostname.endswith('.nutn.edu.tw'))


def fetch(url):
    if not official(url):
        raise ValueError('Non-NUTN source rejected')
    req = Request(url, headers={'User-Agent': 'NUTN-Campus-Agent-Coursework/1.0'})
    with urlopen(req, timeout=12) as response:
        if not official(response.url):
            raise ValueError('Non-NUTN redirect rejected')
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError('Page too large')
    doc = html.fromstring(data)
    for item in doc.xpath('//script|//style|//noscript'):
        item.drop_tree()
    return doc, hashlib.sha256(data).hexdigest()


def txt(node):
    return re.sub(r'\s+', ' ', node.text_content()).strip()


def aliases(name):
    extra = {'國語文學系': ['國文系', '中文系'], '資訊工程學系': ['資工系'],
             '電機工程學系': ['電機系'], '諮商與輔導學系': ['諮輔系'],
             '文化與自然資源學系': ['文資系'], '數位學習科技學系': ['數位系'],
             '視覺藝術與設計學系': ['視設系'], '戲劇創作與應用學系': ['戲劇系'],
             '經營與管理學系': ['經管系'], '行政管理學系': ['行管系'],
             '生態暨環境資源學系': ['生態系'], '綠色能源科技學系': ['綠能系'],
             '生物科技學系': ['生科系'], '特殊教育學系': ['特教系'],
             '幼兒教育學系': ['幼教系'], '應用數學系': ['應數系'],
             '圖資處': ['圖書館', '圖書資訊處'], '學務處': ['學生事務處'],
             '教務處': ['教務單位'], '國際事務處': ['國際處']}
    values = [name, name.replace('學系', '系')]
    return sorted(set(values + extra.get(name, [])))


def crawl_unit(unit):
    result = {**unit, 'aliases': aliases(unit['name']), 'public_email': None,
              'telephone': None, 'extensions': [], 'office_hours': None,
              'retrieved_at': DATE, 'authority': 'official', 'validity': 'active'}
    contacts, sources = [], []
    try:
        home, digest = fetch(unit['url'])
        text = txt(home)
        sources.append({'url': unit['url'], 'sha256': digest, 'retrieved_at': DATE})
        mails = sorted(set(EMAIL.findall(text)))
        mails = [m for m in mails if m.lower() not in ('yuan@mail.nutn.edu.tw', 'ming@mail.nutn.edu.tw')]
        if len(mails) == 1:
            result['public_email'] = mails[0]
        phone = re.search(r'(?:電話|Tel(?:ephone)?)[：:\s]*([()+\d\-\s]{8,25})', text, re.I)
        if phone:
            result['telephone'] = phone[1].strip()
        # Follow a few explicit faculty-directory links, not an unrestricted crawl.
        links = []
        for a in home.xpath('//a[@href]'):
            label = txt(a)
            if not re.fullmatch(r'.{0,8}(?:專任教師|專任師資|師資陣容|師資介紹|教師介紹|本系師資|師資成員).{0,8}', label):
                continue
            target = urljoin(unit['url'], a.get('href')).split('#')[0]
            if official(target) and target not in links and target != unit['url']:
                links.append(target)
        pages = [(unit['url'], home)]
        for target in links[:2]:
            try:
                page, digest = fetch(target)
                pages.append((target, page))
                sources.append({'url': target, 'sha256': digest, 'retrieved_at': DATE})
            except Exception:
                sources.append({'url': target, 'status': 'fetch_failed'})
        profiles = []
        for directory_url, page in pages[1:]:
            for target, expected_name in profile_links(html.tostring(page, encoding='unicode'), directory_url):
                if target not in {url for url, _ in profiles}:
                    profiles.append((target, expected_name))
        expected_profiles = dict(profiles[:20])
        for target, expected_name in profiles[:20]:
            try:
                page, digest = fetch(target)
                pages.append((target, page))
                sources.append({'url': target, 'sha256': digest, 'retrieved_at': DATE})
            except Exception as exc:
                sources.append({'url': target, 'status': 'fetch_failed', 'error_type': type(exc).__name__})
        seen = set()
        for page_url, page in pages:
            for fields in parse_profile_tables(html.tostring(page, encoding='unicode'), expected_profiles.get(page_url)):
                key = (fields['teacher_name'], fields['public_email'])
                if key in seen:
                    continue
                seen.add(key)
                contacts.append({**fields,
                    'chunk_id': 'campus-person-' + hashlib.sha256(''.join(key).encode()).hexdigest()[:14],
                    'source_id': 'nutn-campus-' + hashlib.sha256(page_url.encode()).hexdigest()[:12],
                    'department': unit['name'],
                    'content': f"姓名：{fields['teacher_name']}；職稱：{fields['title']}；電子信箱：{fields['public_email']}；專業領域：{'、'.join(fields['research_areas'])}",
                    'source_url': page_url, 'retrieved_at': DATE, 'index_version': 'campus-index-v1',
                    'authority': 'official', 'validity': 'active', 'recipient_kind': 'faculty'})
            if page_url in expected_profiles:
                # A named directory entry must match its labelled profile table;
                # do not fall back to unrelated names from a CV or footer.
                continue
            for a in page.xpath('//a[starts-with(@href,"mailto:")]'):
                matches = EMAIL.findall(a.get('href', ''))
                if not matches:
                    continue
                email = matches[0]
                block = a
                for _ in range(5):
                    block = block.getparent()
                    if block is None:
                        break
                    context = txt(block)
                    if len(context) > 1100:
                        break
                    if len(set(EMAIL.findall(context))) != 1:
                        continue
                    names = []
                    for el in block.xpath('.//h2|.//h3|.//h4|.//strong|.//b|.//a'):
                        name = re.sub(r'\s*(?:助理教授|副教授|教授|講師)$', '', txt(el))
                        match = re.fullmatch(r'([\u4e00-\u9fff]{2,4})', name)
                        if match and match[1] not in ('電子郵件', '個人網頁', '聯絡方式', '師資陣容', '研究專長', '學術專長'):
                            names.append(match[1])
                    name_match = re.search(r'姓名[：:\s]*([\u4e00-\u9fff]{2,4})', context)
                    if name_match:
                        names.append(name_match[1])
                    names = set(names)
                    if len(names) != 1 or not re.search('教授|講師|研究專長|學術專長', context):
                        continue
                    name = names.pop()
                    if (name, email) in seen:
                        break
                    seen.add((name, email))
                    title = re.search(r'助理教授|副教授|教授|講師', context)
                    contacts.append({'chunk_id': 'campus-person-' + hashlib.sha256((name+email).encode()).hexdigest()[:14],
                        'source_id': 'nutn-campus-' + hashlib.sha256(page_url.encode()).hexdigest()[:12],
                        'teacher_name': name, 'title': title[0] if title else '教師',
                        'department': unit['name'], 'research_areas': [], 'public_email': email,
                        'content': context, 'source_url': page_url, 'retrieved_at': DATE,
                        'index_version': 'campus-index-v1', 'authority': 'official', 'validity': 'active',
                        'recipient_kind': 'faculty'})
                    break
        result['page_status'] = 'fetched'
    except Exception as exc:
        result['page_status'] = 'fetch_failed'
        result['error_type'] = type(exc).__name__
    return result, contacts, sources


def main():
    units, source_records, telephone_rows = {}, [], []
    for url, kind in ((TEACHING, 'academic'), (ADMIN, 'administrative')):
        doc, digest = fetch(url)
        source_records.append({'url': url, 'sha256': digest, 'retrieved_at': DATE})
        # Index content starts after the ::: marker, using the central content text.
        for a in doc.xpath('//a[@href]'):
            name = txt(a)
            target = urljoin(url, a.get('href'))
            if (not official(target) or target.rstrip('/') == 'https://web.nutn.edu.tw'
                    or name in ('行政單位', '教學單位', '學校首頁') or '停招' in name):
                continue
            if kind == 'academic' and not name.endswith(('學系', '學程', '專班', '研究所')):
                continue
            if kind == 'administrative' and (not name.endswith(('處', '室', '中心')) or name == '副校長室'):
                continue
            units[name] = {'name': name, 'url': target, 'category': kind, 'directory_source': url}
    for url in (PHONE_ACADEMIC, PHONE_ADMIN):
        try:
            doc, digest = fetch(url)
            source_records.append({'url': url, 'sha256': digest, 'retrieved_at': DATE})
            for row in doc.xpath('//tr'):
                cells = [txt(c) for c in row.xpath('./td|./th')]
                for offset in range(0, len(cells)-1, 2):
                    name, ext = cells[offset:offset+2]
                    if 2 <= len(name) <= 30 and re.fullmatch(r'[\d、,，~～\-\s]{2,80}', ext):
                        telephone_rows.append({'name': name, 'extensions_text': ext, 'source_url': url})
        except Exception as exc:
            source_records.append({'url': url, 'status': 'fetch_failed', 'error_type': type(exc).__name__})
    results = list(ThreadPoolExecutor(max_workers=4).map(crawl_unit, units.values()))
    records, contacts = [], []
    for unit, people, sources in results:
        rows = [r for r in telephone_rows if r['name'] in unit['aliases']]
        if rows:
            unit['telephone'] = '06-2133111'
            unit['extensions'] = [rows[0]['extensions_text']]
            unit['phone_source_url'] = rows[0]['source_url']
        unit['chunk_id'] = 'campus-unit-' + hashlib.sha256(unit['name'].encode()).hexdigest()[:12]
        records.append(unit)
        contacts.extend(people)
        source_records.extend(sources)
        print(unit['name'], unit['page_status'], 'faculty:', len(people), flush=True)
    # Keep explicit office sections from the official telephone directory too.
    for row in telephone_rows:
        if row['name'] in units or not re.search('處|室|中心|宿舍', row['name']):
            continue
        parent = next((u for u in records if row['name'].startswith(u['name'])), None)
        if not parent:
            continue
        records.append({**parent, 'name': row['name'], 'aliases': aliases(row['name']),
            'chunk_id': 'campus-unit-' + hashlib.sha256(row['name'].encode()).hexdigest()[:12],
            'telephone': '06-2133111', 'extensions': [row['extensions_text']],
            'public_email': None, 'phone_source_url': row['source_url']})
    output = {'schema_version': '1.0', 'retrieved_at': DATE,
        'scope': 'NUTN public academic and administrative directory; faculty contact coverage is partial',
        'units': records, 'contacts': contacts, 'sources': source_records,
        'limitations': ['Faculty entries are included only when name/email association is unambiguous on a public page.',
                         'Office hours and unpublished emails are not inferred. Login-only email directory is excluded.']}
    if len(records) < 25:
        raise RuntimeError('Directory coverage unexpectedly small; previous snapshot retained')
    path = ROOT / 'data/campus_catalog.json'
    if path.exists():
        from publish_faculty_audit import retain_reviewed_faculty
        output = retain_reviewed_faculty(json.loads(path.read_text(encoding='utf-8')), output)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    from build_email_directory import build_directory
    (ROOT / 'ui/email_directory.json').write_text(json.dumps(build_directory(), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Saved', len(records), 'units and', len(output['contacts']), 'faculty records (deep-audited records retain original retrieval dates)')


if __name__ == '__main__':
    main()
