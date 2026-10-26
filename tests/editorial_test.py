import datetime as dt
import importlib.util
import json
import copy
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


class EditorialRegressionTests(unittest.TestCase):
    queue = EditorialTests.queue
    def article(self, **changes):
        return {'id': 'train', 'title': '嵯峨野の新型トロッコ、予約と料金',
                'announcedAt': '2026-10-23',
                'points': ['新型トロッコ列車の運行開始は2027年3月1日'],
                'sources': [{'url': 'https://official.test/releases/train.pdf'}], **changes}

    def classify(self, title, articles=None, **fields):
        q = self.queue()
        q['candidates'][0].update(title=title, **fields)
        return e.prepare(q, articles or [], NOW)

    def test_real_five_candidates_reclassify_without_mutating_inputs(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/editorial-20261026.json').read_text())
        q, a = fixture['queue'], fixture['articles']
        before = copy.deepcopy((q, a))
        r = e.prepare(q, a, e.stamp(fixture['comparisonAt']))
        self.assertEqual(r['counts'], {'candidates': 5, 'actionable': 2, 'alreadyCovered': 0, 'updateCandidates': 1, 'held': 2})
        update = r['updateCandidates'][0]
        self.assertEqual(update['articleIds'], ['sagano-new-train-202703'])
        self.assertEqual(update['matchEvidence'][0]['basis'], 'same-official-host-and-topic')
        self.assertIn('update-existing', update['action'])
        self.assertEqual({i['relevance']['targetEndDate'] for i in r['held']}, {'2026-10-23', '2026-10-24'})
        self.assertEqual(r['health']['status'], 'degraded')
        self.assertEqual(len(r['health']['monitorFailures']), 3)
        self.assertEqual((q, a), before)

    def test_same_topic_new_url_later_reservation_news_is_update(self):
        r = self.classify('2026/10/26 新型トロッコ列車の予約と料金の追加発表', [self.article()], sourceListedDate='2026-10-26')
        self.assertEqual(len(r['updateCandidates']), 1)
        self.assertFalse(r['worklist'])
        self.assertIn('newer-announcement-hint', r['updateCandidates'][0]['updateSignals'])

    def test_same_url_newer_announcement_is_not_suppressed(self):
        r = self.classify('続報 予約開始', [self.article()], url='https://official.test/releases/train.pdf', sourcePublishedAt='2026-10-26')
        self.assertEqual(len(r['updateCandidates']), 1)
        self.assertFalse(r['alreadyCovered'])

    def test_same_url_in_place_changed_source_becomes_update(self):
        q = self.queue()
        q['candidates'][0]['url'] = 'https://official.test/releases/train.pdf'
        q['sourceMonitors'] = [{'url': q['candidates'][0]['url'], 'status': 200, 'changed': True}]
        r = e.prepare(q, [self.article()], NOW)
        self.assertEqual(len(r['updateCandidates']), 1)
        self.assertIn('source-hash-change-needs-body-comparison', r['updateCandidates'][0]['updateSignals'])
        self.assertFalse(r['updateCandidates'][0]['bodyVerified'])

    def test_exact_match_without_change_still_requires_comparison(self):
        r = self.classify('新型列車', [self.article()], url='https://official.test/releases/train.pdf')
        self.assertEqual(len(r['alreadyCovered']), 1)
        self.assertIn('update-existing', r['alreadyCovered'][0]['action'])
        self.assertFalse(r['alreadyCovered'][0]['autoPublish'])

    def test_unrelated_news_on_same_official_host_stays_new(self):
        for title in ['京都の御朱印と仁和寺の地域連携セット券の発売', 'EF66機関車の運転台でジオラマ体験', '他線区の新型通勤列車を導入']:
            with self.subTest(title=title):
                r = self.classify(title, [self.article()])
                self.assertEqual(len(r['worklist']), 1)
                self.assertFalse(r['updateCandidates'])

    def test_identical_topic_on_different_official_host_stays_new(self):
        r = self.classify('新型トロッコ列車の運行開始と予約料金', [self.article()], url='https://other.test/notice')
        self.assertEqual(len(r['worklist']), 1)

    def test_url_tracking_and_encoded_pdf_normalize(self):
        a = self.article(sources=[{'url': 'https://official.test/日本.pdf'}])
        r = self.classify('新型列車', [a], url='https://OFFICIAL.test/%E6%97%A5%E6%9C%AC.pdf?utm_source=x#page=1')
        self.assertEqual(r['alreadyCovered'][0]['articleIds'], ['train'])

    def test_past_cancellation_and_service_notice_leave_breaking_queue(self):
        for title, end in [('2026/10/23 10月23日(金) 列車の運休について', '2026-10-23'),
                           ('2026/10/23 10月24日(土)の運転について', '2026-10-24')]:
            with self.subTest(title=title):
                r = self.classify(title, sourceListedDate='2026-10-23', priority='S')
                self.assertFalse(r['worklist'])
                self.assertEqual(r['held'][0]['relevance']['targetEndDate'], end)
                self.assertEqual(r['held'][0]['operationalStatus'], 'unknown')
                self.assertIn('not proof of recovery', r['held'][0]['reason'])

    def test_target_today_or_future_remains_reviewable(self):
        for title in ['2026年10月26日 列車の運休', '2026-10-27 列車の運休', '10月27日 列車の運休']:
            with self.subTest(title=title):
                r = self.classify(title, sourceListedDate='2026-10-23', priority='S')
                self.assertEqual(len(r['worklist']), 1)
                self.assertEqual(r['worklist'][0]['relevance']['status'], 'dated-target-hint')
                self.assertFalse(r['worklist'][0]['bodyVerified'])

    def test_explicit_full_date_does_not_need_announcement_year(self):
        r = self.classify('2026年10月23日 列車の運休')
        self.assertEqual(r['held'][0]['relevance']['status'], 'past-target-hint')

    def test_announcement_listing_date_is_never_target_or_discovery_date(self):
        r = self.classify('2026/10/23 列車の運休について', sourceListedDate='2026-10-23')
        entry = r['held'][0]
        self.assertEqual(entry['relevance']['status'], 'unknown-target')
        self.assertIsNone(entry['relevance']['targetEndDate'])
        self.assertIsNone(entry['announcementDate'])
        self.assertEqual(entry['announcementDateStatus'], 'unknown')
        self.assertEqual(entry['sourceListedDate'], '2026-10-23')
        self.assertEqual(entry['lastSeenAt'], AT)

    def test_unanchored_yearless_target_cannot_use_acquisition_year(self):
        r = self.classify('10月23日 列車の運休')
        self.assertEqual(r['held'][0]['relevance']['status'], 'unknown-target')

    def test_explicit_range_uses_end_not_first_date(self):
        for title in ['10月23日〜10月27日 列車の運休', '10月23日から27日まで列車の運休', '2026年10月23日〜2026年10月27日列車の運休']:
            with self.subTest(title=title):
                r = self.classify(title, sourceListedDate='2026-10-23')
                self.assertEqual(r['worklist'][0]['relevance']['targetEndDate'], '2026-10-27')

    def test_open_ended_recurring_ambiguous_periods_are_held_not_expired(self):
        for title in ['10月23日から列車の運休', '10月23日以降、当面運休',
                      '毎週10月23日を含む土曜日は運休', '10月23日から11月末まで運休',
                      '10月23日〜列車の運休', '10月23日から翌年3月1日まで運休',
                      '10月23日と本日は運休', '運休について', '2026年13月99日運休']:
            with self.subTest(title=title):
                r = self.classify(title, sourceListedDate='2026-10-23', priority='S')
                self.assertFalse(r['worklist'])
                self.assertNotEqual(r['held'][0]['relevance']['status'], 'past-target-hint')
                self.assertEqual(r['held'][0]['operationalStatus'], 'unknown')

    def test_jst_day_boundary_and_year_rollover(self):
        q = self.queue()
        q['candidates'][0].update(title='2026年10月26日 列車の運休')
        for now, bucket in [(dt.datetime(2026, 10, 26, 14, 59, tzinfo=dt.timezone.utc), 'worklist'),
                            (dt.datetime(2026, 10, 26, 15, 0, tzinfo=dt.timezone.utc), 'held')]:
            q['collectedAt'] = q['candidates'][0]['lastSeenAt'] = now.isoformat()
            self.assertEqual(len(e.prepare(q, [], now)[bucket]), 1)
        q['candidates'][0].update(title='1月1日 列車の運休', sourceListedDate='2026-12-31')
        now = dt.datetime(2026, 12, 31, 9, tzinfo=dt.timezone.utc)
        q['collectedAt'] = q['candidates'][0]['lastSeenAt'] = now.isoformat()
        self.assertEqual(e.prepare(q, [], now)['worklist'][0]['relevance']['targetEndDate'], '2027-01-01')

    def test_past_announcement_does_not_expire_future_train_launch(self):
        r = self.classify('2026/10/23 新型列車を2027年3月1日から運行開始', sourceListedDate='2026-10-23')
        self.assertEqual(len(r['worklist']), 1)
        self.assertEqual(r['worklist'][0]['relevance']['status'], 'not-short-lived')

    def test_matched_duplicate_from_failed_source_is_still_unavailable(self):
        q = self.queue()
        q['sources'][0]['status'] = 'failed'
        q['candidates'][0]['url'] = 'https://official.test/releases/train.pdf'
        r = e.prepare(q, [self.article()], NOW)
        self.assertEqual(r['health']['status'], 'unavailable')
        self.assertFalse(r['alreadyCovered'])
        self.assertEqual(r['held'][0]['articleIds'], ['train'])
        self.assertEqual(r['held'][0]['operationalStatus'], 'unknown')

    def test_no_candidates_is_not_proof_of_healthy_sources(self):
        q = self.queue()
        q.update(candidates=[])
        q['sources'][0].update(candidateCount=0, parserWarning='NO_MATCHES')
        r = e.prepare(q, [], NOW)
        self.assertEqual(r['counts']['candidates'], 0)
        self.assertEqual(r['health']['status'], 'unavailable')

    def test_unknown_priority_never_enters_new_worklist(self):
        self.assertEqual(len(self.classify('新型列車', priority=None)['held']), 1)


if __name__ == '__main__':
    unittest.main()
