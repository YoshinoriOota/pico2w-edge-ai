"""V3 検証用: 消費電流測定のための状態保持モジュール.

各関数は 1 つの電力状態を無限（または時限）に保持する。PC 側から

    mpremote exec --no-follow "import v3_states; v3_states.state_infer()"

のように起動し、USB 電流計の表示を目視で読み取る。次の状態へ移る際は
次の mpremote exec が自動的に前のループを中断する。

Wi-Fi 認証情報は Pico 上の wifi_config.py (SSID / PSK) から読む。
このファイルはリポジトリに含めない (実機にのみ配置する)。
"""

import time


def state_infer():
    """状態2: 撮影 + 前処理 + 推論を連続実行し続ける."""
    import dnnrt_loader
    from ov7670 import OV7670, FRAME_BYTES

    cam = OV7670()
    cam.init_qqvga_rgb565()
    frame = bytearray(FRAME_BYTES)
    model = dnnrt_loader.load_model("model.nnb")
    gray = bytearray(28 * 28)
    fvec = [0.0] * (28 * 28)
    print("state_infer: loop start")
    while True:
        cam.capture(frame)
        _preprocess(frame, gray, fvec)
        model.set_input(0, fvec)
        model.forward()
        model.get_output(0)


def state_camera_idle(xclk_on=True):
    """状態3: カメラ初期化済みでアイドル (xclk_on=False で XCLK 停止)."""
    from ov7670 import OV7670

    cam = OV7670()
    cam.init_qqvga_rgb565()
    if not xclk_on:
        cam._pwm.deinit()
    print("state_camera_idle: xclk_on=%s" % xclk_on)
    while True:
        time.sleep_ms(100)


def state_wifi():
    """状態4: Wi-Fi 接続を維持し UDP パケットを送信し続ける (10Hz)."""
    import network
    import socket
    import wifi_config

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(wifi_config.SSID, wifi_config.PSK)
    for _ in range(30):
        if wlan.isconnected():
            break
        time.sleep(1)
    if not wlan.isconnected():
        print("state_wifi: 接続失敗")
        return
    ip = wlan.ifconfig()[0]
    print("state_wifi: connected %s" % ip)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = b"v3-current-test " * 4   # 64 byte
    dest = (ip.rsplit(".", 1)[0] + ".255", 9999)  # 同一セグメントへブロードキャスト
    while True:
        s.sendto(payload, dest)
        time.sleep_ms(100)


def state_lightsleep(sleep_s=20, awake_s=5, cycles=5):
    """状態5: lightsleep(sleep_s) と通常動作(awake_s) を交互に繰り返す.

    スリープ中は USB シリアルが応答しなくなる。読み取りはスリープ区間
    (長い方) で行うこと。cycles 回で自動終了し REPL に戻る。
    """
    import machine

    print("state_lightsleep: %ds sleep / %ds awake x%d" % (sleep_s, awake_s, cycles))
    time.sleep(3)  # この print がホストへ届く猶予
    for i in range(cycles):
        machine.lightsleep(sleep_s * 1000)
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < awake_s * 1000:
            time.sleep_ms(50)
    print("state_lightsleep: done")


def _preprocess(buf, gray_out, float_out):
    """160x120 RGB565 の中央 112x112 を 28x28 グレースケール化 (V2 と同一)."""
    k = 0
    for j in range(28):
        row = (4 + j * 4) * 160
        for i in range(28):
            idx = (row + 24 + i * 4) * 2
            v = (buf[idx] << 8) | buf[idx + 1]
            r = (v >> 8) & 0xF8
            g = (v >> 3) & 0xFC
            b = (v << 3) & 0xF8
            gray = (r + g + g + b) >> 2
            gray_out[k] = gray
            float_out[k] = gray / 255.0
            k += 1
