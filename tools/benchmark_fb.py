# Lightweight benchmark for fb_client_generate3
# Measures response time and checks basic output rules (3 bullets, banned tokens)

import time
import json
import argparse
import statistics
from typing import List

# Import generate_feedback from module
from fb_client_generate3 import generate_feedback

BANNED_TOKENS = ["理由：", "理由:", "Q1", "Q2", "Q3", "カード", "（", "【", "["]

SAMPLES = [
    {
        "grade": "小3",
        "shop": "けんきゅういん",
        "minutes": 30,
        "rounds": 2,
        "activity": "大人のお仕事を聞き、4種に分類してグラフ作成",
        "q1_did": ["人の話をよく聞いてまとめた"],
        "q2_enjoyed": ["グラフがうまくできた"],
        "q3_diff": "メモを取るのがたいへんだった",
        "q4_next_quadrant": "つくる",
        "challenge_cards": ["ありがとうを言う"]
    },
    {
        "grade": "小2",
        "shop": "ぎんこう",
        "minutes": 10,
        "rounds": 3,
        "activity": "おかねの受け渡し練習",
        "q1_did": ["ルールを守って行動した"],
        "q2_enjoyed": ["お客さんがうれしそうだった"],
        "q3_diff": "時間内に終えるのがむずかしかった",
        "q4_next_quadrant": "うごかす",
        "challenge_cards": ["さいごまでやりとげる"]
    },
    {
        "grade": "小4",
        "shop": "たいかいうんえい",
        "minutes": 20,
        "rounds": 1,
        "activity": "会場の説明や司会を体験",
        "q1_did": ["説明を30秒でできた"],
        "q2_enjoyed": ["話すのが楽しかった"],
        "q3_diff": "緊張した",
        "q4_next_quadrant": "つたえる",
        "challenge_cards": ["ありがとうを言う"]
    }
]


def check_output(text: str) -> List[str]:
    """Return list of violation messages"""
    violations = []
    # check banned tokens
    for b in BANNED_TOKENS:
        if b in text:
            violations.append(f"banned_token:{b}")
    # check bullet lines (to_three_bullets will format but we expect 3 lines)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) != 3:
        violations.append(f"line_count:{len(lines)}")
    return violations


def run_benchmark(samples, model: str, fast: bool):
    times = []
    all_violations = []
    for s in samples:
        start = time.perf_counter()
        try:
            out = generate_feedback(s, model=model, stream=False, concise=fast)
        except Exception as e:
            all_violations.append(f"error:{e}")
            times.append(None)
            continue
        end = time.perf_counter()
        elapsed = end - start
        times.append(elapsed)
        violations = check_output(out)
        all_violations.append({"sample": s.get("shop"), "violations": violations, "output": out})
    # stats
    successful_times = [t for t in times if t is not None]
    stats = {
        "count": len(samples),
        "mean_s": statistics.mean(successful_times) if successful_times else None,
        "stdev_s": statistics.stdev(successful_times) if len(successful_times) > 1 else 0.0,
        "times": times,
        "results": all_violations,
    }
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark fb_client_generate3 generate_feedback")
    parser.add_argument("--model", default=None, help="Ollama model name (use env default if empty)")
    parser.add_argument("--fast", action="store_true", help="use concise/fast mode")
    args = parser.parse_args()

    model = args.model
    stats = run_benchmark(SAMPLES, model=model, fast=args.fast)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
