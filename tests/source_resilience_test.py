import datetime as dt
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


c, e, reporter = (module(name) for name in ('collect', 'editorial_queue', 'report_radar'))
NOW = dt.datetime(2026, 10, 29, 16, tzinfo=dt.timezone.utc)
AT = NOW.isoformat()
SOURCES = json.loads((ROOT/'content/sources.json').read_text())
FEED = next(s for s in SOURCES if s['id'] == 'jr-east-prtimes')
URL = 'https://prtimes.jp/main/html/rd/p/000000001.000017557.html'


def rss1(date='2026-10-29T23:00:00+09:00', publisher='東日本旅客鉄道株式会社', url=URL):
    return f'''<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
      xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
      <channel><title>{FEED['feedChannelTitle']}</title><dc:date>2026-10-30</dc:date></channel>
      <item><title>新型列車キャンペーンのお知らせ</title><link>{url}</link>
      <dc:corp>{publisher}</dc:corp><dc:date>{date}</dc:date>
      <description>Never copy article body or image URLs into the queue.</description></item></rdf:RDF>'''.encode()


class SourceResilienceTests(unittest.TestCase):
    def queue(self, items, sources=None):
        return {'collectedAt': AT, 'sources': sources or [{'sourceId': FEED['id'], 'status': 200, 'candidateCount': 1}], 'candidates': c.merge([], items, AT)}

    def test_company_rss1_dates_are_unverified_and_body_is_not_saved(self):
        item = c.parse_source(rss1(), FEED)[0]
        self.assertEqual(item['sourceListedDate'], '2026-10-29')
        self.assertIsNone(item['sourcePublishedAt'])
        self.assertNotIn('description', item)
        result = e.prepare(self.queue([item]), [], NOW)
        self.assertEqual(result['worklist'][0]['dateStatus'], 'feed-hint-only')
        self.assertFalse(result['worklist'][0]['bodyVerified'])
        self.assertFalse(result['worklist'][0]['autoPublish'])

    def test_company_channel_change_is_a_failure(self):
        body = rss1().replace(FEED['feedChannelTitle'].encode(), b'Other company')
        with self.assertRaises(ValueError):
            c.parse_source(body, FEED)

    def test_company_item_publisher_change_is_a_failure(self):
        with self.assertRaises(ValueError):
            c.parse_source(rss1(publisher='Unrelated company'), FEED)

    def test_other_publishers_paths_and_hosts_are_excluded(self):
        for url in ('https://prtimes.jp/main/html/rd/p/000000001.000099999.html',
                    'https://evil.test/main/html/rd/p/000000001.000017557.html',
                    'http://prtimes.jp/main/html/rd/p/000000001.000017557.html'):
            self.assertFalse(c.parse_source(rss1(url=url), FEED))

    def test_rss2_supports_rfc2822_item_date(self):
        source = {**FEED, 'feedChannelTitle': None, 'feedPublisher': None}
        body = f'<rss><channel><title>Official</title><item><title>New train announcement</title><link>{URL}</link><pubDate>Thu, 29 Oct 2026 15:10:00 GMT</pubDate></item></channel></rss>'.encode()
        self.assertEqual(c.parse_source(body, source)[0]['sourceListedDate'], '2026-10-30')

    def test_atom_uses_alternate_link_and_published_not_updated(self):
        source = {**FEED, 'feedChannelTitle': None, 'feedPublisher': None}
        body = f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>New train announcement</title><link rel="self" href="https://evil.test/self"/><link rel="alternate" href="{URL}"/><published>2026-10-29T16:00:00Z</published><updated>2026-11-20T00:00:00Z</updated></entry></feed>'.encode()
        self.assertEqual(c.parse_source(body, source)[0]['sourceListedDate'], '2026-10-30')
        self.assertIsNone(c.parse_source(body.replace(b'published', b'ignored'), source)[0]['sourceListedDate'])

    def test_bad_or_timezone_free_date_does_not_use_discovery_time(self):
        for value in ('', 'yesterday', '2026-02-30', '2026-10-29T12:00:00'):
            self.assertIsNone(c.parse_source(rss1(date=value), FEED)[0]['sourceListedDate'])

    def test_html_challenge_and_malformed_feed_are_not_empty_success(self):
        for body in (b'<html><title>Access denied</title></html>', b'<rss>broken'):
            with self.assertRaises((ValueError, c.ET.ParseError)):
                c.parse_source(body, FEED)

    def test_jr_date_is_scoped_to_same_list_item(self):
        body = '''<ul><li><p class="date">2026年10月29日</p><a href="/press/2026/a.pdf">新型列車の運行開始を発表します</a></li>
          <li><a href="/press/2026/20261030_b.pdf">こちらには掲載日がありません</a></li>
          <li><p class="date">2026年99月99日</p><a href="/press/2026/c.pdf">日付が不正なプレスリリースです</a></li></ul>'''.encode()
        items = c.parse_source(body, SOURCES[0])
        self.assertEqual([i['sourceListedDate'] for i in items], ['2026-10-29', None, None])
        self.assertTrue(all(i['sourcePublishedAt'] is None for i in items))

    def test_old_feed_items_are_not_new_announcements(self):
        item = c.parse_source(rss1(date='2026-08-20'), FEED)[0]
        result = e.prepare(self.queue([item]), [], NOW)
        self.assertFalse(result['worklist'])
        self.assertIn('rediscovery', result['held'][0]['reason'])

    def test_future_feed_date_is_held(self):
        item = c.parse_source(rss1(date='2026-11-20'), FEED)[0]
        result = e.prepare(self.queue([item]), [], NOW)
        self.assertFalse(result['worklist'])
        self.assertIn('future-listed', result['held'][0]['reason'])

    def test_rss_discovery_is_deduplicated_by_url_and_title(self):
        item = c.parse_source(rss1(), FEED)[0]
        first = c.merge([], [item], AT)
        second = c.merge(first, [item, {**item, 'id': 'other', 'url': URL+'?version=2'}], AT)
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]['firstSeenAt'], AT)
        self.assertIn(URL+'?version=2', second[0]['alternateUrls'])

    def test_healthy_alternate_preserves_actual_collection_evidence(self):
        item = c.parse_source(rss1(), FEED)[0]
        old = {**item, 'id': 'original', 'sourceId': 'jr-east', 'url': 'https://www.jreast.co.jp/press/2026/a.pdf'}
        previous = c.merge([], [old], (NOW-dt.timedelta(days=1)).isoformat())
        merged = c.merge(previous, [item], AT)
        q = self.queue([])
        q['candidates'] = merged
        q['sources'].append({'sourceId': 'jr-east', 'status': 'failed', 'httpStatus': 403})
        result = e.prepare(q, [], NOW)
        self.assertEqual(result['health']['status'], 'degraded')
        self.assertEqual(len(result['worklist']), 1)
        self.assertEqual(result['worklist'][0]['collectionEvidence'][0]['url'], URL)
        self.assertEqual(merged[0]['firstSeenAt'], previous[0]['firstSeenAt'])

    def test_old_alternate_does_not_refresh_a_failed_source(self):
        item = c.parse_source(rss1(), FEED)[0]
        q = self.queue([item])
        q['candidates'][0]['lastSeenAt'] = AT
        q['candidates'][0]['sourceObservations'][0]['lastSeenAt'] = (NOW-dt.timedelta(days=1)).isoformat()
        result = e.prepare(q, [], NOW)
        self.assertFalse(result['worklist'])
        self.assertEqual(len(result['held']), 1)

    def test_published_rss_url_remains_already_covered(self):
        item = c.parse_source(rss1(), FEED)[0]
        result = e.prepare(self.queue([item]), [{'id': 'published', 'sources': [{'url': URL}]}], NOW)
        self.assertFalse(result['worklist'])
        self.assertEqual(result['alreadyCovered'][0]['articleIds'], ['published'])

    def run_collector(self, mode):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d);(root/'content').mkdir()
            source = {**FEED, 'id': 'healthy'}
            (root/'content/sources.json').write_text(json.dumps([SOURCES[0], source]))
            (root/'content/articles.json').write_text(json.dumps([{'sources': [{'url': 'https://www.jreast.co.jp/press/2026/a.pdf'}]}]))
            previous = root/'previous.json'
            old = c.merge([], [{**c.parse_source(rss1(), FEED)[0], 'id': 'kept', 'sourceId': 'jr-east', 'url': 'https://www.jreast.co.jp/press/2026/old.pdf'}], '2026-10-20T00:00:00+00:00')
            previous.write_text(json.dumps({'sourceMonitors': [{'url': 'https://www.jreast.co.jp/press/2026/a.pdf', 'sha256': 'keep-last-success'}], 'candidates': old}))
            def fetch(url, host):
                if host == 'www.jreast.co.jp' or mode == 'all-fail':
                    raise HTTPError(url, 403, 'Forbidden', None, None)
                body = rss1()
                if mode == 'empty':
                    start, end = body.index(b'<item>'), body.index(b'</item>')+len(b'</item>')
                    body = body[:start]+body[end:]
                return body, 200
            with patch.object(c, 'ROOT', root), patch.object(c, 'fetch', side_effect=fetch), patch.object(c.time, 'sleep'), patch('sys.stdout', new_callable=io.StringIO):
                code = c.run(root/'queue.json', previous)
            return code, json.loads((root/'queue.json').read_text())

    def test_partial_http_failure_is_saved_with_nonzero_health(self):
        code, q = self.run_collector('partial')
        self.assertEqual(code, 1)
        self.assertEqual(q['health']['status'], 'degraded')
        self.assertEqual(q['sources'][0]['httpStatus'], 403)
        self.assertEqual(q['sourceMonitors'][0]['sha256'], 'keep-last-success')
        self.assertIsNone(q['sourceMonitors'][0]['changed'])
        self.assertTrue(q['candidates'])

    def test_all_failure_still_writes_explicit_unavailable_queue(self):
        code, q = self.run_collector('all-fail')
        self.assertEqual(code, 2)
        self.assertEqual(q['health']['status'], 'unavailable')
        self.assertTrue(all(s['status'] == 'failed' for s in q['sources']))
        self.assertEqual(q['candidates'][0]['id'], 'kept')
        self.assertEqual(q['candidates'][0]['lastSeenAt'], '2026-10-20T00:00:00+00:00')

    def test_empty_or_wrong_feed_is_unavailable_not_no_news(self):
        code, q = self.run_collector('empty')
        self.assertEqual(code, 2)
        self.assertEqual(q['health']['sourcesOk'], 0)
        self.assertEqual(q['sources'][1]['status'], 200)
        self.assertIn('not proof of no news', q['sources'][1]['parserWarning'])

    def test_report_fails_degraded_after_candidates_saved_and_separates_publication(self):
        code, q = self.run_collector('partial')
        editorial = e.prepare(q, [], dt.datetime.fromisoformat(q['collectedAt']))
        text, exit_code = reporter.report(q, editorial, code)
        self.assertEqual(exit_code, 1)
        self.assertIn('degraded', text)
        self.assertIn('Articles published by this workflow: **0**', text)
        self.assertIn('NOT no-news', text)

    def test_report_only_succeeds_for_healthy_pipeline(self):
        q = self.queue(c.parse_source(rss1(), FEED))
        editorial = e.prepare(q, [], NOW)
        self.assertEqual(reporter.report(q, editorial, 0)[1], 0)
        self.assertEqual(reporter.report(q, editorial, 2)[1], 1)


if __name__ == '__main__':
    unittest.main()
