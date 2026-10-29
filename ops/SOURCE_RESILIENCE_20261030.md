# 公式ニュース収集の改善（2026年10月30日・日本時間）

## 調査で確認したこと

- 作業開始時の最新data/editorial.jsonは2026-10-29 22:06ごろ（JST）の収集結果。本体一覧とJR東日本の既存出典3件がHTTP 403、healthはdegraded。GitHub Actions自体はsuccessだった。
- 同じ識別User-Agentを使うこの作業環境の通常HTTPアクセスでは、公式一覧・トップページ・robots.txtを200で取得できた。403がすべての接続環境で再現する状態ではない。
- GitHub-hosted runnerに対する拒否条件の詳細は不明。接続元などに依存する制限の可能性はあるが、IP制限やWAFの仕様と断定する証拠はない。User-Agent偽装、プロキシ、CAPTCHA回避、403/429への再試行は導入していない。
- JR東日本ドメイン内の公式ニュースRSSは今回確認できなかった。推測したURLは設定していない。

## 実取得できた補助経路

- https://prtimes.jp/companyrdf.php?company_id=17557
- 配信元確認：https://prtimes.jp/main/html/searchrlp/company_id/17557
- RSSリンク確認：https://prtimes.jp/main/html/rd/p/000001561.000017557.html の会社概要欄「RSS」。会社名と公式サイトへのリンクも照合した。
- HTTP 200、RSS1.0/RDF、200項目を確認。channel titleは「東日本旅客鉄道株式会社【プレスリリース】 by PR TIMES」、各項目のdc:corpも同社。収集上限100件は維持する。
- PR TIMESへの企業自身の配信分に限る。JR東日本本体の地方支社を含む全発表、Suica等の別ページ、既存記事PDFの変更監視を網羅しない。本体の失敗は別のsourceIdで残し、補助RSS成功で隠さない。

## 利用条件と収集範囲

- JR東日本：https://www.jreast.co.jp/site/rules.html/ 、 https://www.jreast.co.jp/robots.txt
- PR TIMES：https://prtimes.jp/main/html/kiyaku 、 https://prtimes.jp/robots.txt
- PR TIMESの報道目的の企業コンテンツ利用と情報受信の条件を確認。一般の公開RSSを低頻度に取得し、見出し・URL・項目日付のヒントだけを編集候補として扱う。description、本文、画像、連絡先、会員限定データは保存しない。記事や素材の利用は従来どおり別途レビューが必要であり、候補の取得を転載・画像利用許可と扱わない。
- 3時間間隔、HTTPS、ホスト・発表URLの許可リスト、各6MB/25秒、最大8情報源/500候補/8監視先は維持。外部APIキー、有料API、外部契約、追加依存パッケージは不要。

## 実装

1. RSS1.0に対応し、既存RSS2.0/Atomを維持。企業別RSSではchannel名、配信企業、企業IDを含む発表URLを検証する。不一致・HTMLの拒否ページ・XML破損を取得障害にする。
2. 項目のdc:date/pubDate/publishedを参考日付として取り込む。channel dateやAtom updated、収集日時、ファイル名から発表日を補完しない。sourcePublishedAtは未確認のまま。タイムゾーン付き項目日付の比較は日本時間。
3. JR東日本HTMLでは同じli内のdate要素を参考日付として関連付ける。次項目への日付流出とURLからの日付推定を防ぐ。
4. URL/見出しの既存重複処理を維持。別情報源で同じ見出しを再取得した場合は、実際の情報源・URL・取得時刻をsourceObservationsに残す。健全な別経路で再確認できた候補と、失敗元の古い候補を区別する。本文・同一事象の判定を自動で確認済みにしない。
5. 過去の一日運行案内、日本時間の日付境界、既報PDF/一覧対応、同URLの条件変更時の更新レビューを維持。企業別RSSの30日超の候補と未来の掲載日は保留する。古い発表の初回取得を新発表と扱わない。
6. 403等のHTTPコードを構造化。失敗時も過去候補と直前成功ハッシュを保持し、変更有無を不明にする。0件はNO_MATCHES警告。healthはok/degraded/unavailableを明示する。
7. dataへの保存後、全経路/出典監視が健全な場合だけ収集Actionを成功にする。分類サマリーに記事公開0件を明記する。dataへ切り替える前に報告スクリプトをRUNNER_TEMPへ退避し、ブランチ切替後も報告できるようにした。

## 検証結果

- Python 50テスト成功（既存30＋追加20）、Node公開制御3テスト成功。
- ビルド成功（既存3記事）、ローカルリンク・画像alt・JSON-LD検査成功。
- 2026-10-30 00:54ごろ（JST）のローカル実収集：本体100件、企業RSS100件、嵯峨野5件を取得。過去キュー込み205候補、編集作業候補40、既報1、保留164。作業リスト表示は既存の上位20件まで、1回の公開上限も従来どおり別工程。
- 同実行では情報源3/3、出典監視4/4が200、health=ok。ただしこれは作業環境での結果で、GitHub-hosted runnerで403が解消した証拠ではない。
- 障害再現テスト：一部403、全件403、200応答だが0件、企業違い、XML破損、監視失敗時のハッシュ保持、失敗時の過去候補保持、鮮度のない別経路を正常扱いしないことを検証。
- 公開記事データ・docs・広告・ANA設定は変更なし。記事の自動公開0件。

## GitHubでの確認

PR #4をmainへ統合済み（45516c2db1e492dd58933a97d62f5fa127cc4f6a）。既存のpushトリガーによる実収集も完了した。3時間間隔の定期実行設定は変更していない。
確認対象はdata/editorial.jsonのhealth、sourceFailures、monitorFailures、分類件数と、Actionsの実行サマリー。
403が継続する場合はdegradedのまま候補を保存し、Actionも失敗表示にする。本体の解消と補助RSSの成功を分けて判断する。

### GitHub-hosted runnerでの実測（2026-10-30 00:58:07 JST）

- 修正PR：https://github.com/MORRY1992/f-sp-topishirube/pull/4 （merged）。
- 検証CI：https://github.com/MORRY1992/f-sp-topishirube/actions/runs/40906847161 （success）。PR検証CIもsuccess。
- 実収集：https://github.com/MORRY1992/f-sp-topishirube/actions/runs/40906847231 。
- JR東日本企業別RSSは200・100候補、嵯峨野は200・5候補。本体一覧とJR東日本の出典3件の403は継続。RSSが本体の全発表を補ったとは判断しない。
- dataへの保存に成功（9c90294）。候補総数106、編集作業候補11、既報1、保留94、health=degraded。本文確認済み・自動公開を許可した候補はない。記事公開0件。
- 取得・分類・保存の各ステップはsuccess、最後の健全性報告ステップが意図どおり非ゼロで終了し、Action全体はfailure。単なる実行完了と全情報源の健全性を混同しないことを実ランでも確認した。
- 次回の定期実行は既存cron（17 */3 * * *、UTC）の同じコードを使用する。追加のWorkスケジュール・API契約は作成していない。
