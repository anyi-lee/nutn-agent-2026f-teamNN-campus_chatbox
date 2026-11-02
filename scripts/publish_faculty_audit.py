#!/usr/bin/env python3
"""Publish an explicitly reviewed faculty audit; never fetch or guess contacts.

This is a merge, not a whole-school replacement. Existing records in other
departments remain intact. Conflicts and untrusted sources stop publication.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from campus_catalog import official_url
from build_email_directory import build_directory


def retain_reviewed_faculty(current, refreshed):
    """A shallow directory refresh must not erase the reviewed deep profiles.

    Keep their original timestamps/hashes, not a false claim of revalidation.
    An actual changed address requires a separately reviewed faculty audit.
    """
    protected = [r for r in current['contacts'] if r.get('index_version') == 'campus-index-v2']
    contacts = {(r['department'], r['teacher_name']):r for r in refreshed['contacts']}
    for row in protected:
        key = (row['department'],row['teacher_name'])
        if key in contacts and contacts[key]['public_email'].lower() != row['public_email'].lower():
            raise ValueError('Fresh directory conflicts with reviewed faculty email; previous snapshot retained')
        contacts[key] = row
    used_urls = {r[k] for r in protected for k in ('source_url','membership_source_url')}
    sources = {s['url']:s for s in refreshed['sources']}
    sources.update({s['url']:s for s in current['sources'] if s['url'] in used_urls})
    return {**refreshed, 'contacts':list(contacts.values()), 'sources':list(sources.values())}


def merge(catalog, report):
    if report.get('schema_version') != 'faculty-audit-v1':
        raise ValueError('Unknown audit format')
    academic = {u['name'] for u in catalog['units'] if u['category'] == 'academic'}
    contacts = {(r['department'], r['teacher_name']): r for r in catalog['contacts']}
    sources = {r['url']: r for r in catalog['sources']}
    for department in report['departments']:
        if department['department'] not in academic or department['conflicts'] or department['limit_reached']:
            raise ValueError('Unknown department, conflicting contact, or truncated crawl')
        documents = {d['url']: d for d in department['documents']}
        for row in department['contacts']:
            if (row['department'] != department['department'] or row['source_url'] not in documents
                    or row['membership_source_url'] != department['url']
                    or not official_url(row['source_url']) or not official_url(row['membership_source_url'])
                    or row['authority'] != 'official' or row['validity'] != 'active'
                    or not re.fullmatch(r'[\u4e00-\u9fff]{2,4}', row['teacher_name'])
                    or not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', row['public_email'])):
                raise ValueError('Contact lacks audited identity/source/email evidence')
            key = (row['department'], row['teacher_name'])
            if key in contacts and contacts[key]['public_email'].lower() != row['public_email'].lower():
                raise ValueError('Existing contact email conflict requires human review')
            contacts[key] = row
        for row in department['documents']:
            sources[row['url']] = row
    result = {**catalog, 'contacts': list(contacts.values()), 'sources': list(sources.values())}
    ids = [r['chunk_id'] for r in result['contacts']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate contact chunk IDs')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reviewed-audit', required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.reviewed_audit.read_text(encoding='utf-8'))
    path = ROOT / 'data/campus_catalog.json'
    result = merge(json.loads(path.read_text(encoding='utf-8')), report)
    result['retrieved_at'] = datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'ui/email_directory.json').write_text(json.dumps(build_directory(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Merged faculty affiliation records:', len(result['contacts']))
    print('Preserved unit directory:', len(result['units']))


if __name__ == '__main__':
    main()
