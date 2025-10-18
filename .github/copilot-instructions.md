# copilot-instructions for llm-fb2025

このリポジトリは「こどものまち 2025」の即時フィードバック生成クライアント群です。
ローカルLLM（例：Ollama）へプロンプトを投げ、子ども向けの短く優しいフィードバック文を生成します。

要点：AIエージェントは下の点を守って変更・実装を行ってください。

- アーキテクチャの大枠
  - Pythonスクリプト群（`fb_client_generate.py`, `fb_client_generate2.py`, `fb_client_generate3.py`, `fb_client.py`）は、Ollama等のローカルLLMへJSONまたはプロンプトをPOSTしてフィードバックを得るクライアントです。
  - `llm-fb_prompt.md` と `fb_client.py` の `system_prompt` が生成ルールのソース・オーソリティです。これらを最優先に尊重して変更してください。

- 重要ファイル（参照例）
  - `fb_client.py`：システムプロンプト（JSON入出力仕様）の定義とChat APIサンプル。
  - `fb_client_generate.py`：高品質単発生成用（Few-shot、出力規約あり）。
  - `fb_client_generate2.py`：高速・80字制限・カード必須バリエーション。
  - `fb_client_generate3.py`：箇条書き3行バリエーション（ラベル・カッコ除去処理あり）。
  - `llm-fb_prompt.md`：仕様・入力JSON・期待出力の詳細ドキュメント（必読）。

- プロジェクト固有のルール（絶対守る）
  - 出力はユーザー向けの短いフィードバック（多くは2〜3文、箇条書きの場合は3行）で、ひらがな多め・優しい口調であること。
  - JSON出力が求められる箇所（`fb_client.py` の例）では、余計な説明文を付けず純粋なJSONのみを返すこと。
  - 禁止表現：他者比較・個人情報・否定表現・危険行為の示唆（プロンプト内に明示）。
  - 数値ログ（minutes / rounds / count_products_or_rounds）がある場合は、称賛や次の一歩の根拠に使う。

- 開発・実行ワークフロー
  - ローカル実行例（Ollamaが稼働している前提）：
    - 環境変数：`OLLAMA_HOST`（既定: http://localhost:11434）と`OLLAMA_MODEL`をセット可能。
    - スクリプト実行例（PowerShell）：

```powershell
python .\fb_client_generate.py --model "qwen2.5:3b-instruct-q4_K_M"
python .\fb_client_generate2.py
python .\fb_client_generate3.py
python .\fb_client.py
```

  - ネットワーク/タイムアウト：API呼び出しは `requests.post(..., timeout=...)` を使っています。変更時は既存の簡易リトライ（各スクリプトの __main__ 部）を壊さないでください。

- 変更提案時の注意点
  - 指示やFew-shot例を変えると出力の品質に大きく影響します。system prompt は `llm-fb_prompt.md` と `fb_client.py` の `system_prompt` を参照し、一貫性を保ってください。
  - トークン・ストップワード（stop）や `num_predict/num_ctx` の調整はモデルとホスト（Ollama）に依存します。調整する場合は小さな段階でABテストしてください。
  - ストリーミング実装（stream=True）は既存で可視化に使われています。UIやデバッグ時に便利なので、無効化するフラグ（--no-stream）を保持してください。

- テストとデバッグのヒント
  - 入力JSONの最小サンプルは `fb_client.py` の `user_prompt` と `system_prompt` を参考に作成できます。
  - 出力がJSONであることを厳密に検証するユニットテストを追加すること（例：キー存在、型チェック、文字数制約の簡易テスト）。
  - ロギング：APIレスポンスの生のchunksをファイルに保存するフックを追加すると、Few-shot調整時の比較が容易になります。

- 典型的な変更例（望ましい）
  - プロンプトのマイナー調整（文言・追記）→まず `llm-fb_prompt.md` を更新し、それに沿ってスクリプトのbuild_promptを修正。
  - 文字数整形ロジックの改善（gentle_trim, to_three_bullets等）→既存関数を改修して副作用を避ける。

- ここに書かれていない不明点があれば、READMEや実行ログの出力サンプルを要求してください。

---

更新の方向性や文章の追加・削除が必要な箇所についてフィードバックをください。修正案を反映して再度更新します。
