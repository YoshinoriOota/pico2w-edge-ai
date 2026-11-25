"""収集した画像フォルダを NNC のデータセット形式 (CSV) に整形する.

collect_tool.py の出力フォルダ (クラス別サブフォルダ構成) を読み、
NNC に登録できる学習用/評価用 CSV を生成する。

  dataset/
  ├── empty/  empty_0000.png ...     ← クラス0 (フォルダ名昇順でラベル番号が決まる)
  ├── box/    box_0000.png ...       ← クラス1
  ├── _full/                          ← 先頭が _ のフォルダは無視
  ├── nnc_training.csv               ← 生成物 (80%)
  └── nnc_validation.csv             ← 生成物 (20%)

CSV は NNC の仕様に合わせ、1列目 x:image に画像の相対パス、
2列目 y:label にクラス番号 (0始まり) を書く。

使い方:
  python make_nnc_dataset.py dataset
  python make_nnc_dataset.py dataset --split 0.9   # 学習9割に変更
"""

import argparse
import csv
import os
import random


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("root", help="collect_tool.py の --out で指定したフォルダ")
    p.add_argument("--split", type=float, default=0.8,
                   help="学習に回す割合 (既定 0.8)")
    p.add_argument("--seed", type=int, default=1,
                   help="シャッフルの乱数シード (再現性のため固定)")
    args = p.parse_args()

    classes = sorted(
        d for d in os.listdir(args.root)
        if os.path.isdir(os.path.join(args.root, d)) and not d.startswith("_")
    )
    if len(classes) < 2:
        raise SystemExit("クラスフォルダが2つ以上必要です (見つかった: %s)" % classes)

    print("クラス番号の割り当て (フォルダ名昇順):")
    rows = []
    for label, cls in enumerate(classes):
        files = sorted(
            f for f in os.listdir(os.path.join(args.root, cls))
            if f.endswith(".png")
        )
        print("  %d: %-12s %4d枚" % (label, cls, len(files)))
        rows += [("./%s/%s" % (cls, f), label) for f in files]

    random.seed(args.seed)
    random.shuffle(rows)
    n_train = int(len(rows) * args.split)

    for name, subset in (("nnc_training.csv", rows[:n_train]),
                         ("nnc_validation.csv", rows[n_train:])):
        path = os.path.join(args.root, name)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["x:image", "y:label"])
            w.writerows(subset)
        print("生成: %s (%d行)" % (path, len(subset)))

    print("NNC への登録: データセット画面の「アクション」→ CSV を開く")


if __name__ == "__main__":
    main()
