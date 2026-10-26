"""Check generated HTML links, images, and schema without network requests."""
import json,re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,unquote
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs'
base=urlsplit(json.loads((ROOT/'content/site.json').read_text())['url']).path
errors=[];pages=list(OUT.rglob('*.html'))
class Check(HTMLParser):
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        for attr in ('href','src'):
            val=a.get(attr,'');p=urlsplit(val)
            if not val or p.scheme or p.netloc or val.startswith('#'):continue
            name=unquote(p.path)
            if not name.startswith(base):errors.append(f'{self.file}: outside base {val}');continue
            target=OUT/name[len(base):]
            if target.is_dir():target=target/'index.html'
            if not target.is_file():errors.append(f'{self.file}: missing {val}')
        if tag=='img' and not a.get('alt'):errors.append(f'{self.file}: missing alt')
for f in pages:
    parser=Check();parser.file=f.relative_to(OUT);text=f.read_text();parser.feed(text)
    if text.count('<h1')!=1:errors.append(f'{f}: needs one h1')
    for raw in re.findall(r'<script type="application/ld\+json">(.*?)</script>',text):json.loads(raw)
if errors:raise SystemExit('\n'.join(errors))
print(f'Local links, assets, image alt and JSON-LD checked: {len(pages)} pages')
