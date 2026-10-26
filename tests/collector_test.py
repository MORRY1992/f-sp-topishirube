import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('collect',Path(__file__).resolve().parents[1]/'scripts/collect.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class RadarTests(unittest.TestCase):
 def setUp(self):self.source={'url':'https://www.jreast.co.jp/press/','host':'www.jreast.co.jp','id':'east','name':'official','kind':'html','pathPatterns':['^/press/[0-9]{4}/'],'category':'交通'}
 def test_host_path_and_duplicates(self):
  body=b'<a href="/press/2026/new.pdf?utm_source=x">New train launch today</a><a href="https://evil.test/press/2026/new.pdf">Fake breaking news headline</a><a href="/press/2026/new.pdf">New train launch today</a><a href="/login">Not a news announcement</a>'
  result=c.parse_source(body,self.source);self.assertEqual(len(result),1);self.assertEqual(result[0]['url'],'https://www.jreast.co.jp/press/2026/new.pdf');self.assertIsNone(result[0]['sourcePublishedAt'])
 def test_duplicate_image_alt_and_listing_date(self):
  self.assertEqual(c.plain('New train launch New train launch'),'New train launch')
  self.source['titlePattern']='^20'
  body='<a href="/press/2026/test.pdf">2026/10/23 新型列車のお知らせ</a><a href="/press/2026/shop.pdf">ショップ ショップ ショップ</a>'.encode()
  result=c.parse_source(body,self.source);self.assertEqual(len(result),1);self.assertEqual(result[0]['sourceListedDate'],'2026-10-23');self.assertIsNone(result[0]['sourcePublishedAt'])
 def test_safe_links(self):
  for url in ['http://example.com','javascript:alert(1)','https://user:pass@example.com']:
   with self.assertRaises(ValueError):c.canonical(url)
 def test_merge_preserves_first_seen_and_not_verified(self):
  x={'id':'a','title':'新型列車の運行開始','url':'https://example.com/a'};a=c.merge([], [x], '2026-10-26T08:00:00+00:00');b=c.merge(a,[x], '2026-10-26T11:00:00+00:00');self.assertEqual(b[0]['firstSeenAt'],a[0]['firstSeenAt']);self.assertFalse(b[0]['autoPublish']);self.assertFalse(b[0]['bodyVerified']);self.assertEqual(b[0]['priority'],'A')
 def test_priority_is_explicitly_provisional(self):
  grade,why=c.rank('全線運休のお知らせ');self.assertEqual(grade,'S');self.assertIn('確認',why)
 def test_atom(self):
  s={**self.source,'kind':'rss'};body=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>New train service announced</title><link href="https://www.jreast.co.jp/press/2026/notice.html"/></entry></feed>';self.assertEqual(len(c.parse_source(body,s)),1)
if __name__=='__main__':unittest.main()
