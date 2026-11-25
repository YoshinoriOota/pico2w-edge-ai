"""frame.raw (QQVGA RGB565) を PNG に変換して目視確認する PC 側ツール.

使い方::

    .venv/bin/python code/ov7670_pio/pc/convert_frame.py frame.raw
    # → frame.png (3倍拡大) が生成される

色がおかしい場合はバイト順を入れ替えて試す::

    .venv/bin/python code/ov7670_pio/pc/convert_frame.py frame.raw --swap
"""

import argparse
import sys

from PIL import Image


def rgb565_to_image(raw, width, height, swap=False):
    """RGB565 生データを PIL Image に変換する."""
    expected = width * height * 2
    if len(raw) != expected:
        sys.exit(f"サイズ不一致: {len(raw)} byte (期待値 {expected} byte)")

    img = Image.new("RGB", (width, height))
    px = img.load()
    for y in range(height):
        row = y * width * 2
        for x in range(width):
            i = row + x * 2
            hi, lo = raw[i], raw[i + 1]
            if swap:
                hi, lo = lo, hi
            v = (hi << 8) | lo
            r = (v >> 11) & 0x1F
            g = (v >> 5) & 0x3F
            b = v & 0x1F
            # 5/6bit → 8bit へ拡張
            px[x, y] = ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))
    return img


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", help="frame.raw のパス")
    p.add_argument("-o", "--output", default=None, help="出力 PNG パス")
    p.add_argument("--width", type=int, default=160)
    p.add_argument("--height", type=int, default=120)
    p.add_argument("--swap", action="store_true", help="RGB565 のバイト順を入れ替える")
    p.add_argument("--scale", type=int, default=3, help="拡大率 (既定 3 倍)")
    args = p.parse_args()

    with open(args.input, "rb") as f:
        raw = f.read()

    img = rgb565_to_image(raw, args.width, args.height, swap=args.swap)
    if args.scale > 1:
        img = img.resize((args.width * args.scale, args.height * args.scale),
                         Image.NEAREST)

    out = args.output or args.input.rsplit(".", 1)[0] + ".png"
    img.save(out)
    print(f"保存しました: {out} ({img.width}x{img.height})")


if __name__ == "__main__":
    main()
