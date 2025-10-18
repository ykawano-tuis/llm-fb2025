"""Benchmark suite for fb_client_generate3

Runs multiple iterations per sample and per config (normal vs fast) and
produces a comparative JSON report with timing statistics and violation rates.
"""
import time
import json
import argparse
import statistics
from typing import List, Dict, Any

from fb_client_generate3 import generate_feedback, MODEL_NAME

# reuse sample set similar to tools/benchmark_fb.py
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

BANNED_TOKENS = ["理由：", "理由:", "Q1", "Q2", "Q3", "カード", "（", "【", "["]

CONFIGS = {
    "normal": {
        "concise": False,
        "num_predict": 90,
        "num_ctx": 768,
        "timeout": 40,
    },
    "fast": {
        "concise": True,
        "num_predict": 80,
        "num_ctx": 512,
        "timeout": 15,
    },
}


def analyze_output(text: str) -> Dict[str, Any]:
    violations = []
    for b in BANNED_TOKENS:
        if b in text:
            violations.append(b)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    char_len = len(text)
    return {
        "lines": len(lines),
        "chars": char_len,
        "violations": violations,
    }


def run_suite(samples: List[Dict[str, Any]], configs: Dict[str, Dict[str, Any]], iters: int, model: str = None):
    model = model or MODEL_NAME
    report = {"model": model, "iters": iters, "results": {}}

    for cfg_name, cfg in configs.items():
        cfg_res = {}
        for sample in samples:
            times = []
            outputs = []
            analyses = []
            for i in range(iters):
                start = time.perf_counter()
                try:
                    out = generate_feedback(
                        user_data=sample,
                        model=model,
                        stream=False,
                        timeout=cfg["timeout"],
                        num_predict=cfg["num_predict"],
                        num_ctx=cfg["num_ctx"],
                        concise=cfg["concise"],
                    )
                except Exception as e:
                    out = f"<error:{e}>"
                end = time.perf_counter()
                elapsed = end - start
                times.append(elapsed)
                outputs.append(out)
                analyses.append(analyze_output(out))
            # compute stats
            successful_times = [t for t in times if t is not None]
            mean_t = statistics.mean(successful_times) if successful_times else None
            stdev_t = statistics.stdev(successful_times) if len(successful_times) > 1 else 0.0
            avg_chars = statistics.mean([a["chars"] for a in analyses])
            avg_lines = statistics.mean([a["lines"] for a in analyses])
            violation_counts = sum(1 for a in analyses if a["violations"])
            cfg_res[sample.get("shop")] = {
                "times": times,
                "mean_s": mean_t,
                "stdev_s": stdev_t,
                "avg_chars": avg_chars,
                "avg_lines": avg_lines,
                "violation_count": violation_counts,
                "examples": outputs[:3],
            }
        report["results"][cfg_name] = cfg_res
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark suite for fb_client_generate3: compare normal vs fast")
    parser.add_argument("--iters", type=int, default=10, help="iterations per sample per config")
    parser.add_argument("--model", default=None, help="model name override")
    parser.add_argument("--out", default=None, help="output JSON file path")
    args = parser.parse_args()

    rpt = run_suite(SAMPLES, CONFIGS, iters=args.iters, model=args.model)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rpt, f, ensure_ascii=False, indent=2)
        print(f"Wrote report to {args.out}")
    else:
        print(json.dumps(rpt, ensure_ascii=False, indent=2))
