import datetime as dt
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('editorial', Path(__file__).resolve().parents[1]/'scripts/editorial_queue.py')
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
NOW = dt.datetime(2026, 10, 26, 9, tzinfo=dt.timezone.utc)
AT = NOW.isoformat()


class EditorialTests(unittest.TestCase):
    def queue(self):
        return {'collectedAt': AT, 'sources': [{'sourceId': 'official', 'status': 200, 'candidateCount': 1}], 'candidates': [{'id': 'a', 'title': '新型列車', 'url': 'https://official.test/a', 'sourceId': 'official', 'priority': 'A', 'firstSeenAt': AT, 'lastSeenAt': AT}], 'sourceMonitors': []}

    def test_stale_discovery_cannot_be_presented_as_fresh_news(self):
        q = self.queue()
        r = e.prepare(q, [], NOW+dt.timedelta(hours=7))
        self.assertEqual(r['health']['status'], 'stale')
        self.assertFalse(r['worklist'])
        self.assertEqual(len(r['held']), 1)

    def test_partial_failure_is_explicit_and_failed_source_is_held(self):
        q = self.queue()
        q['sources'].append({'sourceId': 'blocked', 'status': 'failed', 'error': '403'})
        q['candidates'].append({**q['candidates'][0], 'id': 'b', 'sourceId': 'blocked', 'url': 'https://blocked.test/b'})
        r = e.prepare(q, [], NOW)
        self.assertEqual(r['health']['status'], 'degraded')
        self.assertEqual(len(r['worklist']), 1)
        self.assertEqual(len(r['held']), 1)

    def test_existing_source_and_alternate_url_do_not_create_duplicate_article(self):
        q = self.queue()
        q['candidates'][0]['alternateUrls'] = ['https://official.test/press/']
        articles = [{'id': 'published', 'sources': [{'url': 'https://official.test/press'}]}]
        r = e.prepare(q, articles, NOW)
        self.assertFalse(r['worklist'])
        self.assertEqual(r['alreadyCovered'][0]['articleIds'], ['published'])

    def test_changed_source_is_review_only_and_dates_are_not_invented(self):
        q = self.queue()
        q['sourceMonitors'] = [{'url': 'https://official.test/a', 'status': 200, 'changed': True}]
        r = e.prepare(q, [], NOW)
        self.assertEqual(r['worklist'][0]['dateStatus'], 'unknown')
        self.assertFalse(r['worklist'][0]['autoPublish'])
        self.assertFalse(r['worklist'][0]['bodyVerified'])
        self.assertIn('not-proof-of-error', r['sourceChanges'][0]['action'])

    def test_empty_listing_and_future_clock_are_not_healthy(self):
        q = self.queue()
        q['sources'][0]['candidateCount'] = 0
        self.assertEqual(e.prepare(q, [], NOW)['health']['status'], 'unavailable')
        self.assertEqual(e.prepare(self.queue(), [], NOW-dt.timedelta(hours=2))['health']['status'], 'stale')

    def test_failed_monitor_prevents_healthy_status(self):
        q = self.queue()
        q['sourceMonitors'] = [{'url': 'https://official.test/a', 'status': 'failed'}]
        r = e.prepare(q, [], NOW)
        self.assertEqual(r['health']['status'], 'degraded')
        self.assertEqual(len(r['health']['monitorFailures']), 1)


if __name__ == '__main__':
    unittest.main()
