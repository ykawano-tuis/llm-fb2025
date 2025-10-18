# -*- coding: utf-8 -*-
"""
fb_client_generate.py (improved)
Ollama /api/generate を使った「こどものまち 即時フィードバック」クライアント（単発生成・状態レス）

改良点:
- 列挙を避けるための強い生成規約＋Few-shotを付与
- 2〜3文・50〜90文字、箇条書き禁止、具体的な「つぎの一歩」を必ず1つ
- 軽いポストプロセスで90字超をやさしく短縮
"""

import os
import sys
import json
import time
import argparse
import requests
from typing import Dict, Any, Optional

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b-instruct-q4_K_M")


def build_prompt(user_data: Dict[str, Any]) -> str:
    """
    System＋Userを統合した単発プロンプトを生成。
    user_data 例:
    {
      "grade": "小3",
      "shop": "けんきゅういん",
      "minutes": 30,
      "rounds": 2,
      "activity": "大人のお仕事を聞き、4種に分類してグラフ作成",
      "q1_did": ["人の話をよく聞いてまとめた"],
      "q2_enjoyed": ["グラフや写真がうまくできたとき", "みんなが分かりやすいと言ってくれたとき"],
      "q3_diff": "メモを取るのがたいへんだった",
      "q4_next_quadrant": "つくる（ものをつくる×新しいことをひろげる）",
      "challenge_cards": ["ありがとうを言う", "さいごまでやりとげる"]
    }
    """
    grade = user_data.get("grade", "")
    shop = user_data.get("shop", "")
    minutes = user_data.get("minutes")
    rounds = user_data.get("rounds")
    activity = user_data.get("activity", "")

    q1_did = "／".join(user_data.get("q1_did", []))
    q2_enjoyed = "／".join(user_data.get("q2_enjoyed", []))
    q3_diff = user_data.get("q3_diff", "なし")
    q4_next_quadrant = user_data.get("q4_next_quadrant", "")
    cards = "／".join(user_data.get("challenge_cards", []))

    time_part = []
    if isinstance(minutes, int):
        time_part.append(f"{minutes}分")
    if isinstance(rounds, int):
        time_part.append(f"{rounds}回")
    time_str = "、".join(time_part) if time_part else ""

    # ---- 強い生成規約＋Few-shot付き 単一プロンプト ----
    prompt = f"""
【役割】
あなたは小学生向けキャリア学習のフィードバック・アシスタント。

【目的】
質的（できた/たのしい/むずかしい）と量的（分/回）を踏まえ、
子どもが「興味の発見」と「次の挑戦」につながる短い応援文を返す。

【出力規約（厳守）】
- 日本語 2〜3文、合計50〜90文字
- 箇条書き禁止。やさしい言葉、肯定・具体的
- 最後に5〜15分でできる「つぎの一歩」を1つだけ示す
- 禁止：他者比較・個人情報・否定表現

【内在評価観点（表示しないが活用）】
- 関心（Concern）：先を見通す/準備
- 主体（Control）：自分で選んで進める
- 探求（Curiosity）：試す/質問/広げる
- 自信（Confidence）：やり抜く/回数・時間の伸び

【Few-shot例（スタイル参考・出力には含めない）】
入力例A:
- 学年：小3
- 体験：ぎんこう（10分、3回）
- 活動：おかねの受け渡し
- Q1できた：ルールを守る／お金をわたす
- Q2たのしかった：お客さんがよろこんだ
- Q3むずかしかった：時間内に終える
- Q4つぎ：つたえる
- カード：さいごまでやりとげる
出力例A（50〜90字、2〜3文）:
ルールをまもって3回やりとげたね。おきゃくさんの笑顔もすてき。 つぎはおつりを2回だけ5分でれんしゅうしよう。

入力例B:
- 学年：小3
- 体験：けんきゅういん（30分、2回）
- 活動：大人の仕事を聞き取り、4分類してグラフ化
- Q1できた：人の話をよく聞いてまとめた
- Q2たのしかった：グラフや写真がうまくできた／分かりやすいと言われた
- Q3むずかしかった：メモを取る
- Q4つぎ：つくる
- カード：ありがとうを言う／さいごまでやりとげる
出力例B（50〜90字、2〜3文）:
聞いてまとめて見せる力が光ったね。30分×2回でじしんもUP。 つぎは作品を1つ5分でつくり、写真で記録してみよう。

【入力】
- 学年：{grade}
- 体験：{shop}（{time_str}）
- 活動：{activity}
- Q1できた：{q1_did}
- Q2たのしかった：{q2_enjoyed}
- Q3むずかしかった：{q3_diff}
- Q4つぎ：{q4_next_quadrant}
- カード：{cards}

【最終出力】
上の規約を満たす短い応援文のみを出力（2〜3文・50〜90文字）。
"""
    return prompt.strip()


def gentle_trim_to_90chars(text: str) -> str:
    """
    90文字超のときだけやさしく短縮。
    ・全角90字を超える部分をカット
    ・文末が不自然なら句点を付与
    """
    s = text.strip()
    # 余計な改行・箇条書き記号を軽く除去
    s = s.replace("\n", " ").replace("・", " ").replace("  ", " ")
    if len(s) > 90:
        s = s[:90]
    if not s.endswith(("。", "！", "？")):
        s += "。"
    return s


def generate_feedback(
    user_data: Dict[str, Any],
    model: str = MODEL_NAME,
    stream: bool = True,
    timeout: int = 60,
    temperature: float = 0.2,
    num_predict: int = 120,
    num_ctx: int = 1024,
    stop: Optional[list] = None,
) -> str:
    """
    Ollama /api/generate に単発で投げる。
    """
    if stop is None:
        # Few-shotや指示ブロックの境界で止めやすく
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

    # 90字超のみ軽く整形（規約逸脱時の保険）
    return gentle_trim_to_90chars(text)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="こどものまち FB 生成（/api/generate, 単発・高速・高品質）"
    )
    parser.add_argument("--model", default=MODEL_NAME, help="Ollama model name")
    parser.add_argument(
        "--no-stream", action="store_true", help="ストリーミングを無効化"
    )
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--num-predict", type=int, default=120)
    parser.add_argument("--num-ctx", type=int, default=1024)
    args = parser.parse_args()

    # デモ用入力（必要に応じて差し替え）
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
            time.sleep(1.0)