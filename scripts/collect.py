"""Bounded official-source radar. Produces candidates only; never publishes articles.
No external packages, keys, LLM endpoints, or paid APIs. Treat all source text as untrusted data.
"""
import argparse, datetime as dt, hashlib, html, json, re, time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
MAX_BYTES=6_000_000
MAX_ITEMS=500
UTC=dt.timezone.utc

def canonical(url):
    p=urlsplit(url)
    if p.scheme!='https' or p.username or p.password: raise ValueError('Only HTTPS without credentials')
    query=urlencode(sorted((k,v)for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')))
    return urlunsplit((p.scheme,p.netloc.lower(),p.path or '/',query,''))

def plain(text):
    text=re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]*>','',text))).strip()
    # Some listings repeat the same headline in image alt text and link text.
    for copies in (3,2):
        size=(len(text)-(copies-1))//copies
        if size>0 and ' '.join([text[:size]]*copies)==text:
            text=text[:size]
    return text[:240]

def listing_date_hint(title):
    # A listing prefix is a hint only, never a verified announcement date.
    m=re.match(r'^(\d{4})/(\d{1,2})/(\d{1,2})(?:\s|$)',title)
    if not m:return None
    try:return dt.date(*map(int,m.groups())).isoformat()
    except ValueError:return None
class Links(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.links=[];self.href=None;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.href=dict(attrs).get('href');self.parts=[]
        if self.href and tag=='img':self.parts.append(dict(attrs).get('alt',''))
    def handle_data(self,data):
        if self.href:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.href:
            self.links.append((self.href,plain(' '.join(self.parts))));self.href=None;self.parts=[]

def parse_source(body,source):
    # RSS / Atom can be configured when an official endpoint is verified.
    entries=[]
    if source['kind']=='rss':
        tree=ET.fromstring(body)
        for item in list(tree.findall('.//item'))+list(tree.findall('.//{http://www.w3.org/2005/Atom}entry')):
            title=item.findtext('title') or item.findtext('{http://www.w3.org/2005/Atom}title') or ''
            link=item.findtext('link')
            if not link:
                el=item.find('{http://www.w3.org/2005/Atom}link');link=el.get('href','') if el is not None else ''
            entries.append((link,plain(title)))
    else:
        parser=Links();parser.feed(body.decode('utf-8',errors='replace'));entries=parser.links
    result=[];seen=set()
    for link,title in entries:
        if not link or len(title)<10:continue
        if source.get('titlePattern') and not re.search(source['titlePattern'],title):continue
        try:url=canonical(urljoin(source['url'],link))
        except ValueError:continue
        p=urlsplit(url)
        if p.hostname not in source.get('allowedLinkHosts',[source['host']]) or not any(re.search(pattern,p.path) for pattern in source['pathPatterns']):continue
        if url in seen:continue
        seen.add(url);result.append({'id':hashlib.sha256(url.encode()).hexdigest()[:20],'title':title,'url':url,'sourceId':source['id'],'sourceName':source['name'],'category':source['category'],'sourcePublishedAt':None,'sourceListedDate':listing_date_hint(title)})
    return result[:100]

def rank(title):
    if any(x in title for x in ['全線運休','長期間運休','運休','運転見合わせ','重大','リコール']):return 'S','緊急・重大の可能性を示す語を検出。公式本文の確認が必要'
    if any(x in title for x in ['新型','運行開始','ダイヤ改正','値上げ','料金改定','料金体系の変更','キャンペーン','発売']):return 'A','予定・予約・利用条件に関わる語を検出'
    if any(x in title for x in ['お知らせ','イベント','臨時','運転','開業']):return 'B','利用者向けの変更・イベント候補'
    if any(x in title for x in ['決算','株主','人事']):return 'D','初期の実用ニュース対象から外れる可能性'
    return 'C','補足候補。対象と実用性を要確認'

def merge(previous,items,now):
    old={x['id']:x for x in previous};out=dict(old);titles={re.sub(r'[\W_]+','',x['title']):x['id'] for x in previous}
    for x in items:
        t=re.sub(r'[\W_]+','',x['title']);prior=old.get(x['id']);ident=titles.get(t)
        if ident and ident!=x['id']:
            existing=out[ident];existing['alternateUrls']=sorted(set(existing.get('alternateUrls',[])+[x['url']]))[:8];continue
        grade,reason=rank(x['title']);out[x['id']]={**(prior or {}),**x,'firstSeenAt':prior['firstSeenAt'] if prior else now,'lastSeenAt':now,'priority':grade,'priorityReason':reason,'status':'candidate','bodyVerified':False,'autoPublish':False}
        titles[t]=x['id']
    return sorted(out.values(),key=lambda x:('SABCD'.index(x['priority']),-dt.datetime.fromisoformat(x['lastSeenAt']).timestamp()))[:MAX_ITEMS]

def fetch(url,allowed_host):
    req=Request(url,headers={'User-Agent':'TopishirubeNewsRadar/1.0 (+https://github.com/MORRY1992/f-sp-topishirube)','Accept':'text/html,application/rss+xml,application/atom+xml,application/pdf;q=0.8'})
    with urlopen(req,timeout=25)as r:
        if urlsplit(r.url).hostname!=allowed_host:raise ValueError('Unexpected redirect host')
        if int(r.headers.get('Content-Length','0')or'0')>MAX_BYTES:raise ValueError('Response too large')
        data=r.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError('Response too large')
        return data,r.status

def run(output,previous):
    now=dt.datetime.now(UTC).isoformat(timespec='seconds');prior=json.loads(previous.read_text()) if previous and previous.exists() else {}
    sources=[x for x in json.loads((ROOT/'content/sources.json').read_text()) if x.get('enabled',True)];articles=json.loads((ROOT/'content/articles.json').read_text());items=[];runs=[]
    if len(sources)>8:raise ValueError('At most 8 index sources')
    for source in sources:
        try:
            body,status=fetch(source['url'],source['host']);found=parse_source(body,source);items.extend(found);runs.append({'sourceId':source['id'],'url':source['url'],'checkedAt':now,'status':status,'candidateCount':len(found),'parserWarning':None if found else 'NO_MATCHES: source structure may have changed; not proof of no news'})
        except Exception as e:runs.append({'sourceId':source['id'],'url':source['url'],'checkedAt':now,'status':'failed','error':type(e).__name__+': '+str(e)[:160]})
        time.sleep(1)
    monitors=[];oldhash={x['url']:x.get('sha256') for x in prior.get('sourceMonitors',[])}
    urls=list(dict.fromkeys(s['url'] for a in articles for s in a['sources']))[:8]
    for url in urls:
        try:
            body,status=fetch(url,urlsplit(url).hostname);digest=hashlib.sha256(body).hexdigest();monitors.append({'url':url,'checkedAt':now,'status':status,'sha256':digest,'changed':bool(oldhash.get(url) and oldhash[url]!=digest),'previousSha256':oldhash.get(url),'action':'editorial-review-only'})
        except Exception as e:monitors.append({'url':url,'checkedAt':now,'status':'failed','sha256':oldhash.get(url),'error':type(e).__name__+': '+str(e)[:160],'changed':None})
        time.sleep(1)
    rules={v['id']:v.get('titlePattern')for v in sources}
    previous_candidates=[x for x in prior.get('candidates',[]) if not rules.get(x.get('sourceId')) or re.search(rules[x['sourceId']],x['title'])]
    result={'version':1,'collectedAt':now,'notice':'候補は未検証。公開記事ではありません。重要度は見出しによる仮判定です。','sources':runs,'sourceMonitors':monitors,'candidates':merge(previous_candidates,items,now),'runs':(prior.get('runs',[])+[{'at':now,'sourcesOk':sum(x['status']==200 for x in runs),'sourcesTotal':len(runs),'newlySeen':len([x for x in items if x['id'] not in {v['id']for v in prior.get('candidates',[])}])}])[-30:]}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'sources':runs,'candidates':len(result['candidates']),'monitors':len(monitors)},ensure_ascii=False))
    return 0 if any(x['status']==200 and x['candidateCount']>0 for x in runs) else 2

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--previous',type=Path);a=p.parse_args();raise SystemExit(run(a.output,a.previous))
