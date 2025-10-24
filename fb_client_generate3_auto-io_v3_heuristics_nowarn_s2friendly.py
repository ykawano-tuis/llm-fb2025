# -*- coding: utf-8 -*-
"""
fb_client_generate3_auto-io_v3_heuristics_nowarn_s2friendly.py

目的：
- JSONL(新スキーマ; gen_inputs_by_quadrant_jsonl_v3.pyの出力)を読み込み、
  各レコードから「箇条書き3文（各1文）」の前向きフィードバックを生成し、
  CSV(no, input, output)を Shift-JIS（Excelで文字化けしない）で出力。
- Warn（警告）を出さない。失敗時は静かにフォールバック。
- 小2向けにやさしい語を促すプロンプト＋後処理（ラベル/難語の抑制、カード語の制御）。
- 次やりたい分類→具体お仕事はヒューリスティクス（キーワード優先）で推薦し、
  3文目で短く自然な根拠をふれる（「理由」という語は使わない）。
- 生成中の文字列を、任意でストリーミング表示（--no-streamで無効化）。

使い方：
  # ストリーミング表示あり（既定）
  python fb_client_generate3_auto-io_v3_heuristics_nowarn_s2friendly.py

  # ストリーミング表示なし
  python fb_client_generate3_auto-io_v3_heuristics_nowarn_s2friendly.py --no-stream

  # UTF-8でCSV出力したい場合
  python fb_client_generate3_auto-io_v3_heuristics_nowarn_s2friendly.py --encoding utf-8
"""

import os
import sys
import json
import argparse
import csv
import random
import re
from typing import Any, Dict, List, Optional, Tuple
import requests

# ========== Ollama設定 ==========
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME  = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M")

# ========== 分類とお仕事 ==========
QUADRANTS_JOBS: Dict[str, List[str]] = {
    "つくるしごと": ["たべものや・おかしや", "スライムや", "どうがクリエイタ"],
    "うごかすしごと": ["カジノ", "ぎんこう", "なんでもや"],
    "つたえるしごと": ["たいかいうんえい", "ジャーナリスト", "けんきゅういん"],
    "たすけるしごと": ["パトロール", "人さがし"],
}

# ========== キーワード・ヒューリスティクス ==========
# 正規表現 → (おすすめお仕事, 自然な根拠フレーズ)
HEURISTIC_RULES: Dict[str, List[Tuple[str, str, str]]] = {
    "つくるしごと": [
        (r"(動画|どうが|撮影|編集|写真)", "どうがクリエイタ", "見せ方の工夫がいかせる"),
        (r"(スライム|ねる|まぜる|ぷにぷに)", "スライムや", "手を動かして作る良さがいかせる"),
        (r"(おかし|料理|作る|たべもの|クッキー|パン|ケーキ)", "たべものや・おかしや", "作って人を喜ばせる力がいかせる"),
    ],
    "うごかすしごと": [
        (r"(お金|会計|銀行|ぎんこう|受付|口座|数字)", "ぎんこう", "数や手順をていねいに扱える"),
        (r"(ゲーム|ルーレット|くじ|勝負|カード|あそび)", "カジノ", "場を楽しく進める工夫がいかせる"),
        (r"(配達|届け|案内|移動|てつだ|巡回|順番|整列)", "なんでもや", "まわりを見て動ける"),
    ],
    "つたえるしごと": [
        (r"(取材|インタビュー|聞い|話|伝え|記事|ニュース|メモ)", "ジャーナリスト", "聞いたことをまとめて伝えられる"),
        (r"(データ|グラフ|調べ|研究|分類|アンケート|集計)", "けんきゅういん", "調べて整理し表せる"),
        (r"(大会|運営|進行|ルール説明|イベント)", "たいかいうんえい", "場を整えて進める力がいかせる"),
    ],
    "たすけるしごと": [
        (r"(見回り|安全|清掃|片付け|注意|マナー)", "パトロール", "まちを守る思いやりがいかせる"),
        (r"(迷子|人探し|さがし|はぐれ|探す)", "人さがし", "困りごとに気づいて助けられる"),
    ],
}

GENERIC_REASONS: Dict[str, str] = {
    "つくるしごと": "手を動かして形にする良さがいかせる",
    "うごかすしごと": "手順や動きで支える力がいかせる",
    "つたえるしごと": "まとめて伝える力がいかせる",
    "たすけるしごと": "気づいて支えるやさしさがいかせる",
}

# ========== ユーティリティ ==========
_SIMPLE_MAP: List[Tuple[str, str]] = [
    (r"クリエイティブ", "工夫"),
    (r"プロジェクト", "活動"),
    (r"パフォーマンス", "できばえ"),
    (r"アウトプット", "しあげ"),
    (r"インプット", "学び"),
    (r"テスト", "学習"),
]

def _pick_qualitative(rec: Dict[str, Any]) -> str:
    """質的要素: did / enjoyed / diff から1つ（did/enjoy優先、'なし'除外）"""
    did = rec.get("q1_did") or []
    enjoyed = rec.get("q2_enjoyed") or []
    diff = rec.get("q3_diff") or ""
    cands: List[str] = []
    if isinstance(did, list): cands += [str(x).strip() for x in did if str(x).strip()]
    if isinstance(enjoyed, list): cands += [str(x).strip() for x in enjoyed if str(x).strip()]
    if isinstance(diff, str) and diff.strip() and diff != "なし": cands.append(diff.strip())
    return random.choice(cands) if cands else "よく考えて取り組めた"

def _pick_quantitative(rec: Dict[str, Any]) -> str:
    """量的要素: minutes または rounds から1つ"""
    mins = rec.get("minutes")
    rnds = rec.get("rounds")
    q: List[str] = []
    if isinstance(mins, int): q.append(f"{mins}分")
    if isinstance(rnds, int): q.append(f"{rnds}回")
    return random.choice(q) if q else "短い時間"

def _keywords_base(rec: Dict[str, Any], qual: str) -> str:
    """ヒューリスティクス用の検索テキスト"""
    parts: List[str] = [str(qual)]
    if rec.get("activity"): parts.append(str(rec["activity"]))
    for k in ("q1_did", "q2_enjoyed"):
        lst = rec.get(k) or []
        if isinstance(lst, list): parts.extend(map(str, lst))
    if rec.get("q3_diff"): parts.append(str(rec["q3_diff"]))
    return " ".join(parts)

def _recommend_job_with_reason(rec: Dict[str, Any], qual: str) -> Tuple[str, str]:
    """分類内のキーワード優先でお仕事と根拠を選ぶ"""
    quad = rec.get("q4_next_quadrant") or ""
    candidates = QUADRANTS_JOBS.get(quad, [])
    text = _keywords_base(rec, qual)

    # 1) ルールマッチ（上から優先）
    for pattern, job, reason in HEURISTIC_RULES.get(quad, []):
        if re.search(pattern, text):
            if job in candidates:
                return job, reason

    # 2) 現お仕事を除外して分類内ランダム
    if candidates:
        cur = str(rec.get("shop", ""))
        pool = [j for j in candidates if j != cur] or candidates
        return random.choice(pool), GENERIC_REASONS.get(quad, "力がいかせる")

    # 3) 分類未設定 → 全体から
    all_jobs = [j for lst in QUADRANTS_JOBS.values() for j in lst]
    return random.choice(all_jobs), GENERIC_REASONS.get("つたえるしごと", "力がいかせる")

def _maybe_pick_card(rec: Dict[str, Any]) -> Optional[str]:
    cards = rec.get("challenge_cards") or []
    return random.choice(cards) if cards else None

def _sentences_to_three_bullets(text: str) -> str:
    """文分割→3文整形（途中切断なし）→箇条書き化"""
    s = (text or "").replace("\r", "").strip()
    s = re.sub(r"^[・\-\*\s]+", "", s, flags=re.MULTILINE)
    parts = re.split(r"(?<=[。！？])", s)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) == 0:
        parts = ["がんばりがしっかり伝わったね。", "短い時間でも集中できたね。", "新しい仕事に挑戦してみよう。"]
    elif len(parts) == 1:
        parts = [parts[0], "短い時間でも集中できたね。", "新しい仕事に挑戦してみよう。"]
    elif len(parts) == 2:
        parts = [parts[0], parts[1], "新しい仕事に挑戦してみよう。"]
    else:
        parts = [parts[0], parts[1], "".join(parts[2:]).strip()]
        if not re.search(r"[。！？]$", parts[2]): parts[2] += "。"

    bullets = []
    for p in parts[:3]:
        if not p.endswith(("。", "！", "？")): p += "。"
        bullets.append("・" + p)
    return "\n".join(bullets)

# ラベル/難語の除去とカード語の制御（小2向けやさしさ最終調整）
def _post_simplify_for_grade(text: str, card: Optional[str]) -> str:
    s = text

    # 行頭ラベルを除去（質的/量的やお店名コロン出力など）
    s = re.sub(r"^[・\s]*?(質的|量的)\s*[:：]\s*", "・", s, flags=re.MULTILINE)
    s = re.sub(
        r"^[・\s]*?(たべものや・おかしや|スライムや|どうがクリエイタ|カジノ|ぎんこう|なんでもや|たいかいうんえい|ジャーナリスト|けんきゅういん|パトロール|人さがし)\s*[:：]\s*",
        "・",
        s,
        flags=re.MULTILINE,
    )

    # 難語→やさしい語へ
    for pat, rep in _SIMPLE_MAP:
        s = re.sub(pat, rep, s)

    # 行ごと処理
    lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
    if len(lines) < 3:
        while len(lines) < 3:
            lines.append("・がんばりが伝わったね。")
    lines = [ln if ln.startswith("・") else "・" + ln for ln in lines[:3]]

    # カード語のコントロール（「にこにこ」等の裸語の多用を防ぐ）
    if card:
        simple_card = re.sub(r"\s+", "", card)
        lines[0] = re.sub(r"(にこにこ)+", "", lines[0])
        lines[1] = re.sub(r"(にこにこ)+", "", lines[1])
        if simple_card not in lines[2]:
            if lines[2].endswith(("。", "！", "？")):
                lines[2] = lines[2][:-1] + f"、{card}も意識しよう。"
            else:
                lines[2] += f"、{card}も意識しよう。"
    else:
        lines = [re.sub(r"(にこにこ)+", "", ln) for ln in lines]

    # 句読点整形
    fixed: List[str] = []
    for ln in lines[:3]:
        t = re.sub(r"\s+", " ", ln).strip()
        if not t.endswith(("。", "！", "？")):
            t += "。"
        t = re.sub(r"([。！？])\1+", r"\1", t)
        fixed.append(t)

    return "\n".join(fixed)

# ========== プロンプト生成（小2向け厳格化） ==========
def _build_prompt(rec: Dict[str, Any], qual: str, quant: str,
                  suggest_job: str, reason_hint: str, opt_card: Optional[str],
                  concise: bool = False) -> str:
    quad = rec.get("q4_next_quadrant", "")
    card_hint = (f"必要なら「{opt_card}」をやさしく一度だけ入れてよい" if opt_card else "チャレンジカードは入れなくてもよい")
    banned = "使わない語: 質的,量的,テスト,クリエイティブ,プロジェクト,高度,抽象的,メタ,メタ認知"
    tone = "やさしい言葉で、短い文。むずかしい言い回しやカタカナ語は使わない。"

    return f"""
小学生（小2めやす）向けの前向きフィードバックを作成してください。

【出力仕様（厳守）】
- 箇条書き3文のみ、各1文。学年名やラベルやカッコは出さない（例:「質的:」「量的:」禁止）。
- 子どもの一人称や二人称は使わない（「ぼく/わたし」「きみ/あなた」などは書かない）。
- 使ってよい題材は2つだけ: 〔やったこと〕{qual} ／ 〔時間や回数〕{quant}。他の要素は出さない。
- 三文目は、次やりたい分類の具体お仕事「{suggest_job}」をおすすめし、{reason_hint} を短く自然にふれる。
  {card_hint}（その語をむやみにくり返さない）。
- 全体で60〜90文字“目安”。文の途中では切らない。{banned}
- {tone}
- 文の例: 「〜ができてすごいね。〜をがんばってえらいね。つぎは〜をやってみよう。」

【出力】
・
・
・
""".strip()

# ========== LLM呼び出し（ストリーミング対応/警告なし） ==========
def _invoke_llm(prompt: str, *, model: str, stream: bool, timeout: int,
                num_predict: int, num_ctx: int) -> str:
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "keep_alive": "0s",
        "options": {
            "temperature": 0.2,   # 小2向け難語混入を抑えるため低め
            "top_p": 0.9,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
            "repeat_penalty": 1.1,
            "seed": random.randint(1, 2_000_000_000),
        },
        "stop": ["\n【", "（", "["],
    }

    if stream:
        resp = requests.post(url, json=payload, timeout=timeout, stream=True)
        resp.raise_for_status()
        buf: List[str] = []
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "response" in obj:
                chunk = obj["response"]
                # 逐次表示
                sys.stdout.write(chunk)
                sys.stdout.flush()
                buf.append(chunk)
            if obj.get("done"):
                break
        sys.stdout.write("\n")
        sys.stdout.flush()
        return "".join(buf).strip()

    # 非ストリーミング
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json().get("response", "").strip()

# ========== 1件生成 ==========
def _gen_feedback(rec: Dict[str, Any], *, model: str, stream: bool,
                  timeout: int, num_predict: int, num_ctx: int) -> str:
    qual = _pick_qualitative(rec)
    quant = _pick_quantitative(rec)
    job, reason = _recommend_job_with_reason(rec, qual)
    card = _maybe_pick_card(rec)

    prompt = _build_prompt(rec, qual, quant, job, reason, card, concise=False)
    try:
        raw = _invoke_llm(prompt, model=model, stream=stream, timeout=timeout,
                          num_predict=num_predict, num_ctx=num_ctx)
        bullets = _sentences_to_three_bullets(raw)
        bullets = _post_simplify_for_grade(bullets, card)
        return bullets
    except Exception:
        # Warn非表示：静かにフォールバック
        fb = (
            f"{qual}ができてすごいね。"
            f"{quant}もしっかり取り組めてえらいね。"
            f"つぎは{job}をためしてみよう、{reason}から。"
        )
        return _post_simplify_for_grade(_sentences_to_three_bullets(fb), card)

# ========== JSONL入出力 ==========
def read_jsonl(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]

def dumps_compact_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

def write_minimal_csv(rows: List[Dict[str, str]], path: str, encoding: str) -> None:
    with open(path, "w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["no", "input", "output"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

# ========== CLI ==========
def main():
    ap = argparse.ArgumentParser(description="JSONL→LLM 3文FB→CSV（SJIS／小2向けやさしい語／ヒューリスティクス推薦／Warn無）")
    ap.add_argument("--input", default="input-data_10.jsonl")
    ap.add_argument("--output", default="out_feedback_sjis.csv")
    ap.add_argument("--encoding", default="shift_jis")
    ap.add_argument("--model", default=MODEL_NAME)
    ap.add_argument("--timeout", type=int, default=40)
    ap.add_argument("--num-predict", type=int, default=100)
    ap.add_argument("--num-ctx", type=int, default=768)
    ap.add_argument("--no-stream", action="store_true", help="ストリーミング表示を無効化")
    args = ap.parse_args()

    stream = not args.no_stream

    records = read_jsonl(args.input)
    out_rows: List[Dict[str, str]] = []

    for i, rec in enumerate(records, 1):
        # ストリーミング時は見出しを軽く表示
        if stream:
            print(f"\n# {i} ----------------------")
        fb = _gen_feedback(
            rec,
            model=args.model,
            stream=stream,
            timeout=args.timeout,
            num_predict=args.num_predict,
            num_ctx=args.num_ctx,
        )
        # 非ストリーミング時は生成後に完成形を表示してもよい（必要なら以下を解除）
        # else:
        #     print(f"\n# {i} ----------------------\n{fb}\n")

        out_rows.append({"no": str(i), "input": dumps_compact_json(rec), "output": fb})

    write_minimal_csv(out_rows, args.output, args.encoding)
    print(f"\n✅ 出力完了: {args.output}（文字コード: {args.encoding}）")

if __name__ == "__main__":
    main()
