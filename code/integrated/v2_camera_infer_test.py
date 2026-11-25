"""V2 残検証スクリプト: カメラ + DNNRT 同時動作のメモリ・時間実測.

「起動 → 撮影 → 前処理 → 推論」の一気通貫を実機で 3 サイクル実行し、
各段階のヒープ残量と所要時間を計測する。認識結果の妥当性は問わない
(model.nnb は手書き数字系の 11 クラス分類器であり、カメラの被写体とは
無関係のため)。目的はメモリ成立と時間の実測のみ。

事前条件 (Pico ファイルシステム上):
  - ov7670.py       : code/ov7670_pio/ov7670.py
  - model.nnb       : code/dnnrt_port/resource/model.nnb (28x28 gray, 11クラス)
  - dnnrt_loader.py : code/dnnrt_upy/lib/dnnrt_loader.py

実行方法 (PC 側)::

    .venv/bin/mpremote run code/integrated/v2_camera_infer_test.py
    .venv/bin/mpremote cp :pre.raw pre.raw   # 前処理結果 (28x28 gray) の回収
"""

import gc
import time

import dnnrt
import dnnrt_loader
from ov7670 import OV7670, FRAME_BYTES, FRAME_W, FRAME_H

# 前処理: 160x120 の中央 112x112 を 4 画素間引きで 28x28 に縮小する
CROP = const(112)
STRIDE = const(4)
DST = const(28)
X0 = (FRAME_W - CROP) // 2   # 24 (const() は import 値を含む式に使えない)
Y0 = (FRAME_H - CROP) // 2   # 4


def mem(label):
    """gc 後のヒープ空きを表示して値を返す."""
    gc.collect()
    free = gc.mem_free()
    print("  [mem] %-28s: %6d byte free" % (label, free))
    return free


def preprocess(buf, gray_out, float_out):
    """RGB565 フレームを 28x28 グレースケールに縮小し 0.0-1.0 に正規化する.

    :param buf: QQVGA RGB565 フレーム (38400 byte)
    :param gray_out: 784 byte の bytearray (PC 確認用の 8bit グレー画像)
    :param float_out: 784 要素の list (dnnrt set_input へ渡す)
    """
    k = 0
    for j in range(DST):
        row = (Y0 + j * STRIDE) * FRAME_W
        for i in range(DST):
            idx = (row + X0 + i * STRIDE) * 2
            v = (buf[idx] << 8) | buf[idx + 1]
            r = (v >> 8) & 0xF8          # 5bit → 8bit 近似
            g = (v >> 3) & 0xFC          # 6bit → 8bit 近似
            b = (v << 3) & 0xF8
            gray = (r + g + g + b) >> 2  # 輝度近似 (G を 2 倍重み)
            gray_out[k] = gray
            float_out[k] = gray / 255.0
            k += 1


def main():
    print("=== V2残: カメラ + DNNRT 同時動作検証 ===")
    m_start = mem("起動直後")

    # --- 実アプリと同じ順序で初期化: カメラ → フレームバッファ → モデル ---
    cam = OV7670()
    cam.init_qqvga_rgb565()
    mem("カメラ初期化後")

    frame = bytearray(FRAME_BYTES)
    mem("フレームバッファ確保後")

    model = dnnrt_loader.load_model("model.nnb")
    m_ready = mem("model.nnb ロード+コンテキスト後")

    in_shape = model.input_shape(0)
    print("  model input: %s / output: %s" % (in_shape, model.output_shape(0)))
    assert in_shape == (1, 1, 28, 28), "想定外の入力形状"

    gray = bytearray(DST * DST)
    fvec = [0.0] * (DST * DST)
    mem("前処理バッファ確保後")

    # --- 撮影 → 前処理 → 推論 を 3 サイクル ---
    for cycle in range(3):
        t0 = time.ticks_ms()
        cam.capture(frame)
        t1 = time.ticks_ms()
        preprocess(frame, gray, fvec)
        t2 = time.ticks_ms()
        model.set_input(0, fvec)
        model.forward()
        t3 = time.ticks_ms()
        out = model.get_output(0)
        t4 = time.ticks_ms()

        best = 0
        for i in range(len(out)):
            if out[i] > out[best]:
                best = i
        print("cycle %d: 撮影 %dms / 前処理 %dms / 推論 %dms / 出力取得 %dms"
              " -> class %d (%.3f)" % (
                  cycle,
                  time.ticks_diff(t1, t0),
                  time.ticks_diff(t2, t1),
                  time.ticks_diff(t3, t2),
                  time.ticks_diff(t4, t3),
                  best, out[best]))

    m_end = mem("3サイクル完了後")

    # --- 前処理結果を PC 確認用に保存 ---
    with open("pre.raw", "wb") as f:
        f.write(gray)
    print("pre.raw (784 byte, 28x28 gray) 保存")

    # --- 判定 ---
    print("=== 判定 ===")
    print("カメラ+モデル同時確保後のヒープ残: %d byte" % m_ready)
    print("3サイクル後のヒープ残          : %d byte (リークなしなら同水準)" % m_end)
    total = time.ticks_diff(t4, t0)
    print("1サイクル所要 (撮影込み)       : %d ms" % total)
    ok = m_ready > 100 * 1024 and total < 10_000
    print("成功基準 (ヒープ内完結・10秒以内): %s" % ("達成" if ok else "未達"))


main()
