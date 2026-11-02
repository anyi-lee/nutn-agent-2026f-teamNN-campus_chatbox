#!/usr/bin/env python3
"""Audit configured faculty sources and their explicit directory/profile links.

Writes only a review report to --output and raw temporary cache. Publication to
the application snapshot is deliberately a separate reviewed operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse, unquote

from audit_faculty_sources import ROOT, fetch_page, clean
from verified_faculty_extract import extract_contacts, discover, candidates, identity


def audit_department(seed,cache):
    queue=[(seed['url'],None,'seed',0)]
    visited,documents,records,failures,discovered_names=set(),[],[],[],set()
    ranks={}
    while queue and len(visited)<50:
        url,expected,kind,depth=queue.pop(0)
        if url in visited:continue
        visited.add(url)
        try:
            doc,meta=fetch_page(url,cache)
            if kind!='profile':
                for node in doc.xpath('//h1|//h2|//h3|//h4|//strong'):
                    found=identity(clean(node))
                    if found and found[1]:ranks[found[0]]=found[1]
            rows=extract_contacts(doc,expected,ranks.get(expected))
            documents.append({**meta,'kind':kind,'expected_name':expected,'parsed_contacts':len(rows)})
            for fields in rows:
                name=fields['teacher_name'];email=fields['public_email']
                records.append({**fields,'department':seed['department'],'source_url':url,
                    'membership_source_url':seed['url'],'retrieved_at':meta['retrieved_at'],
                    'source_id':'nutn-campus-'+hashlib.sha256(url.encode()).hexdigest()[:12],
                    'chunk_id':'campus-person-'+hashlib.sha256((seed['department']+'|'+name+'|'+email).encode()).hexdigest()[:14],
                    'authority':'official','validity':'active','recipient_kind':'faculty','index_version':'campus-index-v2',
                    'content':f"姓名：{name}；職稱：{fields['title']}；電子信箱：{email}；專業領域：{'、'.join(fields['research_areas'])}"})
            if kind=='profile':continue
            if kind=='seed':
                for verify in seed.get('verification_profiles',[]):
                    queue.append((verify['url'],verify['name'],'profile',depth+1))
            directories,profiles=discover(doc,url)
            is_individual = any(token in url.lower() for token in ('?faculty=','/detail.php','facultyview_'))
            if not is_individual:
                discovered_names.update(name for name,weight in candidates(doc).items() if weight>=4)
            if depth<2:
                for target in directories[:3]:
                    if urlparse(target).hostname==urlparse(seed['url']).hostname and target not in visited:
                        queue.append((target,None,'directory',depth+1))
            for target,name in profiles:
                full=[row['teacher_name'] for row in records if len(row['teacher_name'])>len(name)
                      and row['teacher_name'].endswith(name) and row['teacher_name'] in unquote(target)]
                if len(set(full))==1:name=full[0]
                discovered_names.add(name)
                if target not in visited and name not in {row['teacher_name'] for row in records}:
                    queue.append((target,name,'profile',depth+1))
        except Exception as exc:
            failures.append({'url':url,'kind':kind,'expected_name':expected,'status':'fetch_failed',
                             'error_type':type(exc).__name__,'error':str(exc)[:250]})
    # Keep conflicting public addresses for review; do not silently choose one.
    by_person={}
    for row in records:
        by_person.setdefault(row['teacher_name'],{}).setdefault(row['public_email'],row)
    contacts,conflicts=[],[]
    for name,addresses in by_person.items():
        if len(addresses)==1:
            contacts.append(next(iter(addresses.values())))
        else:
            conflicts.append({'teacher_name':name,'code':'MULTIPLE_SOURCE_EMAILS','records':list(addresses.values())})
    return {**seed,'status':'fetched' if documents else 'fetch_failed','documents':documents,'failures':failures,
            'contacts':contacts,'conflicts':conflicts,'unresolved_names':sorted(discovered_names-{row['teacher_name'] for row in contacts}),
            'limit_reached':bool(queue),'remaining_pages':len(queue)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--department',action='append')
    args=parser.parse_args()
    seeds=json.loads((ROOT/'data/faculty_sources.json').read_text())['sources']
    if args.department:seeds=[s for s in seeds if s['department'] in args.department]
    args.cache_dir.mkdir(parents=True,exist_ok=True)
    def run(seed):
        row=audit_department(seed,args.cache_dir)
        print(row['department'],'pages:',len(row['documents']),'verified:',len(row['contacts']),
              'conflicts:',len(row['conflicts']),'unresolved:',len(row['unresolved_names']),'failed:',len(row['failures']),flush=True)
        return row
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(run,seeds))
    args.output.write_text(json.dumps({'schema_version':'faculty-audit-v1','departments':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
