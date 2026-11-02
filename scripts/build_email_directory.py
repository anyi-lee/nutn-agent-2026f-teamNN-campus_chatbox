#!/usr/bin/env python3
"""Compile public recipient grouping for the static UI (no keys or live calls).

The running /api/config recipient allowlist remains authoritative. This file
only adds department/category labels; it never supplies a recipient email.
Print JSON, or use --write to regenerate the checked-in public UI asset.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from campus_catalog import CampusCatalog, CATALOG_PATH


def build_directory():
    catalog = CampusCatalog()
    path = ROOT / 'data/faculty_chunks.json'
    original = json.loads(path.read_text(encoding='utf-8'))['chunks']
    records = original + catalog.recipient_chunks(original)
    records.append({'teacher_name': '資訊工程學系辦公室', 'department': '資訊工程學系',
                    'recipient_kind': 'unit', 'title': '系辦公開聯絡窗口'})
    units = [{'name': unit['name'], 'category': unit['category'], 'url': unit['url']}
             for unit in catalog.units]
    admin_names = [unit['name'] for unit in units if unit['category'] == 'administrative']
    for unit in units:
        if unit['category'] == 'administrative':
            # The official snapshot spells sections with their office prefix.
            # Use that explicit prefix, not a guessed semantic relationship.
            parents = [name for name in admin_names if name != unit['name'] and unit['name'].startswith(name)]
            unit['parent_office'] = min(parents, key=len) if parents else unit['name']
    recipients = [{'name': row['teacher_name'], 'title': row['title'],
                   'department': row.get('department', '資訊工程學系'),
                   'kind': row.get('recipient_kind', 'faculty')}
                  for row in records]
    digest = hashlib.sha256(path.read_bytes() + CATALOG_PATH.read_bytes()).hexdigest()
    return {'schema_version': 'email-directory-v2', 'source_sha256': digest,
            'retrieved_at': catalog.document['retrieved_at'], 'units': units, 'recipients': recipients}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='Update ui/email_directory.json')
    args = parser.parse_args()
    output = json.dumps(build_directory(), ensure_ascii=False, indent=2) + '\n'
    if args.write:
        (ROOT / 'ui/email_directory.json').write_text(output, encoding='utf-8')
        print('Updated ui/email_directory.json (public names/categories only; no email addresses).')
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
