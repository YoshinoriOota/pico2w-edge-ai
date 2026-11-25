"""通知の受け皿: UDP 受信サーバ (PC 側、書籍 第11章).

Pico からの通知を受けて、時刻付きで表示・ログファイルに記録する。
常時起動している PC・ラズパイ・NAS などで動かしておく。

使い方:
    python notify_server.py                # ポート9999で待ち受け
    python notify_server.py --port 9999 --log notify.log
"""

import argparse
import datetime
import socket


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=9999)
    p.add_argument("--log", default="notify.log")
    args = p.parse_args()

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", args.port))
    print("通知待ち受け中 (UDP :%d)  Ctrl+C で終了" % args.port, flush=True)

    while True:
        data, addr = s.recvfrom(1024)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = "[%s] %s %s" % (now, addr[0], data.decode(errors="replace"))
        print(line, flush=True)
        with open(args.log, "a") as f:
            f.write(line + "\n")


if __name__ == "__main__":
    main()
