"""Bounded official-source radar. Produces candidates only; never publishes articles.
No external packages, keys, LLM endpoints, or paid APIs. Treat all source text as untrusted data.
"""
import argparse, datetime as dt, hashlib, html, json, re, time
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
MAX_BYTES=6_000_000
MAX_ITEMS=500
UTC=dt.timezone.utc
JST=dt.timezone(dt.timedelta(hours=9))
RSS1='{http://purl.org/rss/1.0/}'
ATOM='{http://www.w3.org/2005/Atom}'
DC='{http://purl.org/dc/elements/1.1/}'

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

class DatedListing(Links):
    """JR East dates belong to the same li, never to the next link or its URL."""
    def __init__(self):
        super().__init__();self.rows=[];self.stack=[];self.date_parts=None
    def handle_starttag(self,tag,attrs):
        if tag=='li':self.stack.append({'start':len(self.links),'date':None})
        if self.stack and tag=='p' and 'date' in dict(attrs).get('class','').split():self.date_parts=[]
        super().handle_starttag(tag,attrs)
    def handle_data(self,data):
        if self.date_parts is not None:self.date_parts.append(data)
        super().handle_data(data)
    def handle_endtag(self,tag):
        super().handle_endtag(tag)
        if tag=='p' and self.date_parts is not None:
            value=plain(''.join(self.date_parts));self.date_parts=None
            m=re.fullmatch(r'(\d{4})年(\d{1,2})月(\d{1,2})日',value)
            if self.stack and m:
                try:self.stack[-1]['date']=dt.date(*map(int,m.groups())).isoformat()
                except ValueError:pass
        if tag=='li' and self.stack:
            row=self.stack.pop()
            self.rows.extend((url,title,row['date'])for url,title in self.links[row['start']:])

def feed_date_hint(value):
    """A publisher-supplied date is still unverified. Never use channel/updated dates."""
    if not value:return None
    value=value.strip()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):return dt.date.fromisoformat(value).isoformat()
        try:parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:parsed=parsedate_to_datetime(value)
        return parsed.astimezone(JST).date().isoformat() if parsed.tzinfo else None
    except (ValueError,TypeError,OverflowError):return None

def feed_entries(body,source):
    tree=ET.fromstring(body)
    if tree.tag=='rss':
        channel=tree.find('channel');items=tree.findall('./channel/item');prefix=''
    elif tree.tag=='{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF':
        channel=tree.find(RSS1+'channel');items=tree.findall(RSS1+'item');prefix=RSS1
    elif tree.tag==ATOM+'feed':
        channel=tree;items=tree.findall(ATOM+'entry');prefix=ATOM
    else:raise ValueError('Unsupported feed format; not a no-news result')
    if channel is None:raise ValueError('Missing feed channel')
    if source.get('feedChannelTitle') and channel.findtext(prefix+'title')!=source['feedChannelTitle']:
        raise ValueError('Unexpected feed publisher/channel')
    entries=[]
    for item in items:
        if source.get('feedPublisher') and item.findtext(DC+'corp')!=source['feedPublisher']:
            raise ValueError('Unexpected item publisher')
        title=item.findtext(prefix+'title') or ''
        if prefix==ATOM:
            link=next((el.get('href','')for el in item.findall(ATOM+'link') if el.get('rel','alternate')=='alternate' and el.get('type','text/html') in ('text/html','application/xhtml+xml')), '')
            date=item.findtext(ATOM+'published')
        else:
            link=item.findtext(prefix+'link');date=item.findtext(DC+'date') or item.findtext('pubDate') or item.findtext(prefix+'date')
        entries.append((link,plain(title),feed_date_hint(date)))
    return entries

def parse_source(body,source):
    # RSS / Atom can be configured when an official endpoint is verified.
    entries=[]
    if source['kind']=='rss':
        entries=feed_entries(body,source)
    else:
        parser=DatedListing() if source.get('listingDates')=='jr-east-li' else Links()
        parser.feed(body.decode('utf-8',errors='replace'))
        entries=parser.rows if isinstance(parser,DatedListing) else [(link,title,None)for link,title in parser.links]
    result=[];seen=set()
    for link,title,listed in entries:
        if not link or len(title)<10:continue
        if source.get('titlePattern') and not re.search(source['titlePattern'],title):continue
        try:url=canonical(urljoin(source['url'],link))
        except ValueError:continue
        p=urlsplit(url)
        if p.hostname not in source.get('allowedLinkHosts',[source['host']]) or not any(re.search(pattern,p.path) for pattern in source['pathPatterns']):continue
        if url in seen:continue
        seen.add(url);result.append({'id':hashlib.sha256(url.encode()).hexdigest()[:20],'title':title,'url':url,'sourceId':source['id'],'sourceName':source['name'],'category':source['category'],'sourcePublishedAt':None,'sourceListedDate':listed or listing_date_hint(title),'sourceDateBasis':'feed-hint' if source['kind']=='rss' else 'listing-hint','maxListedAgeDays':source.get('maxListedAgeDays')})
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
        t=re.sub(r'[\W_]+','',x['title']);prior=out.get(x['id']);ident=titles.get(t)
        observation={k:x.get(k)for k in ('sourceId','url','sourceListedDate')};observation['lastSeenAt']=now
        if ident and ident!=x['id']:
            existing=out[ident]
            observations=existing.get('sourceObservations') or [{k:existing.get(k)for k in ('sourceId','url','sourceListedDate','lastSeenAt')}]
            observations=[v for v in observations if (v.get('sourceId'),v.get('url'))!=(x.get('sourceId'),x['url'])]
            existing.update(sourceObservations=(observations+[observation])[-8:],lastSeenAt=now,bodyVerified=False,autoPublish=False)
            existing['alternateUrls']=sorted(set(existing.get('alternateUrls',[])+[x['url']]))[:8];continue
        grade,reason=rank(x['title']);out[x['id']]={**(prior or {}),**x,'firstSeenAt':prior['firstSeenAt'] if prior else now,'lastSeenAt':now,'priority':grade,'priorityReason':reason,'status':'candidate','bodyVerified':False,'autoPublish':False}
        observations=(prior or {}).get('sourceObservations',[])
        out[x['id']]['sourceObservations']=([v for v in observations if (v.get('sourceId'),v.get('url'))!=(x.get('sourceId'),x['url'])]+[observation])[-8:]
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

def failure_record(error):
    # Preserve the real HTTP status without retrying/evading a 403 or 429.
    result={'status':'failed','error':type(error).__name__+': '+str(error)[:160]}
    if getattr(error,'code',None):result['httpStatus']=error.code
    return result

def run(output,previous):
    now=dt.datetime.now(UTC).isoformat(timespec='seconds');prior=json.loads(previous.read_text()) if previous and previous.exists() else {}
    sources=[x for x in json.loads((ROOT/'content/sources.json').read_text()) if x.get('enabled',True)];articles=json.loads((ROOT/'content/articles.json').read_text());items=[];runs=[]
    if len(sources)>8:raise ValueError('At most 8 index sources')
    for source in sources:
        try:
            body,status=fetch(source['url'],source['host']);found=parse_source(body,source);items.extend(found);runs.append({'sourceId':source['id'],'url':source['url'],'checkedAt':now,'status':status,'coverage':source.get('coverage','configured-listing-only'),'candidateCount':len(found),'parserWarning':None if found else 'NO_MATCHES: source structure may have changed; not proof of no news'})
        except Exception as e:runs.append({'sourceId':source['id'],'url':source['url'],'checkedAt':now,**failure_record(e)})
        time.sleep(1)
    monitors=[];oldhash={x['url']:x.get('sha256') for x in prior.get('sourceMonitors',[])}
    urls=list(dict.fromkeys(s['url'] for a in articles for s in a['sources']))[:8]
    for url in urls:
        try:
            body,status=fetch(url,urlsplit(url).hostname);digest=hashlib.sha256(body).hexdigest();monitors.append({'url':url,'checkedAt':now,'status':status,'sha256':digest,'changed':bool(oldhash.get(url) and oldhash[url]!=digest),'previousSha256':oldhash.get(url),'action':'editorial-review-only'})
        except Exception as e:monitors.append({'url':url,'checkedAt':now,**failure_record(e),'sha256':oldhash.get(url),'changed':None})
        time.sleep(1)
    rules={v['id']:v.get('titlePattern')for v in sources}
    previous_candidates=[x for x in prior.get('candidates',[]) if not rules.get(x.get('sourceId')) or re.search(rules[x['sourceId']],x['title'])]
    healthy=[s for s in runs if s['status']==200 and s.get('candidateCount',0)>0 and not s.get('parserWarning')]
    health='unavailable' if not healthy else ('degraded' if len(healthy)<len(runs) or any(m['status']!=200 for m in monitors) else 'ok')
    result={'version':1,'collectedAt':now,'health':{'status':health,'sourcesOk':len(healthy),'sourcesTotal':len(runs)},'notice':'候補は未検証。公開記事ではありません。重要度は見出しによる仮判定です。','sources':runs,'sourceMonitors':monitors,'candidates':merge(previous_candidates,items,now),'runs':(prior.get('runs',[])+[{'at':now,'sourcesOk':len(healthy),'sourcesTotal':len(runs),'health':health,'newlySeen':len([x for x in items if x['id'] not in {v['id']for v in prior.get('candidates',[])}])}])[-30:]}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'sources':runs,'candidates':len(result['candidates']),'monitors':len(monitors)},ensure_ascii=False))
    return {'ok':0,'degraded':1,'unavailable':2}[health]

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--previous',type=Path);a=p.parse_args();raise SystemExit(run(a.output,a.previous))
