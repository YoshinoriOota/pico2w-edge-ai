"""通知: Wi-Fi を「送るときだけ」使う UDP 送信 (Pico側、書籍 10.5).

- 接続 → 送信 → 切断を 1 関数に閉じ込める
- finally で wlan.active(False) を保証する (消し忘れ = 29mA の罠を構造で封じる)
- 接続に失敗したら諦めて False を返す (次の起床サイクルに任せる)

wifi_config.py (Pico 上にのみ置く。リポジトリに入れない) に以下を定義:
    SSID = "..."
    PSK  = "..."
    DEST = "192.168.x.x"   # 通知の宛先 (notify_server.py を動かす PC など)
    PORT = 9999
"""

import socket
import time

import network
import wifi_config


def send_udp(message, timeout_s=15):
    """Wi-Fi に接続して UDP で message を送り、必ず切断する.

    :return: 送信できたら True、接続失敗なら False
    """
    wlan = network.WLAN(network.STA_IF)
    try:
        wlan.active(True)
        wlan.connect(wifi_config.SSID, wifi_config.PSK)
        for _ in range(timeout_s * 10):
            if wlan.isconnected():
                break
            time.sleep_ms(100)
        else:
            return False
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.sendto(message.encode(), (wifi_config.DEST, wifi_config.PORT))
        finally:
            s.close()
        # sendto は「送信キューへの受付」であり、実際に電波になるまで
        # 数十ms かかる。すぐ active(False) するとキュー上のパケットごと
        # チップを止めてしまい、通知が静かに消える (実機で確認したハマり)
        time.sleep_ms(300)
        return True
    finally:
        wlan.active(False)  # 成功でも失敗でも例外でも、必ず消灯する
