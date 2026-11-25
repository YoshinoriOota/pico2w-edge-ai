"""データ収集用: PC 側の受信・保存ツール.

Pico 側の撮影サーバ (pico_collect.py を main.py として配置) と対話し、
撮影画像をクラス別フォルダに PNG で保存する。

保存されるもの (1 ショットにつき):
  <out>/<class>/<class>_NNNN.png        : 28x28 グレースケール (NNC 学習用)
  <out>/_full/<class>_NNNN.png          : 160x120 カラー (確認用, --save-full 時)

28x28 への縮小は、Pico 実機の推論時前処理 (中央112x112 を 4画素間引き +
グレースケール化) と完全に同一のロジックで行う。
「学習と推論の前処理を揃える」ための最重要ポイント (書籍 7.3 節)。

使い方:
  対話モード (Enterで1枚撮影、クラス名入力で切替、q で終了):
    python collect_tool.py --port /dev/ttyACM0 --out dataset --class-name box
  自動モード (定点で一定間隔の連続撮影):
    python collect_tool.py --port /dev/ttyACM0 --out dataset \
        --class-name empty --auto 100 --interval 5
"""

import argparse
import os
import sys
import time

import serial
from PIL import Image

FRAME_W, FRAME_H = 160, 120
FRAME_BYTES = FRAME_W * FRAME_H * 2
# Pico 側 (第9章の推論前処理) と同一のパラメータ
CROP, STRIDE, DST = 112, 4, 28
X0, Y0 = (FRAME_W - CROP) // 2, (FRAME_H - CROP) // 2


def open_camera(port, do_reset=True):
    """シリアルを開き、Pico の撮影サーバと疎通確認する."""
    ser = serial.Serial(port, 115200, timeout=3)
    if do_reset:
        # 実行中のプログラムを中断し、ソフトリセットで main.py を再起動する
        ser.write(b"\x03\x03")
        time.sleep(0.5)
        ser.reset_input_buffer()
        ser.write(b"\x04")
        _wait_line(ser, b"READY", timeout=10)
    ser.reset_input_buffer()
    ser.write(b"PING\n")
    if not _wait_line(ser, b"PONG", timeout=3):
        sys.exit("Pico が応答しません。main.py (pico_collect.py) を確認してください")
    return ser


def _wait_line(ser, keyword, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        line = ser.readline()
        if keyword in line:
            return True
    return False


def snap(ser):
    """1 フレーム撮影し、生 RGB565 バイト列を返す."""
    ser.reset_input_buffer()
    ser.write(b"SNAP\n")
    while True:
        line = ser.readline()
        if not line:
            raise RuntimeError("応答なし (タイムアウト)")
        if line.startswith(b"ERROR"):
            raise RuntimeError(line.decode().strip())
        if line.startswith(b"FRAME"):
            n = int(line.split()[1])
            break
    raw = b""
    while len(raw) < n:
        chunk = ser.read(n - len(raw))
        if not chunk:
            raise RuntimeError("データが途中で途切れました (%d/%d)" % (len(raw), n))
        raw += chunk
    return raw


def rgb565_to_full_image(raw):
    """160x120 のカラー画像 (確認用) に変換する."""
    img = Image.new("RGB", (FRAME_W, FRAME_H))
    px = img.load()
    for y in range(FRAME_H):
        row = y * FRAME_W * 2
        for x in range(FRAME_W):
            i = row + x * 2
            v = (raw[i] << 8) | raw[i + 1]
            r, g, b = (v >> 11) & 0x1F, (v >> 5) & 0x3F, v & 0x1F
            px[x, y] = ((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2))
    return img


def rgb565_to_28x28_gray(raw):
    """Pico 側推論と同一の前処理で 28x28 グレースケールに変換する."""
    img = Image.new("L", (DST, DST))
    px = img.load()
    for j in range(DST):
        row = (Y0 + j * STRIDE) * FRAME_W
        for i in range(DST):
            idx = (row + X0 + i * STRIDE) * 2
            v = (raw[idx] << 8) | raw[idx + 1]
            r = (v >> 8) & 0xF8
            g = (v >> 3) & 0xFC
            b = (v << 3) & 0xF8
            px[i, j] = (r + g + g + b) >> 2
    return img


def next_index(class_dir, class_name):
    """クラスフォルダ内の連番の次の番号を返す."""
    n = 0
    if os.path.isdir(class_dir):
        for f in os.listdir(class_dir):
            if f.startswith(class_name + "_") and f.endswith(".png"):
                try:
                    n = max(n, int(f[len(class_name) + 1:-4]) + 1)
                except ValueError:
                    pass
    return n


def save_shot(raw, out_dir, class_name, save_full):
    class_dir = os.path.join(out_dir, class_name)
    os.makedirs(class_dir, exist_ok=True)
    idx = next_index(class_dir, class_name)
    name = "%s_%04d.png" % (class_name, idx)

    rgb565_to_28x28_gray(raw).save(os.path.join(class_dir, name))
    if save_full:
        full_dir = os.path.join(out_dir, "_full")
        os.makedirs(full_dir, exist_ok=True)
        rgb565_to_full_image(raw).save(os.path.join(full_dir, name))
    return os.path.join(class_dir, name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", required=True, help="例: /dev/ttyACM0, COM5")
    p.add_argument("--out", default="dataset", help="保存先フォルダ")
    p.add_argument("--class-name", default="class0", help="撮影するクラス名")
    p.add_argument("--auto", type=int, default=0,
                   help="指定枚数を自動連続撮影する (0=対話モード)")
    p.add_argument("--interval", type=float, default=2.0,
                   help="自動撮影の間隔秒 (--auto 時)")
    p.add_argument("--save-full", action="store_true",
                   help="確認用の 160x120 カラー画像も保存する")
    p.add_argument("--no-reset", action="store_true",
                   help="接続時にソフトリセットしない (テスト用)")
    args = p.parse_args()

    ser = open_camera(args.port, do_reset=not args.no_reset)
    print("接続OK: %s" % args.port)

    if args.auto > 0:
        # 自動モード: 定点撮影
        for i in range(args.auto):
            path = save_shot(snap(ser), args.out, args.class_name, args.save_full)
            print("[%d/%d] %s" % (i + 1, args.auto, path))
            if i < args.auto - 1:
                time.sleep(args.interval)
    else:
        # 対話モード
        print("Enter=撮影 / 文字列=クラス切替 / q=終了  (現在: %s)" % args.class_name)
        cls = args.class_name
        while True:
            key = input("[%s] > " % cls).strip()
            if key == "q":
                break
            if key:
                cls = key
                print("クラスを切り替えました: %s" % cls)
                continue
            path = save_shot(snap(ser), args.out, cls, args.save_full)
            print("保存: %s" % path)

    ser.write(b"QUIT\n")
    ser.close()
    print("終了しました")


if __name__ == "__main__":
    main()
