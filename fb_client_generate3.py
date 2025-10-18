# -*- coding: utf-8 -*-
"""
fb_client_generate.py (no-grade/no-label/no-trim, bullet-3, two-signals, job-reco)

変更点:
- 学年は出力に含めない
- 「理由：」「Q1/Q2/Q3/カード」等のラベル語・カッコ書き禁止
- 文字数カット処理を撤廃（60〜90字は目安）
- stopに「（」「【」「[」を追加してカッコ出力を抑制
- repeat_penaltyで冗長表現を軽減

要件:
- 質的/量的から2つだけ選んでフィードバック（全部列挙しない）
- 次やりたい分類から合いそうなお仕事を1つ推薦（理由は文脈に自然に含めるが「理由」という語は使わない）
- 出力は箇条書き3文（各1文、合計60〜90文字“目安”）。カット処理はしない。
"""

import os
import sys
import json
import time
import random
import argparse
import requests
from typing import Dict, Any, Optional

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M")


def choose_tone() -> str:
    return random.choice(["やさしめ", "わくわく", "おだやか"])


def to_three_bullets(text: str) -> str:
    """モデル出力を箇条書き3行に整える（文字数は切らない）。"""
    s = text.strip().replace("\r", "")
    lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
    bullets = [ln for ln in lines if ln.startswith("・")]

    if len(bullets) < 3:
        # 箇条で来なければ文分割→先頭に「・」
        joined = " ".join(lines)
        parts = [p.strip() for p in joined.replace("。", "。|").split("|") if p.strip()]
        bullets = ["・" + p if not p.startswith("・") else p for p in parts if p]

    bullets = bullets[:3]
    while len(bullets) < 3:
        bullets.append("・がんばりがしっかり伝わったよ。")

    # ラベルやカッコの除去（念のため）
    cleaned = []
    ban_tokens = ["理由：", "理由:", "Q1", "Q2", "Q3", "カード", "（", "【", "["]
    for b in bullets:
        t = b
        for z in ban_tokens:
            t = t.replace(z, "")
        cleaned.append(t.strip())

    return "\n".join(cleaned)


def build_prompt(user_data: Dict[str, Any]) -> str:
    # 入力
    grade = user_data.get("grade", "")  # 出力には使わない
    shop = user_data.get("shop", "")
    minutes = user_data.get("minutes")
    rounds = user_data.get("rounds")
    activity = user_data.get("activity", "")

    q1_did = "／".join(user_data.get("q1_did", []))
    q2_enjoyed = "／".join(user_data.get("q2_enjoyed", []))
    q3_diff = user_data.get("q3_diff", "なし")
    q4_next_quadrant = user_data.get("q4_next_quadrant", "")
    cards_list = user_data.get("challenge_cards", [])
    cards = "／".join(cards_list)

    tparts = []
    if isinstance(minutes, int):
        tparts.append(f"{minutes}分")
    if isinstance(rounds, int):
        tparts.append(f"{rounds}回")
    tstr = "、".join(tparts) if tparts else ""

    tone = choose_tone()

    quadrant_jobs = {
        "つくる": ["たべものや・おかしや", "スライムや", "どうがさくせい"],
        "うごかす": ["カジノ", "ぎんこう", "なんでもや"],
        "つたえる": ["たいかいうんえい", "ジャーナリスト", "けんきゅういん"],
        "たすける": ["パトロール", "人さがし"],
    }
    jobs_text = "; ".join([f"{k}: {', '.join(v)}" for k, v in quadrant_jobs.items()])

    prompt = f"""
【指示】
小学生向けキャリアFB。出力は箇条書き3行のみ（各1文）。合計60〜90文字が目安。
現在の活動として書く。学年は出力に含めない。
「理由：」「Q1/Q2/Q3/カード」などのラベル語やカッコ書きは使わない。
質的(できた/たのしい/むずかしい/チャレンジカード)と量的(分/回)から
重要な2つだけ選んで称賛と気づきを述べる（全部は書かない）。
次やりたい分類に沿い、下の候補から合いそうなお仕事を1つ推薦し、自然なひとこと理由を添える。
トーンは「{tone}」。ひらがな多め・安全・肯定・具体的。

【次やりたい→おすすめ】
{jobs_text}

【入力】
- 体験：{shop}（{tstr}）
- 活動：{activity}
- できた：{q1_did}
- たのしかった：{q2_enjoyed}
- むずかしかった：{q3_diff}
- チャレンジカード：{cards}
- 次やりたい分類：{q4_next_quadrant}

【出力フォーマット（厳守）】
・選んだ要素1を短く称賛（現在の活動として）。
・選んだ要素2で成長や気づきをひとこと（数字は分/回のみ）。
・次は「おすすめ」をためそう（自然な理由を一言、ラベル語なし）。
"""
    return prompt.strip()


def generate_feedback(
    user_data: Dict[str, Any],
    model: str = MODEL_NAME,
    stream: bool = True,
    timeout: int = 40,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    num_predict: int = 90,
    num_ctx: int = 768,
    stop: Optional[list] = None,
) -> str:
    # ランダム性（少し揺らす）
    rnd_seed = random.randint(1, 2_000_000_000)
    if temperature is None:
        temperature = random.choice([0.3, 0.4, 0.5])
    if top_p is None:
        top_p = random.choice([0.9, 0.92, 0.95])

    # カッコや説明ブロックに入りにくくする
    if stop is None:
        stop = ["\n【", "（", "【", "["]

    prompt = build_prompt(user_data)
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": stream,
        "keep_alive": "0s",
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "seed": rnd_seed,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
            "repeat_penalty": 1.1,
        },
        "stop": stop,
    }

    if stream:
        resp = requests.post(url, json=payload, timeout=timeout, stream=True)
        resp.raise_for_status()
        chunks = []
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "response" in obj:
                sys.stdout.write(obj["response"])
                sys.stdout.flush()
                chunks.append(obj["response"])
            if obj.get("done", False):
                break
        print("")
        raw = "".join(chunks).strip()
    else:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()

    return to_three_bullets(raw)


def main():
    parser = argparse.ArgumentParser(
        description="こどものまち FB（3行/二要素/推薦・ノートリム）"
    )
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--timeout", type=int, default=40)
    parser.add_argument("--num-predict", type=int, default=90)
    parser.add_argument("--num-ctx", type=int, default=768)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    args = parser.parse_args()

    # デモデータ
    user_data = {
        "grade": "小1",  # 出力には使わない
        "shop": "けんきゅういん",
        "minutes": 30,
        "rounds": 2,
        "activity": "大人のお仕事を聞き、4種に分類してグラフ作成",
        "q1_did": ["人の話をよく聞いてまとめた"],
        "q2_enjoyed": [
            "グラフや写真がうまくできたとき",
            "みんなが分かりやすいと言ってくれたとき",
        ],
        "q3_diff": "メモを取るのがたいへんだった",
        "q4_next_quadrant": "うごかすしごと",
        "challenge_cards": ["ありがとうを言う", "さいごまでやりとげる"],
    }

    text = generate_feedback(
        user_data=user_data,
        model=args.model,
        stream=(not args.no_stream),
        timeout=args.timeout,
        temperature=args.temperature,
        top_p=args.top_p,
        num_predict=args.num_predict,
        num_ctx=args.num_ctx,
    )
    print("\n---\n最終出力:")
    print(text)


if __name__ == "__main__":
    for i in range(2):
        try:
            main()
            break
        except requests.RequestException as e:
            if i == 1:
                raise
            print(f"[warn] request error: {e}; retrying...", file=sys.stderr)
            time.sleep(0.7)
