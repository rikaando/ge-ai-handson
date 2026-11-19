# サンプル 2: サブテーマ 2 の実装例 (クレジットカード番号の検出)

サブテーマ 2 (`theme2_credit_card_audit/credit_card_audit.py`) の Python 標準ライブラリによる参考実装と単体テストです。追加パッケージのインストールなしでそのまま実行でき、サンプルコードの検出処理はエージェントからも再利用できます。

## ファイル構成

| ファイル | 内容 |
| :--- | :--- |
| `credit_card_audit.py` | 14 桁・16 桁のクレジットカード番号を境界付き正規表現と Luhn 検証で検出し、国際ブランド判定と末尾 4 桁以外をマスクしたうえで、発生部署や対象ログを整形テキストまたは JSON 形式で標準出力に表示する CLI 兼モジュール |
| `test_credit_card_audit.py` | 14 桁・16 桁カード番号の検出、末尾 4 桁以外のマスク処理 (平文の非出力)、10〜18 桁の業務番号に対する誤検知ゼロ、CLI 標準出力・JSON 出力を検証する単体テスト |

## 実行方法

以下のコマンドはすべてリポジトリ直下 `ge-ai-handson/` で実行します。

### 監査スクリプトの実行

```bash
python3 samples/sample2_credit_card_audit/credit_card_audit.py
python3 samples/sample2_credit_card_audit/credit_card_audit.py --text "カード番号 4111-1111-1111-1111 と注文番号 ORD-2026101501"
python3 samples/sample2_credit_card_audit/credit_card_audit.py --json
```

### 単体テストの実行

```bash
python3 -m unittest discover -s samples/sample2_credit_card_audit -p "test_*.py" -v
```

## Antigravity へのプロンプト例

リポジトリ直下 `ge-ai-handson/` で起動した `agy` に以下を入力すると、コードを変更せずに単体テストや監査スクリプトを実行して結果を確認できます。

### 単体テストの実行と全件監査レポートの表示

```text
コードは変更せず、samples/sample2_credit_card_audit/ の単体テストを実行したあと、samples/sample2_credit_card_audit/credit_card_audit.py を実行して標準出力の監査レポートを表示してください。
```

### 指定テキストの単発判定

```text
コードは変更せず、samples/sample2_credit_card_audit/credit_card_audit.py に --text オプションで "カード番号 4111-1111-1111-1111 と注文番号 ORD-2026101501" を渡して実行し、判定結果を表示してください。
```

この検出ロジックを Cloud Run にデプロイして Gemini Enterprise から呼び出す手順は `samples/sample3_cloud_run_a2a/README.md` を参照してください。
