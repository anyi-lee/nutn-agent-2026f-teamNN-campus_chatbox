"""Deterministic faculty cards/rows and public profile discovery (lxml maintenance).

Each candidate stays inside a one-email/one-identity card. Navigation, footers,
CV prose and unexplained email/name combinations never become contact facts.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from audit_faculty_sources import clean, official, EMAIL
from faculty_profile_parser import parse_profile_tables
from lxml import html

RANK = r'(?:特聘|專任|合聘|兼任)?(?:助理教授|副教授|教授|講師|研究員)'
NAME = r'[\u4e00-\u9fff]{2,4}?'
NOT_NAMES = set('學歷 專長 電話 分機 學位 姓名 職稱 教授 副教授 助理教授 助理 講師 系主任 院長 專任教師 兼任教師 退休教師 專任師資 兼任師資 教師介紹 師資介紹 個人網頁 個人網站 聯絡方式 電子信箱 研究專長 最高學歷 學術專長 專業領域 專長領域 專業發展 學術成果 課程資訊 聯絡我們 回到首頁 首頁 了解更多 查閱 系所介紹 系友會 行政助理 行政人員 系辦職員 研究室 資訊工程 館藏發展'.split())


def valid_name(name):
    return bool(re.fullmatch(NAME,name) and name not in NOT_NAMES and not re.search('教授|主任|院長|講師|助理|老師|主聘|支援|學程|系所|成員|校友',name))


def identity(text):
    text = re.sub(r'^[◤►▶\s]+','',text).strip()
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])','',text)
    if text in ('主聘','支援','傑出校友','專任老師','兼任老師') or text in NOT_NAMES or re.search('人員|分類|下一頁|上一頁|系所成員|成員介紹|繁體中文|系辦|查詢',text):
        return None
    text = re.sub(r'^(?:中心主任|主任)\s*(?='+NAME+r'$)','',text)
    match = re.match(r'^('+NAME+r')\s*('+RANK+r')(?=$|[\s（(兼])',text)
    if match and valid_name(match[1]):
        return match[1], match[2], 5
    if re.search('教授|講師|主任|院長|行政|系友|查閱|助理|職員|師資|教師',text):
        # Rank-only/navigation labels are not Chinese personal names. Keep a
        # genuine name plus a role suffix, but never "副教授兼" or "卓主任".
        role = re.fullmatch(r'('+NAME+r')\s*(?:系主任|主任|院長)',text)
        if role and valid_name(role[1]):
            return role[1],'',2
        return None
    match = re.fullmatch(r'('+NAME+r')(?:\s*(?:系主任|主任|院長)|\s*[(（][^()（）]{1,35}[)）])?',text)
    if match and valid_name(match[1]):
        return match[1], '', 1
    return None


def candidates(node, expected_name=None):
    result = {}
    for part in node.iter():
        if not isinstance(part.tag,str):
            continue
        if part.tag == 'img':
            found = identity((part.get('alt') or '').strip())
            if found:
                result[found[0]]=max(result.get(found[0],0),found[2]+1)
            continue
        if part.tag not in ('h1','h2','h3','h4','h5','h6','a','p','span','div','td','li','strong','b','font'):
            continue
        direct=identity((part.text or '').strip())
        if direct:
            result[direct[0]]=max(result.get(direct[0],0),direct[2]+1)
        text = clean(part)
        if len(text)>70:
            continue
        found = identity(text)
        if found:
            weight=found[2]
            cls=(part.get('class') or '').lower()
            if re.search(r'(teacher|faculty|member)[_-]?(name|title)|(?:^|\s)name(?:\s|$)|field-name-title',cls):
                weight+=4
            if part.tag.startswith('h') and part.tag[1:].isdigit():
                weight+=2
            if part.tag=='a' and re.search('faculty|teacher|member|pageinfo|detail',part.get('href') or '',re.I):
                weight+=3
            result[found[0]]=max(result.get(found[0],0),weight)
    if expected_name and expected_name in result:
        # Exact identity evidence only. "仙湧" occurring inside "劉仙湧" is not
        # a second professor and must never override the full-name evidence.
        result[expected_name]=max(result.get(expected_name,0),8)
    return result


def emails(node):
    text = clean(node)
    values=set(EMAIL.findall(text))
    for a in node.xpath('.//a[starts-with(translate(@href,"MAILTO","mailto"),"mailto:")]'):
        values.update(EMAIL.findall(a.get('href') or ''))
    # Only repair whitespace inside a complete, explicit address token, e.g.
    # "kil5@mail .nutn.edu.tw". Never invent a username/domain or punctuation.
    for raw in re.findall(r'[A-Za-z0-9._%+-]+\s*@\s*(?:[A-Za-z0-9-]+\s*\.\s*)+[A-Za-z]{2,}',text):
        values.add(re.sub(r'\s+','',raw))
    return values


def unmodified_emails(node):
    values=set(EMAIL.findall(clean(node)))
    for a in node.xpath('.//a[@href]'):
        if (a.get('href') or '').lower().startswith('mailto:'):
            values.update(EMAIL.findall(a.get('href')))
    return values


def record_from_block(node, expected_name=None, rank_hint=None):
    text=clean(node)
    addresses=emails(node)
    if len(addresses)!=1 or (not re.search(RANK,text) and not (expected_name and rank_hint)):
        return None
    names=candidates(node,expected_name)
    if not names:
        return None
    best=max(names.values())
    picked=[name for name,weight in names.items() if weight==best]
    if len(picked)!=1 or (expected_name and picked[0]!=expected_name):
        return None
    name=picked[0]
    rank=re.search(r'職稱\s*[：:]?\s*('+RANK+r')',text)
    if not rank:
        rank=re.search(re.escape(name)+r'\s*('+RANK+r')',text)
    if not rank:
        rank=re.search('('+RANK+')',text)
    areas=re.search(r'(?:課程及研究領域|研究專長|學術專長|專長領域|專業領域|專\s*長)\s*[：:]?\s*(.{1,350}?)(?=\s*(?:E-?mail|Email|電\s*話|聯絡電話|分機|研究室|學歷|班級導師|實驗室|TEL|Tel|發表著作)|$)',text,re.I)
    return {'teacher_name':name,'title':rank[1] if rank else rank_hint,'public_email':next(iter(addresses)),
            'research_areas':[v.strip() for v in re.split('[、，；;]',areas[1]) if v.strip()] if areas else [],
            'parse_method':'one_identity_one_email_block',
            'email_whitespace_normalized':next(iter(addresses)) not in unmodified_emails(node)}


def extract_contacts(doc, expected_name=None, rank_hint=None):
    # Keep only visible-content regions; authentication forms and footer contacts
    # are neither faculty evidence nor appropriate persisted cache fixtures.
    doc=html.fromstring(html.tostring(doc,encoding='unicode'))
    for node in doc.xpath('//footer|//nav|//input|//textarea|//button|//header[.//nav or @role="banner"]|//*[@role="navigation"]'):
        node.drop_tree()
    records=[]
    for fields in parse_profile_tables(html.tostring(doc,encoding='unicode'),expected_name,allow_missing_title=bool(expected_name)):
        if fields['title']=='教師（官網未列職稱）' and rank_hint:fields['title']=rank_hint
        records.append({**fields,'parse_method':'labelled_profile_table'})
    targets=[]
    for node in doc.iter():
        if not isinstance(node.tag,str):
            continue
        if '@' in (node.text or '') or 'mailto:' in (node.get('href') or '').lower():
            targets.append(node)
        if '@' in (node.tail or '') and node.getparent() is not None:
            targets.append(node.getparent())
    for node in targets:
        current=node
        for _ in range(12):
            if current is None or current.tag in ('body','html'):
                break
            if len(emails(current))>1:
                break
            found=record_from_block(current,expected_name,rank_hint)
            if found:
                records.append(found)
                break
            current=current.getparent()
    merged={}
    for row in records:
        key=(row['teacher_name'],row['public_email'])
        if key not in merged or (merged[key]['parse_method']!='labelled_profile_table' and row['research_areas'] and not merged[key]['research_areas']):
            merged[key]=row
    return list(merged.values())


def discover(doc, url):
    directories,profiles=[],[]
    for a in doc.xpath('//a[@href]'):
        target=urljoin(url,a.get('href')).split('#')[0]
        if not official(target) or target==url or re.search('logout|login|wp-admin|wp-login',target,re.I):
            continue
        text=clean(a)
        pagination = (re.fullmatch(r'下一頁|下頁|Next|next|[2-9]\d?',text) or 'next' in (a.get('rel') or '').split())
        if pagination and urlparse(target).hostname == urlparse(url).hostname and (urlparse(target).path==urlparse(url).path or '/page/' in urlparse(target).path):
            if target not in directories:directories.append(target)
        if len(text)<45 and re.search('專任(?:教師|師資|老師)|師資與成員|師資成員',text) and not re.search('兼任|退休',text):
            if target not in directories:directories.append(target)
        options=candidates(a)
        if not options and re.search(r'faculty|teacher|member|detail|teacv|teaportfolio',target,re.I):
            parent=a.getparent()
            for _ in range(4):
                if parent is None:break
                options=candidates(parent)
                if options:
                    best=max(options.values())
                    if len([name for name,weight in options.items() if weight==best])==1:
                        break
                parent=parent.getparent()
        # A profile link has an explicit name and recognisable public profile URL
        # (not a generic CV paragraph or external search link).
        if options and re.search(r'faculty=|/faculty/|facultyview_|teacher.*\.(?:aspx|asp|html)|/(?:about/)?detail\.php|task=pageinfo|member.*\.(?:html|php)|tea(?:cv|portfolio)\.aspx',target,re.I):
            best=max(options.values());names=[name for name,weight in options.items() if weight==best]
            if len(names)==1 and not re.search('faculty_category|teacherfulltime',target,re.I):
                pair=(target,names[0])
                if pair not in profiles:profiles.append(pair)
    return directories,profiles
