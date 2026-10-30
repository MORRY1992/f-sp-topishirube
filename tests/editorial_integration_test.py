"""Focused PR#3 + PR#4 integration regression tests (no network)."""
import datetime as dt
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'editorial', Path(__file__).resolve().parents[1] / 'scripts/editorial_queue.py')
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
NOW = dt.datetime(2026, 10, 30, 8, tzinfo=dt.timezone.utc)
AT = NOW.isoformat()
OFFICIAL = 'https://official.test'
PDF = OFFICIAL + '/releases/train.pdf'
PAGE = OFFICIAL + '/news/train'
RSS_URL = 'https://news.test/train'


class IntegrationRegressionTests(unittest.TestCase):
    def queue(self, title='新型列車', **fields):
        item = {'id': 'news', 'title': title, 'url': PAGE, 'sourceId': 'main',
                'priority': 'A', 'firstSeenAt': AT, 'lastSeenAt': AT}
        item.update(fields)
        return {'collectedAt': AT, 'sources': [
            {'sourceId': 'main', 'status': 200, 'candidateCount': 1}],
            'candidates': [item], 'sourceMonitors': []}

    def article(self):
        return {'id': 'train', 'title': '新型列車導入について',
                'sources': [{'url': PDF}]}

    def index(self, reviewed=True):
        topic = {'articleIds': ['train'], 'sourceUrls': [PDF, PAGE],
                 'listingTitle': '2026/10/30 新型列車導入について',
                 'sourceListedDate': '2026-10-30'}
        if reviewed:
            topic['reviewedAt'] = '2026-10-30T04:00:00+00:00'
        return {'topics': [topic]}

    def test_verified_alias_same_news_different_url_is_not_new(self):
        q = self.queue('2026/10/30 新型列車導入について',
                       sourceListedDate='2026-10-30')
        r = e.prepare(q, [self.article()], NOW, self.index())
        self.assertFalse(r['worklist'])
        self.assertEqual(r['alreadyCovered'][0]['articleIds'], ['train'])
        self.assertEqual(r['alreadyCovered'][0]['matchEvidence'][0]['basis'],
                         'reviewed-alias-url')
        self.assertFalse(r['alreadyCovered'][0]['autoPublish'])

    def test_reviewed_alias_changed_title_routes_to_update(self):
        q = self.queue('2026/10/30 続報 新型列車導入について',
                       sourceListedDate='2026-10-30')
        r = e.prepare(q, [self.article()], NOW, self.index())
        self.assertEqual(len(r['updateCandidates']), 1)
        self.assertFalse(r['worklist'])
        self.assertIn('reviewed-topic-listing-changed',
                      r['updateCandidates'][0]['updateSignals'])

    def test_unreviewed_alias_on_other_host_does_not_suppress(self):
        q = self.queue('別会社の新型列車', url='https://other.test/train')
        index = {'topics': [{'articleIds': ['train'],
                             'sourceUrls': ['https://other.test/train']}]}
        r = e.prepare(q, [self.article()], NOW, index)
        self.assertEqual(len(r['worklist']), 1)

    def test_different_url_same_official_topic_routes_update(self):
        q = self.queue('2026/10/30 新型トロッコ列車の予約と料金の追加発表')
        article = {'id': 'train', 'title': '新型トロッコ列車の予約と料金',
                   'points': ['運行開始は来春'], 'sources': [{'url': PDF}]}
        r = e.prepare(q, [article], NOW)
        self.assertFalse(r['worklist'])
        self.assertEqual(r['updateCandidates'][0]['articleIds'], ['train'])
        self.assertIn('different-url-related-topic-needs-comparison',
                      r['updateCandidates'][0]['updateSignals'])

    def test_jr_403_but_fresh_rss_observation_can_be_reviewed(self):
        q = self.queue(sourceId='main', url=PDF, alternateUrls=[RSS_URL],
                       sourceObservations=[
                           {'sourceId': 'main', 'url': PDF,
                            'lastSeenAt': (NOW-dt.timedelta(days=1)).isoformat()},
                           {'sourceId': 'rss', 'url': RSS_URL, 'lastSeenAt': AT}])
        q['sources'] = [{'sourceId': 'main', 'status': 'failed', 'httpStatus': 403},
                        {'sourceId': 'rss', 'status': 200, 'candidateCount': 1}]
        r = e.prepare(q, [], NOW)
        self.assertEqual(r['health']['status'], 'degraded')
        self.assertEqual(len(r['worklist']), 1)
        self.assertEqual(r['worklist'][0]['collectionEvidence'][0]['sourceId'], 'rss')
        self.assertEqual(len(r['health']['sourceFailures']), 1)

    def test_failed_or_stale_observations_cannot_prove_fresh(self):
        for status in ('failed', 200):
            with self.subTest(status=status):
                q = self.queue(sourceId='main', url=PDF, alternateUrls=[RSS_URL],
                               sourceObservations=[
                                   {'sourceId': 'rss', 'url': RSS_URL,
                                    'lastSeenAt': (NOW-dt.timedelta(hours=8)).isoformat()}])
                q['sources'] = [{'sourceId': 'main', 'status': 'failed', 'httpStatus': 403},
                                {'sourceId': 'rss', 'status': status, 'candidateCount': 1}]
                r = e.prepare(q, [], NOW)
                self.assertFalse(r['worklist'])
                self.assertEqual(len(r['held']), 1)
                self.assertIn('stale-or-unavailable', r['held'][0]['reason'])

    def test_observation_from_unrelated_url_is_not_retrieval_evidence(self):
        q = self.queue(sourceId='main', url=PDF, sourceObservations=[
            {'sourceId': 'rss', 'url': 'https://unrelated.test/notice',
             'lastSeenAt': AT}])
        q['sources'] = [{'sourceId': 'main', 'status': 'failed'},
                        {'sourceId': 'rss', 'status': 200, 'candidateCount': 1}]
        r = e.prepare(q, [], NOW)
        self.assertFalse(r['worklist'])
        self.assertEqual(len(r['held']), 1)

    def test_rss_old_and_future_dates_both_held(self):
        for listed, reason in [('2026-08-01', 'old-listed-item'),
                               ('2026-11-01', 'future-listed-date')]:
            with self.subTest(listed=listed):
                q = self.queue('新型列車のお知らせ', sourceDateBasis='feed-hint',
                               sourceListedDate=listed, maxListedAgeDays=20)
                r = e.prepare(q, [], NOW)
                self.assertFalse(r['worklist'])
                self.assertIn(reason, r['held'][0]['reason'])
                self.assertEqual(r['held'][0]['dateStatus'], 'feed-hint-only')

    def test_past_disruption_is_not_misreported_as_recovered(self):
        q = self.queue('2026年10月29日 列車の運休',
                       sourceListedDate='2026-10-29', priority='S')
        r = e.prepare(q, [], NOW)
        self.assertFalse(r['worklist'])
        self.assertEqual(r['held'][0]['relevance']['status'], 'past-target-hint')
        self.assertEqual(r['held'][0]['operationalStatus'], 'unknown')

    def test_exact_url_followup_not_second_new_article(self):
        q = self.queue('2026/10/30 続報 予約と料金を変更',
                       url=PDF, sourcePublishedAt='2026-10-30')
        r = e.prepare(q, [{**self.article(), 'announcedAt': '2026-10-29'}], NOW)
        self.assertFalse(r['worklist'])
        self.assertEqual(r['updateCandidates'][0]['articleIds'], ['train'])
        self.assertIn('newer-announcement-hint',
                      r['updateCandidates'][0]['updateSignals'])
        self.assertFalse(r['updateCandidates'][0]['bodyVerified'])

    def test_all_sources_failed_means_unavailable_not_no_news(self):
        q = self.queue()
        q['sources'][0] = {'sourceId': 'main', 'status': 'failed', 'httpStatus': 403}
        r = e.prepare(q, [], NOW)
        self.assertEqual(r['health']['status'], 'unavailable')
        self.assertFalse(r['worklist'])
        self.assertTrue(r['health']['sourceFailures'])

    def test_invalid_urls_do_not_count_as_verified_document_identity(self):
        for url in ('http://official.test/release',
                    'https://user:pass@official.test/a',
                    'https://wrong.test:badport/path'):
            with self.subTest(url=url):
                self.assertEqual(e.key(url), '')


if __name__ == '__main__':
    unittest.main()
