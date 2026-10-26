# 運営手順と料金境界

確認基準日：2026-10-26（日本時間）

## 費用

- 公開GitHubリポジトリの標準GitHub-hosted runnerは無料。大型runner、privateでの実行、キャッシュ・artifactの追加保存は使わない。
  https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions
- Pages Freeは月500ビルド・同時1ビルド・20分timeout。既存サイトとの共有利用に注意。収集はdataブランチ、公開はmainと分離。既存アカウントの実残量・契約プランは未確認。アップグレード・有料Functions・R2・KV・D1を追加しない。
  https://developers.cloudflare.com/pages/platform/limits/
- GitHub Pagesは公開リポジトリで無料。サイト1GB、帯域100GB/月等のsoft limitあり。現時点では広告未設置の試験・開発公開。収益用本番はCloudflareに移す。
  https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
  https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies
- ChatGPT Workの定期実行はプラグイン利用が可能だが、実際の接続・権限・プラン制限に依存。課金APIの代替としてGitHub Actions上でChatGPTを呼ぶ設計にはしない。
  https://learn.chatgpt.com/docs/automations
- Firecrawlクレジット、外部画像生成サービス、ChatGPT API、有料ドメインは不使用。

## 日次編集手順

1. GitHub data/queue.jsonを読み、取得成功数と最終取得日時を確認。古い候補は速報としない。
2. S→A→Bの順に公式原文を読む。発表日時、対象、利用日、料金の算定基準、例外、取消・変更を確認。
3. 同一事象の既存記事を探し、重複新規記事ではなく必要に応じて更新。出典更新検知はレビューの契機であり自動訂正しない。
4. 事実と実用メモを分け、出典・確認日時・未確認事項を記録。既存記事の言い換えは行わない。
5. 画像は内容に合う汎用イメージを選ぶ。実在施設・商品そのものと誤認する場合は使わない。AI生成注記と代替テキストを必須にする。
6. review各項目を実際に確認してから公開可にする。ビルド・リンク・検索・保存を検証。新規記事・画像にはブラウザ表示を確認。
7. mainへ公開。新規候補だけでmainにコミットしない。Cloudflare利用は1日2〜3公開バッチ程度から開始し、同一アカウントの消費を観測して調整。
8. 記事を増やせなければ、未確認情報で埋めない。取得障害と編集保留を報告。

## 品質判定

A. 出典本文と数字・日付が一致し、原文の制約を省いて誤認を招いていない。
B. 読者が対象・行動・注意点を判断できる。推測と公式発表を分ける。
C. 画像の権利とAI表示が明確。事故・人物の記録写真と誤認させない。
D. 無価値な量産、転載、誤解を招く広告、虚偽の体験談を避ける。

## AdSenseへ進む前の残作業

本番URL公開、実機確認、継続更新、商標類似調査、非公開の問い合わせ窓口、Search Console登録・サイトマップ送信、計測の方針とプライバシー更新、広告利用に必要な本人アカウントの確認。記事数や経過日数に根拠のない「合格基準」を設けない。
Google公式：https://support.google.com/adsense/answer/9724?hl=ja
Google Publisher Policies：https://support.google.com/publisherpolicies/answer/10502938?hl=ja

## 担当の境界

静的収集は3時間間隔の予定であり24時間の即時速報を保証しない。定期実行の遅延・GitHubの自動停止・取得元変更・Work利用枠切れ等を監視。停止時には最終成功を記録し未更新と扱う。他F計画サイトの設定・稼働・広告を変更しない。
