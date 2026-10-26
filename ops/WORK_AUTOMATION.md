# Work定期編集：登録待ち

作成試行：2026-10-26 JST
結果：too_many_active_automations / current_count15 / plan_limit15。
既存の定期タスクは停止・変更していない。

候補のスケジュール：Asia/Tokyoの朝・午後・夜（8時・14時・20時頃）。この頻度は初期運用案であり、登録済みではない。

## 実行内容

GitHub MORRY1992/f-sp-topishirube の最新README、ops/OPERATIONS.md、ops/REVIEW_20261026.md、content/site.jsonを読む。
data/queue.jsonの取得状況・候補・更新監視を読み、S/A優先で一次資料本文を確認して最大1記事を作成するか既存記事を更新。日付・対象・価格条件・例外を照合し、実用情報を加える。すべてのreview項目を実際に満たすものだけ公開。npm test・build・check_linksで検証し生成済みdocsもmainに反映する。画像は適切な既存素材をAI生成表示付きで再利用。掲載不能なら保留。

通常の無料範囲の調査・開発・検証・公開はユーザー承認済み。費用発生、追加API、Firecrawlクレジット、有料ドメインは禁止。他F計画サイト変更は禁止。取得不能をニュースなしとせず、未公開を公開済みとしない。記事の単純転載・虚偽体験・推測の断定を避ける。

Workの利用可能な枠・接続・権限に依存するため、完全無人・常駐・即時の保証はしない。
