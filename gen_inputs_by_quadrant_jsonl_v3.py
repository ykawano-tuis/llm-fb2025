# -*- coding: utf-8 -*-
"""
gen_inputs_by_quadrant_jsonl_v3.py
こどものまち：低学年（1〜2年）向け アンケート入力データ ジェネレータ（JSONL出力版／UTF-8ファイル保存対応）

使い方:
  # 標準出力に出す
  python gen_inputs_by_quadrant_jsonl_v3.py --n 5 --seed 2025

  # ファイルに保存（UTF-8, 改行は \n）
  python gen_inputs_by_quadrant_jsonl_v3.py --n 50 --seed 2025 --path out_lowgrade.jsonl
"""

import argparse
import json
import random
from typing import List, Dict, Any, Tuple, Optional

# ----------------------------- 定義 -----------------------------
QUADRANTS = {
    "つくるしごと": ["たべものや・おかしや", "スライムや", "どうがクリエイタ"],
    "うごかすしごと": ["カジノ", "ぎんこう", "なんでもや"],
    "つたえるしごと": ["たいかいうんえい", "ジャーナリスト", "けんきゅういん"],
    "たすけるしごと": ["パトロール", "人さがし"],
}
ALL_JOBS = [job for jobs in QUADRANTS.values() for job in jobs]
JOB2QUAD = {job: quad for quad, jobs in QUADRANTS.items() for job in jobs}

QUAD_POOLS = {
    "つくるしごと": {
        "did": ["アイデアを出してものをつくった", "さいごまでつくりきった"],
        "enjoy": ["じぶんのアイデアがうまくいったとき", "できあがったものを見せたとき"],
        "diff": ["思ったとおりにできなかった", "時間の中でおわらせるのがたいへんだった"],
    },
    "うごかすしごと": {
        "did": ["ルールをまもってうごけた", "おきゃくさんにきちんとおかねをわたせた"],
        "enjoy": ["まちの人とやりとりしたとき", "みんなで協力してうまくいったとき"],
        "diff": ["あわててまちがえた", "ルールをおぼえるのがたいへんだった"],
    },
    "つたえるしごと": {
        "did": ["はなしてつたえることができた", "人の話をよく聞いてまとめた"],
        "enjoy": ["グラフや写真がうまくできたとき", "みんなが分かりやすいと言ってくれたとき"],
        "diff": ["メモをとるのがたいへんだった", "まとめる時間がたりなかった"],
    },
    "たすけるしごと": {
        "did": ["こまっている人を見つけて声をかけた", "まちをきれいにした"],
        "enjoy": ["「ありがとう」と言われたとき", "まちがきれいになったとき"],
        "diff": ["どこを見回ればいいか分からなかった", "まちを全部回りきれなかった"],
    },
}

CHALLENGE_CARDS = [
    "にこにこであいさつ", "ありがとうを言う", "まえにでてはなす", "しゅうちゅうしてはたらく",
    "さいごまでやりとげる", "アイデアを出す", "なかまとそうだんする", "じかんをまもる",
    "まわりをてつだう", "しっぱいしてもやりなおす",
]

# ----------------------------- ユーティリティ -----------------------------
def pick_n(items: List[str], n_range: Tuple[int, int]) -> List[str]:
    n = random.randint(*n_range)
    n = min(n, len(items))
    return random.sample(items, k=n)

def pick_one(items: List[str]) -> str:
    return random.choice(items)

def pick_cards(n_max: int = 3) -> List[str]:
    n = random.randint(1, n_max)
    return random.sample(CHALLENGE_CARDS, k=n)

# ----------------------------- 1件生成 -----------------------------
def generate_one() -> Dict[str, Any]:
    job = random.choice(ALL_JOBS)
    quad = JOB2QUAD[job]
    pool = QUAD_POOLS[quad]

    data: Dict[str, Any] = {
        "grade": random.choice(["小1", "小2"]),  # 小1/小2をランダム
        "shop": job,
        "minutes": random.choice([20, 25, 30, 35, 40]),
        "rounds": random.randint(1, 3),
        "activity": "大人のお仕事を聞き、4種に分類してグラフ作成" if job == "けんきゅういん" else "お店のしごとを体験した",
        "q1_did": pick_n(pool["did"], (1, 2)),
        "q2_enjoyed": pick_n(pool["enjoy"], (1, 2)),
        "q3_diff": pick_one(pool["diff"]),
        "q4_next_quadrant": random.choice(list(QUADRANTS.keys())),
        "challenge_cards": pick_cards(3),
    }
    return data

def generate_many(n: int) -> List[Dict[str, Any]]:
    return [generate_one() for _ in range(n)]

# ----------------------------- 出力 -----------------------------
def dumps_jsonl(rows: List[Dict[str, Any]]) -> str:
    # ensure_ascii=False で日本語をそのまま、各行が1 JSON
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)

def write_jsonl_file(rows: List[Dict[str, Any]], path: str) -> None:
    # 文字コードは UTF-8（BOM なし）、改行は \n 固定
    text = dumps_jsonl(rows) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

# ----------------------------- CLI -----------------------------
def main():
    parser = argparse.ArgumentParser(description="こどものまち 低学年向け JSONLデータジェネレータ（小1/小2ランダム, UTF-8保存対応）")
    parser.add_argument("--n", type=int, default=5, help="生成件数")
    parser.add_argument("--seed", type=int, default=None, help="乱数シード")
    parser.add_argument("--path", type=str, default=None, help="保存先パス（指定なしで標準出力）")
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    rows = generate_many(args.n)

    if args.path:
        write_jsonl_file(rows, args.path)
        print(f"JSONLを書き出しました（UTF-8）: {args.path}")
    else:
        # 標準出力
        print(dumps_jsonl(rows))

if __name__ == "__main__":
    main()
