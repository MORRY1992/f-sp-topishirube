import datetime as dt
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('editorial_regression', ROOT/'scripts/editorial_queue.py')
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)
NOW = dt.datetime(2026, 10, 27, 16, tzinfo=dt.timezone.utc)  # Oct 28 in Japan
INDEX = json.loads((ROOT/'content/topic-index.json').read_text())
TOPIC = INDEX['topics'][0]
ARTICLES = [{'id': 'sagano-new-train-202703', 'sources': [{'url': TOPIC['sourceUrls'][1]}]}]


class EditorialRegressionTests(unittest.TestCase):
    def queue(self, title=None, url=None, now=NOW, listed='2026-10-23'):
        at = now.isoformat()
        return {
            'collectedAt': at,
            'sources': [{'sourceId': 'sagano', 'status': 200, 'candidateCount': 1}],
            'candidates': [{
                'id': 'candidate', 'sourceId': 'sagano', 'priority': 'S',
                'title': title or TOPIC['listingTitle'],
                'url': url or TOPIC['sourceUrls'][0],
                'sourceListedDate': listed, 'firstSeenAt': at, 'lastSeenAt': at,
            }],
        }

    def result(self, q, now=NOW, articles=ARTICLES, topics=INDEX):
        return e.prepare(q, articles, now, topic_index=topics)

    def test_real_sagano_listing_and_published_pdf_are_one_topic(self):
        result = self.result(self.queue())
        self.assertEqual(result['counts'], {'candidates': 1, 'actionable': 0, 'alreadyCovered': 1, 'updateCandidates': 0, 'held': 0})
        self.assertEqual(result['alreadyCovered'][0]['articleIds'], ['sagano-new-train-202703'])

    def test_tracking_and_fragment_do_not_hide_known_alias(self):
        result = self.result(self.queue(url=TOPIC['sourceUrls'][0]+'?utm_source=radar#body'))
        self.assertEqual(len(result['alreadyCovered']), 1)

    def test_meaningful_query_is_not_removed_as_tracking(self):
        result = self.result(self.queue(url=TOPIC['sourceUrls'][0]+'?edition=2'))
        self.assertEqual(len(result['worklist']), 1)
        self.assertFalse(result['alreadyCovered'])

    def test_changed_booking_conditions_on_same_url_require_update_review(self):
        result = self.result(self.queue(title='2026/10/28 新型トロッコの予約条件変更について', listed='2026-10-28'))
        item = result['updateCandidates'][0]
        self.assertEqual(item['action'], 'compare-official-body-and-update-existing-if-material')
        self.assertTrue(item['updateReviewRequired'])
        self.assertEqual(item['articleIds'], ['sagano-new-train-202703'])
        self.assertFalse(item['autoPublish'])
        self.assertFalse(item['bodyVerified'])
        self.assertFalse(result['alreadyCovered'])

    def test_new_listing_date_with_same_wording_also_requires_review(self):
        q = self.queue(listed='2026-10-28')
        self.assertEqual(self.result(q)['updateCandidates'][0]['action'], 'compare-official-body-and-update-existing-if-material')

    def test_new_url_is_not_suppressed_by_similar_title(self):
        result = self.result(self.queue(url='https://www.sagano-kanko.co.jp/news/6000/'))
        self.assertEqual(len(result['worklist']), 1)
        self.assertIn('duplicate-topic', result['worklist'][0]['requiredChecks'])

    def test_mapping_to_nonexistent_article_cannot_suppress_candidate(self):
        result = self.result(self.queue(), articles=[])
        self.assertEqual(len(result['worklist']), 1)

    def test_unreviewed_alias_cannot_suppress_candidate(self):
        result = self.result(self.queue(), topics={'topics': [{**TOPIC, 'reviewedAt': None}]})
        self.assertEqual(len(result['worklist']), 1)

    def test_past_one_day_cancellation_is_held_not_urgent_work(self):
        q = self.queue(title='2026/10/23 10月23日(金) 列車の運休について',
                       url='https://www.sagano-kanko.co.jp/news/5590/')
        result = self.result(q)
        self.assertFalse(result['worklist'])
        item = result['held'][0]
        self.assertEqual(item['eventDateHint'], '2026-10-23')
        self.assertEqual(item['eventDateStatus'], 'title-hint-only')
        self.assertIn('not proof', item['reason'])
        self.assertFalse(item['bodyVerified'])
        self.assertFalse(item['autoPublish'])

    def test_service_day_uses_japan_date_at_midnight_not_utc(self):
        q = self.queue(title='2026/10/27 10月27日(火)の運転について',
                       url='https://www.sagano-kanko.co.jp/news/5600/', listed='2026-10-27')
        self.assertEqual(len(self.result(q)['held']), 1)

    def test_todays_notice_remains_for_editorial_review(self):
        q = self.queue(title='2026/10/28 10月28日(水)の運転について',
                       url='https://www.sagano-kanko.co.jp/news/5601/', listed='2026-10-28')
        self.assertEqual(len(self.result(q)['worklist']), 1)

    def test_future_notice_is_not_archived(self):
        q = self.queue(title='2026/10/28 10月29日(木)の運休について',
                       url='https://www.sagano-kanko.co.jp/news/5602/', listed='2026-10-28')
        self.assertEqual(len(self.result(q)['worklist']), 1)

    def test_ongoing_disruption_is_not_treated_as_one_day_expiry(self):
        for phrase in ['10月23日から当面の間、運転見合わせ', '10月23日以降の長期間運休について']:
            q = self.queue(title='2026/10/23 '+phrase, url='https://www.sagano-kanko.co.jp/news/5603/')
            result = self.result(q)
            # Indefinite disruptions are not expired: current status remains unverified.
            self.assertFalse(result['worklist'])
            self.assertEqual(result['held'][0]['relevance']['status'],
                             'open-or-recurring-target')
            self.assertEqual(result['held'][0]['operationalStatus'], 'unknown')

    def test_december_listing_of_january_service_uses_next_year_hint(self):
        now = dt.datetime(2026, 12, 31, 14, tzinfo=dt.timezone.utc)
        q = self.queue(title='2026/12/31 1月1日(金)の運転について',
                       url='https://www.sagano-kanko.co.jp/news/5604/', listed='2026-12-31', now=now)
        item = self.result(q, now=now)['worklist'][0]
        self.assertEqual(item['eventDateHint'], '2027-01-01')

    def test_stale_update_and_failed_source_stay_held(self):
        q = self.queue(title='2026/10/28 新型トロッコ予約条件の変更', listed='2026-10-28')
        q['sources'][0]['status'] = 'failed'
        result = self.result(q)
        self.assertFalse(result['worklist'])
        self.assertTrue(result['held'][0]['updateReviewRequired'])
        self.assertEqual(result['health']['status'], 'unavailable')

    def test_changed_alias_monitor_points_to_existing_article(self):
        q = self.queue()
        q['sourceMonitors'] = [{'url': TOPIC['sourceUrls'][0], 'status': 200, 'changed': True}]
        result = self.result(q)
        self.assertEqual(result['sourceChanges'][0]['articleIds'], ['sagano-new-train-202703'])
        self.assertIn('not-proof-of-error', result['sourceChanges'][0]['action'])


if __name__ == '__main__':
    unittest.main()
