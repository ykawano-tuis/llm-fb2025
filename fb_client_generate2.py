# -*- coding: utf-8 -*-
"""
fb_client_generate.py (fast+concise+card+random)
- 高速化：超短プロンプト、num_predict=80, num_ctx=768, stop強め
- 文字数：最大80字にハード制限（やさしく整形）
- カード：質的FBにチャレンジカードを必ず1つ言及
- ランダム性：seed/temperature/top_p/トーンを少し揺らす
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


# ----------------------
# 小さなユーティリティ
# ----------------------
def choose_tone() -> str:
    return random.choice(["やさしめ", "わくわく", "おだやか"])


def gentle_trim(text: str, max_len: int = 80) -> str:
    """最大文字数を超えたらやさしく丸める（句点付与）"""
    s = text.strip().replace("\n", " ").replace("  ", " ")
    if len(s) > max_len:
        s = s[:max_len]
    if not s.endswith(("。", "！", "？")):
        s += "。"
    return s


# ----------------------
# プロンプト生成（超短）
# ----------------------
def build_prompt(user_data: Dict[str, Any]) -> str:
    grade = user_data.get("grade", "")
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
    # 出力中に必ず1つ入れてほしいカード（なければ空文字）
    card_must = random.choice(cards_list) if cards_list else ""

    tparts = []
    if isinstance(minutes, int):
        tparts.append(f"{minutes}分")
    if isinstance(rounds, int):
        tparts.append(f"{rounds}回")
    tstr = "、".join(tparts) if tparts else ""

    tone = choose_tone()

    # 極力短い指示（列挙にならないよう“2〜3文・要約→称賛→一歩”の型を強制）
    prompt = f"""
【指示】
小学生向けキャリアFB。日本語2〜3文、合計50〜80文字。箇条書き禁止。
要約→称賛→つぎの一歩の順。ひらがな多め・肯定的・具体的・安全。
質的（できた/たのしい/むずかしい）と量的（分/回）を1文内で自然にふれる。
文中にチャレンジカード「{card_must}」を1回だけ入れる。
最後に5〜15分でできる具体行動を1つ提案。トーンは「{tone}」。

【入力】
- 学年：{grade}
- 体験：{shop}（{tstr}）
- 活動：{activity}
- Q1できた：{q1_did}
- Q2たのしかった：{q2_enjoyed}
- Q3むずかしかった：{q3_diff}
- Q4つぎ：{q4_next_quadrant}
- カード：{cards}

【出力】
短い応援文のみ（2〜3文・50〜80文字）。余計な説明は出さない。
"""
    return prompt.strip()


# ----------------------
# 生成呼び出し
# ----------------------
def generate_feedback(
    user_data: Dict[str, Any],
    model: str = MODEL_NAME,
    stream: bool = True,
    timeout: int = 45,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    num_predict: int = 80,
    num_ctx: int = 768,
    stop: Optional[list] = None,
) -> str:
    # ランダム性（毎回ちょい変わる）
    rnd_seed = random.randint(1, 2_000_000_000)
    if temperature is None:
        temperature = random.choice([0.25, 0.35, 0.45])
    if top_p is None:
        top_p = random.choice([0.9, 0.92, 0.95])

    if stop is None:
        stop = ["\n【", "\n\n\n"]

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
        },
        "stop": stop,
    }

    if stream:
        resp = requests.post(url, json=payload, timeout=timeout, stream=True)
        resp.raise_for_status()
        out_chunks = []
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "response" in obj:
                chunk = obj["response"]
                sys.stdout.write(chunk)
                sys.stdout.flush()
                out_chunks.append(chunk)
            if obj.get("done", False):
                break
        print("")
        text = "".join(out_chunks).strip()
    else:
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()

    # 文字数を80字上限で整える（足りない場合はそのまま）
    return gentle_trim(text, max_len=80)


# ----------------------
# エントリポイント
# ----------------------
def main():
    parser = argparse.ArgumentParser(
        description="こどものまち FB 生成（速い・80字・カード言及・ランダム）"
    )
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--no-stream", action="store_true")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--num-predict", type=int, default=80)
    parser.add_argument("--num-ctx", type=int, default=768)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    args = parser.parse_args()

    # デモデータ（任意に差し替え）
    user_data = {
        "grade": "小3",
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
        "q4_next_quadrant": "つくる（ものをつくる×新しいことをひろげる）",
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
    # 簡易リトライ
    for i in range(2):
        try:
            main()
            break
        except requests.RequestException as e:
            if i == 1:
                raise
            print(f"[warn] request error: {e}; retrying...", file=sys.stderr)
            time.sleep(0.8)
