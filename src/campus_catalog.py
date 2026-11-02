"""School-wide public directory with explicit source and coverage boundaries."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

CATALOG_PATH = Path(__file__).resolve().parents[1] / 'data/campus_catalog.json'
DIRECTORY_URL = 'https://web.nutn.edu.tw/teaching.html'


def official_url(url):
    parsed = urlparse(str(url))
    return parsed.scheme == 'https' and bool(parsed.hostname) and (
        parsed.hostname == 'nutn.edu.tw' or parsed.hostname.endswith('.nutn.edu.tw'))


class CampusCatalog:
    def __init__(self, path=CATALOG_PATH):
        self.document = json.loads(Path(path).read_text(encoding='utf-8'))
        self.units = self.document['units']
        self.contacts = self.document['contacts']
        for row in self.units + self.contacts:
            url = row.get('source_url') or row.get('directory_source')
            if not official_url(url) or row.get('authority') != 'official' or row.get('validity') != 'active':
                raise ValueError('Campus catalog contains an untrusted record')
            if row.get('public_email') and not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', row['public_email']):
                raise ValueError('Campus catalog contains an invalid public email')
        role_aliases = {'校長室': ['校長'], '教務處': ['教務長'], '學務處': ['學務長'], '總務處': ['總務長']}
        for unit in self.units:
            unit['aliases'] = list(set(unit['aliases'] + role_aliases.get(unit['name'], [])))

    def coverage(self):
        return {'scope': 'university_public_directory', 'units': len(self.units),
                'faculty_contacts': len(self.contacts), 'faculty_coverage': 'partial',
                'retrieved_at': self.document['retrieved_at'],
                'description': '全校公開單位名錄；教師與信箱依已收錄的官方頁面提供，尚未收錄時會停止並附來源。'}

    def units_for(self, query):
        matches = []
        for unit in self.units:
            for alias in unit['aliases']:
                for hit in re.finditer(re.escape(alias), query):
                    matches.append((len(alias), hit.start(), hit.end(), unit))
        taken, result = [], []
        for _, start, end, unit in sorted(matches, key=lambda item: -item[0]):
            if any(start < b and end > a for a, b in taken):
                continue
            taken.append((start, end))
            if unit not in result:
                result.append(unit)
        return result

    def recipient_chunks(self, existing):
        known = {(r.get('department', '資訊工程學系'), r['teacher_name'], r['public_email']) for r in existing}
        rows = [dict(row) for row in self.contacts if (row['department'], row['teacher_name'], row['public_email']) not in known]
        for row in rows:
            expertise = re.search(r'(?:研究專長|學術專長|專長)[：:\s]*([^※]+?)(?=※|電話|信箱|$)', row['content'])
            if expertise and not row['research_areas']:
                row['research_areas'] = [expertise[1].strip()]
        for unit in self.units:
            if not unit.get('public_email'):
                continue
            rows.append({'chunk_id': unit['chunk_id'], 'teacher_name': unit['name'],
                'source_id': 'nutn-unit-' + hashlib.sha256(unit['url'].encode()).hexdigest()[:12],
                'source_url': unit['url'], 'department': unit['name'], 'title': '官方單位聯絡窗口',
                'public_email': unit['public_email'], 'research_areas': [],
                'content': f"{unit['name']}官方公開聯絡 Email：{unit['public_email']}。",
                'authority': 'official', 'validity': 'active', 'retrieved_at': unit['retrieved_at'],
                'index_version': 'campus-index-v1', 'recipient_kind': 'unit', 'aliases': unit['aliases']})
        # A stable qualified display name prevents same-name recipients overwriting each other.
        counts = Counter(r['teacher_name'] for r in rows + list(existing))
        for row in rows:
            row['person_name'] = row['teacher_name']
            if counts[row['teacher_name']] > 1:
                row['teacher_name'] += f"（{row['department']}）"
        return rows

    @staticmethod
    def citations(unit):
        urls = [unit['directory_source']]
        if unit.get('phone_source_url'):
            urls.append(unit['phone_source_url'])
        if unit.get('page_status') == 'fetched' and unit['url'] not in urls:
            urls.append(unit['url'])
        return [{'source_id': 'nutn-campus-directory', 'chunk_id': unit['chunk_id'],
                 'label': f"南大官方－{unit['name']}", 'url': url} for url in urls]

    def answer(self, query):
        units = self.units_for(query)
        if not units:
            if re.search(r'全校.*(?:系所|單位)|有哪些(?:學系|系所|單位)|學校.*(?:有哪些系|有哪些單位)', query):
                category = 'administrative' if '行政' in query else 'academic'
                names = '、'.join(u['name'] for u in self.units if u['category'] == category)
                return {'status': 'ok', 'answer': f'目前全校官方名錄收錄的單位包括：{names}。各單位官網也可查詢，請說明想找的單位或事情。',
                'citations': [{'source_id': 'nutn-campus-directory', 'label': '南大－官方單位名錄',
                    'url': 'https://web.nutn.edu.tw/administrative.html' if category == 'administrative' else DIRECTORY_URL}],
                    'evidence': self.coverage(), 'retrieval': None, 'error': None,
                    'suggested_action': None, 'detected_teacher': None, 'used_context': False}
            return None
        blocks, citations = [], []
        missing = False
        for unit in units[:4]:
            line = unit['name'] + '：'
            details = []
            if unit.get('telephone'):
                details.append('電話 ' + unit['telephone'] + (' 轉 ' + '、'.join(unit['extensions']) if unit['extensions'] else ''))
            if unit.get('public_email'):
                details.append('公開 Email ' + unit['public_email'])
            line += '；'.join(details) if details else '目前收錄官方單位入口，尚未驗證個別電話或信箱。'
            if re.search('時間|幾點|開放|營業|休息', query):
                line += '目前快照未收錄可驗證的固定服務時間，請由官網或電話確認。'
                missing = True
            if re.search('主任|院長|校長|承辦人|誰負責', query):
                line += '目前單位名錄不足以確認現任人員姓名，請查看該單位官方頁面。'
                missing = True
            if re.search('流程|辦法|補發|申請條件|怎麼申請|如何申請', query):
                line += '目前名錄只收錄公開聯絡資訊，未載入這項業務的完整辦理流程，請由該單位確認。'
                missing = True
            if re.search('師資|老師|教師|教授', query):
                line += '這筆單位聯絡資料不能代替特定教師的資料；目前師資收錄不完整，請提供教師全名，或查看該系官方師資頁。'
                missing = True
            line += f" 官網：{unit['url']}"
            blocks.append(line)
            citations.extend(self.citations(unit))
        return {'status': 'insufficient_evidence' if missing else 'ok', 'answer': '\n\n'.join(blocks),
                'citations': citations, 'evidence': {'units': units[:4], 'retrieved_at': self.document['retrieved_at']},
                'retrieval': {'model': 'campus_directory', 'candidates': [
                    {'rank': i+1, 'chunk_id': u['chunk_id'], 'teacher_name': u['name'],
                     'score': 1, 'score_label': 'explicit unit match'} for i, u in enumerate(units[:4])],
                    'evidence_gate': {'passed': not missing, 'failure_code': 'DETAIL_NOT_IN_SOURCE' if missing else None}},
                'used_context': False, 'detected_teacher': None, 'suggested_action': None,
                'error': {'code': 'DETAIL_NOT_IN_SOURCE'} if missing else None}


def resolve_recipient(service, query):
    """Only owned server-side official records can supply a recipient address."""
    query = str(query).strip()
    if not query:
        return []
    records = list(service.teacher_by_name.values())
    exact = [r for r in records if query in (r['teacher_name'], r['public_email'], r.get('person_name'))]
    if exact:
        return same_contact_once(exact)
    matches = [r for r in records if any(
        token and token in query for token in (r['teacher_name'], r.get('person_name'), *r.get('aliases', [])))]
    people = [r for r in matches if r.get('recipient_kind') != 'unit']
    if people:
        matches = people
    elif re.search('老師|教授', query):
        # Naming a department must not silently choose its office instead of
        # the requested (possibly unknown) teacher.
        matches = []
        surname = re.search(r'([\u4e00-\u9fff])(?:老師|教授)', query)
        if surname:
            matches = [r for r in records if r.get('recipient_kind') != 'unit' and r['teacher_name'].startswith(surname[1])]
    # Disambiguate duplicate people using an explicitly named department.
    units = service.catalog.units_for(query) if getattr(service, 'catalog', None) else []
    if units and matches and all(r.get('recipient_kind') != 'unit' for r in matches):
        return same_contact_once([r for r in matches if r.get('department') in {u['name'] for u in units}])
    narrowed = [r for r in matches if r.get('department') and r['department'] in query]
    return same_contact_once(narrowed or matches)


def same_contact_once(rows):
    """One public name/address may legitimately appear in multiple units.

    Keep every affiliation in selectors, but don't turn the identical address
    into a false ambiguity. Different addresses or people still require choice.
    """
    keys={(row.get('person_name') or row['teacher_name'], row['public_email'].lower()) for row in rows}
    return rows[:1] if len(keys)==1 else rows
