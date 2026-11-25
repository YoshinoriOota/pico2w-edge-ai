"""電池駆動エッジAIカメラ — 完成形 main.py (書籍 第10〜11章).

起動 (= deepsleep 復帰のリセット) ごとに 1 サイクルを実行する:
  脱出ハッチ → 撮影 → 前処理 → 推論 → 判定が変化していたら通知 → deepsleep

Pico のフラッシュに以下を配置して使う:
  main.py (本ファイル) / ov7670.py / dnnrt_loader.py / preprocess.py /
  notify.py / wifi_config.py / model.nnb

CLASSES はモデルの学習時のクラス割り当て (make_nnc_dataset.py の表示,
フォルダ名昇順) に合わせて書き換えること。
"""

import time

import machine

# ---- 設定 ----
INTERVAL_MIN = 10            # 撮影間隔 [分]
GRACE_SEC = 5                # 脱出ハッチ: 起動直後の待機 [秒]
CLASSES = ["box", "empty"]   # クラス番号 → 名前 (学習時の割り当てに合わせる)
NOTIFY_CLASS = 0             # このクラスに変化したとき通知する (box=荷物あり)
THRESHOLD = 0.8              # 確度がこれ未満の判定は「不明」として無視する
STATE_FILE = "last_state.txt"

# ---- 脱出ハッチ (この間に Ctrl+C すれば REPL に戻れる) ----
time.sleep(GRACE_SEC)

import dnnrt_loader
from ov7670 import OV7670, FRAME_BYTES
from preprocess import preprocess
from notify import send_udp


def read_last_state():
    try:
        with open(STATE_FILE) as f:
            return int(f.read())
    except (OSError, ValueError):
        return -1  # 初回


def write_last_state(state):
    with open(STATE_FILE, "w") as f:
        f.write(str(state))


def run_once():
    cam = OV7670()
    cam.init_qqvga_rgb565()
    frame = bytearray(FRAME_BYTES)
    model = dnnrt_loader.load_model("model.nnb")
    fvec = [0.0] * (28 * 28)

    cam.capture(frame)
    preprocess(frame, fvec)
    model.set_input(0, fvec)
    model.forward()
    out = model.get_output(0)

    best = 0
    for i in range(len(out)):
        if out[i] > out[best]:
            best = i

    if out[best] < THRESHOLD:
        print("uncertain: class=%d p=%.3f -> 判定保留" % (best, out[best]))
        return  # 自信のない判定では状態を更新しない (誤通知の抑制)

    prev = read_last_state()
    print("judge: %s (p=%.3f) prev=%d" % (CLASSES[best], out[best], prev))

    if best != prev:
        message = "%s p=%.2f" % (CLASSES[best], out[best])
        ok = send_udp(message)
        print("notify:", "sent" if ok else "failed (次サイクルに任せる)")
        if ok or prev != -1:
            # 送信失敗時も状態は更新する (毎サイクル再送で電池を溶かさない)
            write_last_state(best)

    # カメラを休止させる (XCLK 停止。deepsleep で PWM も止まるが明示しておく)
    cam.deinit()


try:
    run_once()
except Exception as e:
    # 現場での想定外エラーは記録だけして眠る (次サイクルで再挑戦)
    print("error:", e)

machine.deepsleep(INTERVAL_MIN * 60 * 1000)
