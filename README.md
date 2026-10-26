# トピしるべ

旅と暮らしの、使えるニュース。F計画SPの新規メディア（初期公開・検証段階）。

- 公開先（設定予定）：https://morry1992.github.io/f-sp-topishirube/
- 本公開の希望先：Cloudflare Pages 無料枠（本人認証待ち）
- 追加の有料API / 外部AI課金 / Firecrawl / ドメイン購入：不使用
- 初期記事：3件。一次資料の本文照合と実用メモを追加。

## 開発

Node 20以上とPython 3の標準機能のみ。依存パッケージのインストール不要。

```
npm test
npm run build
python scripts/check_links.py
```

公開HTMLは `docs/`。Cloudflare Pagesならビルド `npm run build`、出力 `docs`、環境変数 `SITE_URL=https://実際のプロジェクト.pages.dev/`。URL確定後にcontent/site.jsonも更新し、全ページのcanonicalを一致させる。GitHub Pagesの暫定公開は main /docs を選択。収益用本番はCloudflareを優先し、移行後の重複公開を避ける。

## 記事の更新

`content/articles.json` に記事データと出典・確認日時を保存。reviewのfacts/value/rights/policyをすべて確認しstatusをreviewedにした記事のみビルド可能。レビューの真偽をコードが自動で判定するわけではない。本文を検証する編集工程は必須。

誤記はcorrectionsに旧内容・変更理由・根拠URL・日時を残し、updatedAtを更新。過去のpublishedAtを書き換えない。ソース更新と訂正を区別する。

## 収集と運営

- GitHub Actions `Official news radar`：3時間ごと、標準ubuntu-latest、公開リポジトリのみ。
- `data` ブランチ `queue.json`：見出し候補・URL・取得日時・仮SABCD判定・公式資料変更監視。公開ページに流用しない。
- `main` は検証済み記事だけ。収集だけのコミットはmainを更新しないのでPagesビルドを消費しない。
- 最大8取得元、各100候補、キュー500件、監視元8件、各6MB・25秒まで。
- 失敗は取得不能として記録。取得不能をニュースなしと表示しない。
- 外部LLMなしでActionsが行うのは収集・ルール分類・重複整理・候補準備まで。
- ChatGPT Work定期実行が記事本文の確認・実用情報作成・再検証・公開作業を担当。実行環境・接続・利用枠に依存し、常駐・即時・無制限を保証しない。
- 公開画像3点は契約内の画像生成で作成し、WebPへ圧縮。毎回の無人画像生成は未保証。追加記事では内容に合う汎用素材を表示注記付きで再利用できる。

## 未完了と限界

商標類似調査、Cloudflare本番接続、非公開問い合わせ窓口、Search Console、実アクセス計測、AdSense登録・申請、長期間の自動更新耐久試験は未完了。GitHub公開窓口は設置済みだが私的情報の受付には使わない。初期3記事だけで広告申請準備完了とは扱わない。

詳細：`ops/OPERATIONS.md` / `ops/REVIEW_20261026.md`
