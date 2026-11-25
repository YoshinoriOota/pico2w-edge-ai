"""V1 検証スクリプト: MicroPython PIO+DMA による OV7670 フレーム取り込み.

技術検証ポイント.md の V1 チェックリストを上から順に実機で確認し、
結果をレポート形式で表示する。最後に取得フレームを /frame.raw に保存する。

実行方法 (PC 側)::

    .venv/bin/mpremote cp code/ov7670_pio/ov7670.py :ov7670.py
    .venv/bin/mpremote run code/ov7670_pio/v1_capture_test.py
    .venv/bin/mpremote cp :frame.raw frame.raw

事前に ov7670.py を Pico へ転送しておくこと (上記 1 行目)。
"""

import gc
import time
from machine import Pin

from ov7670 import OV7670, FRAME_BYTES

RESULTS = []


def check(name, func):
    """検証項目を 1 つ実行し、結果を記録・表示する."""
    try:
        detail = func()
        RESULTS.append((name, True, detail))
        print("[OK] %s: %s" % (name, detail))
        return True
    except Exception as e:
        RESULTS.append((name, False, repr(e)))
        print("[NG] %s: %r" % (name, e))
        return False


def count_edges(pin, ms):
    """pin のエッジ数を ms ミリ秒間ポーリングで数える (信号疎通の簡易確認)."""
    n = 0
    last = pin.value()
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < ms:
        v = pin.value()
        if v != last:
            n += 1
            last = v
    return n


def frame_sanity(buf):
    """フレームが「それらしい」かの簡易チェック (全0/全同値を弾く)."""
    lo = 255
    hi = 0
    # 全画素は重いので 512 バイトおきにサンプリング
    for i in range(0, len(buf), 512):
        b = buf[i]
        if b < lo:
            lo = b
        if b > hi:
            hi = b
    if hi == lo:
        raise ValueError("all bytes identical (0x%02X)" % hi)
    return "byte range 0x%02X-0x%02X" % (lo, hi)


def main():
    print("=== V1: OV7670 PIO+DMA フレーム取り込み検証 ===")
    gc.collect()
    mem_start = gc.mem_free()
    print("初期ヒープ空き: %d byte" % mem_start)

    # V1-1: XCLK 供給 + SCCB 疎通 (ID 読み出しには XCLK が必要なため同時に検証される)
    cam = None

    def v1_1():
        nonlocal cam
        cam = OV7670()
        pid, ver = cam.probe()
        if pid != 0x76:
            raise ValueError("PID=0x%02X (expected 0x76)" % pid)
        return "PID=0x%02X VER=0x%02X (XCLK供給+SCCB疎通OK)" % (pid, ver)

    if not check("V1-1 XCLK(PWM)+SCCB デバイスID", v1_1):
        print("=== 中断: 配線または XCLK を確認してください ===")
        return

    # V1-2: QQVGA RGB565 レジスタ初期化
    check("V1-2 レジスタ初期化(QQVGA RGB565, CLKRC=0x03)",
          lambda: (cam.init_qqvga_rgb565(clkrc=0x03), "done")[1])

    # V1-3: VSYNC/PCLK 信号の疎通 (エッジが観測できるか)
    check("V1-3 VSYNC 信号疎通",
          lambda: "%d edges/300ms" % count_edges(cam.vsync_pin, 300))

    # V1-4: フレームバッファ確保とヒープ残量
    buf = None

    def v1_4():
        nonlocal buf
        gc.collect()
        before = gc.mem_free()
        buf = bytearray(FRAME_BYTES)
        gc.collect()
        after = gc.mem_free()
        return "buf=%d byte 確保, ヒープ残 %d byte (確保前 %d)" % (
            FRAME_BYTES, after, before)

    check("V1-4 フレームバッファ確保", v1_4)

    # V1-5: PIO+DMA で 3 フレーム連続取り込み (再現性)
    def v1_5():
        times = []
        for _ in range(3):
            times.append(cam.capture(buf))
        return "3フレーム取得, 所要 %s ms" % times

    if not check("V1-5 PIO+DMA フレーム取り込み x3", v1_5):
        print("=== 中断: PCLK/HREF/D0-D7 の配線を確認してください ===")
        return

    # V1-6: フレーム内容の簡易サニティ
    check("V1-6 フレーム内容サニティ", lambda: frame_sanity(buf))

    # V1-7: /frame.raw へ保存 (PC 転送用)
    def v1_7():
        with open("frame.raw", "wb") as f:
            f.write(buf)
        return "frame.raw (%d byte) 保存" % len(buf)

    check("V1-7 frame.raw 保存", v1_7)

    # --- サマリ ---
    print("=== サマリ ===")
    ok = sum(1 for _, s, _ in RESULTS if s)
    for name, success, _ in RESULTS:
        print("  %s %s" % ("OK" if success else "NG", name))
    print("%d/%d 項目成功" % (ok, len(RESULTS)))
    print("次: mpremote cp :frame.raw frame.raw して convert_frame.py で画像確認")


main()
