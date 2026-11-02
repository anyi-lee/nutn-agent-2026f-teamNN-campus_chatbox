#!/usr/bin/env python3
"""Bounded official-page inspection. Raw pages stay in a caller's temporary cache.

No login, script execution, key loading, or external-domain redirects. Requires
lxml only for this maintenance workflow, not the application runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import subprocess
from urllib.error import URLError
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def official(url):
    parsed = urlparse(url)
    return (parsed.scheme in ('https','http') and not parsed.username and not parsed.password
            and parsed.port in (None,80,443) and bool(parsed.hostname)
            and (parsed.hostname == 'nutn.edu.tw' or parsed.hostname.endswith('.nutn.edu.tw')))


class OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official(newurl):
            raise ValueError('Non-official redirect rejected before network request')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def curl_with_system_trust(url, body_path):
    """Use OS trust when the bundled Python CA bundle lacks an issuer. No -k."""
    target = url
    for _ in range(5):
        result = subprocess.run(['curl','--fail','--silent','--show-error','--max-time','18',
            '--max-filesize','2000000','--output',str(body_path),'--write-out','%{http_code}\n%{redirect_url}',target],
            capture_output=True,text=True,timeout=23,check=True)
        code, _, redirect = result.stdout.partition('\n')
        if code.startswith('3') and redirect:
            if not official(redirect.strip()):
                raise ValueError('Non-official curl redirect rejected')
            target = redirect.strip()
            continue
        if not code.startswith('2'):
            raise ValueError('Unexpected HTTP response: '+code)
        return body_path.read_bytes(), target
    raise ValueError('Too many redirects')


def clean(node):
    return re.sub(r'\s+', ' ', ' '.join(node.itertext())).strip()


def fetch_page(url, cache):
    if not official(url):
        raise ValueError('Non-official URL rejected')
    key = hashlib.sha256(url.encode()).hexdigest()
    body_path, meta_path = cache / (key+'.html'), cache / (key+'.json')
    if body_path.exists() and meta_path.exists():
        raw, meta = body_path.read_bytes(), json.loads(meta_path.read_text())
    else:
        transport = 'urllib-verified-tls'
        try:
            with build_opener(OfficialRedirects()).open(Request(url,headers={'User-Agent':'NUTN-Campus-Agent-Coursework/1.0'}), timeout=18) as response:
                raw, final_url = response.read(2_000_001), response.url
        except URLError as exc:
            if not isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise
            raw, final_url = curl_with_system_trust(url, body_path)
            transport = 'system-curl-verified-tls'
        if len(raw)>2_000_000:
            raise ValueError('Page exceeds 2 MB')
        meta = {'url':url,'final_url':final_url,'sha256':hashlib.sha256(raw).hexdigest(),'transport':transport,
                'retrieved_at':datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')}
        body_path.write_bytes(raw)
        meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        markup = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        markup = raw
    doc = html.fromstring(markup)
    for node in doc.xpath('//script|//style|//noscript'):
        node.drop_tree()
    return doc, meta


def inspect(source, cache):
    try:
        doc, meta = fetch_page(source['url'],cache)
        names = [(node.tag, clean(node)[:140]) for node in doc.xpath('//h1|//h2|//h3|//h4|//strong') if clean(node)]
        links = []
        for a in doc.xpath('//a[@href]'):
            label = clean(a)
            target = urljoin(source['url'],a.get('href')).split('#')[0]
            if official(target) and (re.search('師資|專任|教師|成員',label) or re.fullmatch(r'[\u4e00-\u9fff]{2,4}(?:\s*(?:副教授|教授|助理教授))?',label)):
                item = {'label':label,'url':target}
                if item not in links:
                    links.append(item)
        return {**source,'status':'fetched','source':meta,'emails':sorted(set(EMAIL.findall(clean(doc)))),
                'headings':names,'links':links}
    except Exception as exc:
        return {**source,'status':'fetch_failed','error_type':type(exc).__name__,'error':str(exc)[:250]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.cache_dir.mkdir(parents=True,exist_ok=True)
    seeds=json.loads((ROOT/'data/faculty_sources.json').read_text())['sources']
    with ThreadPoolExecutor(max_workers=4) as pool:
        records=list(pool.map(lambda seed:inspect(seed,args.cache_dir),seeds))
    args.output.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for row in records:
        print(row['department'],row['status'],'emails:',len(row.get('emails',[])),'links:',len(row.get('links',[])),flush=True)


if __name__=='__main__':
    main()
