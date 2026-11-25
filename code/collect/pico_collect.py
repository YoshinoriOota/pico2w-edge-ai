"""データ収集用: Pico を「撮影専用機」にするスクリプト (Pico 側).

USB シリアル経由の簡単なテキストコマンドで動く撮影サーバ。
PC 側ツール (collect_tool.py) と対になる。

使い方 (書籍第7章):
  1. ov7670.py と本ファイルを Pico に転送し、本ファイルは main.py という
     名前で保存する (電源投入で自動起動させるため)
  2. Thonny を閉じてポートを空け、PC 側で collect_tool.py を実行する

プロトコル (1行コマンド → 応答):
  PING             -> "PONG"
  SNAP             -> "FRAME <バイト数>" + 生RGB565データ + "DONE"
  QUIT             -> "BYE" を返してスクリプト終了 (REPL に戻る)
"""

import sys

from ov7670 import OV7670, FRAME_BYTES


def main():
    cam = OV7670()
    cam.init_qqvga_rgb565()
    buf = bytearray(FRAME_BYTES)
    print("READY")

    while True:
        line = sys.stdin.readline()
        if not line:
            continue
        cmd = line.strip()

        if cmd == "SNAP":
            try:
                cam.capture(buf)
            except Exception as e:
                print("ERROR %s" % e)
                continue
            print("FRAME %d" % len(buf))
            sys.stdout.buffer.write(buf)
            print("\nDONE")
        elif cmd == "PING":
            print("PONG")
        elif cmd == "QUIT":
            print("BYE")
            break


main()
