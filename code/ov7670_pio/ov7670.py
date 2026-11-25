"""OV7670 カメラドライバ (MicroPython / Raspberry Pi Pico 2 W 用).

役割分担:
  - XCLK 供給      : machine.PWM (10MHz 以上を要求されるため PWM で生成)
  - SCCB (I2C互換) : machine.I2C (リピーテッドスタート非対応のため write→read の2段で読む)
  - フレーム取り込み: PIO + DMA (QQVGA 160x120 RGB565 = 38400 byte)

設計のポイント:
  COM10 レジスタで「HBLANK 中は PCLK を停止する」設定 (bit5) を有効にする。
  これにより PCLK が立ち上がる = データ有効となり、PIO 側は HREF を見ずに
  「PCLK 立ち上がりで 8bit 取り込む」だけの単純なプログラムで済む。
  フレーム先頭は VSYNC パルスの立ち下がりで同期する。

使用例::

    from ov7670 import OV7670, FRAME_BYTES
    cam = OV7670()                 # 既定ピン配置 (README.md 参照)
    buf = bytearray(FRAME_BYTES)
    cam.capture(buf)               # 1 フレーム取り込み
"""

import time
from machine import Pin, PWM, I2C
import rp2

#: SCCB スレーブアドレス (7bit)
SCCB_ADDR = const(0x21)

#: QQVGA RGB565 の 1 フレームのバイト数 (160*120*2)
FRAME_W = const(160)
FRAME_H = const(120)
FRAME_BYTES = const(FRAME_W * FRAME_H * 2)

# --- レジスタ番号 ---
_REG_PID = const(0x0A)   # プロダクトID (0x76 固定)
_REG_VER = const(0x0B)   # バージョン (0x73 固定)
_REG_COM7 = const(0x12)  # リセット / 出力フォーマット
_REG_CLKRC = const(0x11)  # 内部クロックプリスケーラ

# QQVGA (160x120) RGB565 設定テーブル
# ダウンサンプル(DCW)で VGA→1/4 に縮小する標準的な組み合わせ。
# 色調整系レジスタはデフォルトのまま (V1 検証は「画が取れること」が目的)。
_REGS_QQVGA_RGB565 = (
    (0x12, 0x04),  # COM7: RGB 出力
    (0x0C, 0x04),  # COM3: DCW イネーブル
    (0x3E, 0x1A),  # COM14: DCW/スケーリング PCLK 有効・手動・PCLK 1/4 分周
    (0x70, 0x3A),  # SCALING_XSC
    (0x71, 0x35),  # SCALING_YSC
    (0x72, 0x22),  # SCALING_DCWCTR: 水平・垂直とも 1/4 ダウンサンプル
    (0x73, 0xF2),  # SCALING_PCLK_DIV: DSP クロック 1/4 分周
    (0xA2, 0x02),  # SCALING_PCLK_DELAY
    (0x15, 0x20),  # COM10: HBLANK 中は PCLK 停止 (本ドライバの要)
    (0x40, 0xD0),  # COM15: RGB565・出力フルレンジ
    (0x3A, 0x04),  # TSLB: 出力シーケンス設定
    # 出力ウィンドウ (VGA 標準値)
    (0x17, 0x16),  # HSTART
    (0x18, 0x04),  # HSTOP
    (0x32, 0x24),  # HREF
    (0x19, 0x02),  # VSTRT
    (0x1A, 0x7A),  # VSTOP
    (0x03, 0x0A),  # VREF
)


def _make_capture_prog(pclk_gpio, href_gpio, vsync_gpio):
    """取り込み用 PIO プログラムを生成する (HREF 同期方式).

    VSYNC パルス (正極性) の立ち下がりでフレーム先頭に同期した後、
    行ごとに HREF の立ち上がりで再同期し、PCLK 立ち上がりごとに
    D0-D7 の 8bit を「1 行分きっかり」X レジスタでカウントして取り込む。
    ブランキング境界で余分な PCLK エッジが出ても行頭で必ず再同期される
    ため、行のバイトずれ (縞・斜めシアー) が起きない。

    1 行のバイト数-1 (QQVGA RGB565 なら 319) を、起動のたびにホスト側
    から TX FIFO 経由で渡すこと (capture() が行う)。

    SHIFT_RIGHT + autopush(32bit) により、取り込んだバイトは
    リトルエンディアンのメモリ上で時系列どおりに並ぶ。
    フレーム全体のバイト数の管理は DMA の転送カウントに任せる。
    """
    @rp2.asm_pio(
        in_shiftdir=rp2.PIO.SHIFT_RIGHT,
        autopush=True,
        push_thresh=32,
    )
    def prog():
        pull()                      # 1行のバイト数-1 をホストから受け取る
        mov(y, osr)
        wait(1, gpio, vsync_gpio)   # VSYNC パルス開始を待つ
        wait(0, gpio, vsync_gpio)   # 立ち下がり = フレーム先頭
        wrap_target()
        mov(x, y)                   # 行バイトカウンタをリロード
        wait(0, gpio, href_gpio)    # 前行の終わりを確認
        wait(1, gpio, href_gpio)    # 行頭に同期
        label("pix")
        wait(0, gpio, pclk_gpio)
        wait(1, gpio, pclk_gpio)    # PCLK 立ち上がり = データ有効
        in_(pins, 8)                # D0-D7 を取り込み
        jmp(x_dec, "pix")           # 1行分繰り返す
        wrap()

    return prog


class OV7670:
    """OV7670 の初期化とフレーム取り込みを行うドライバクラス."""

    def __init__(
        self,
        i2c_id=0,
        sda=0,
        scl=1,
        d0=2,          # D0-D7 は d0 から連続 8 本 (GP2-GP9)
        pclk=10,
        href=11,       # 本ドライバでは未使用 (COM10 で PCLK をゲート) だが配線は必要
        vsync=12,
        xclk=13,
        sm_id=0,
        xclk_freq=15_000_000,
        clkrc=0x03,    # 内部クロック = XCLK/(clkrc+1)。既定 15MHz/4 = 3.75MHz
    ):
        self._vsync_gpio = vsync
        self.vsync_pin = Pin(vsync, Pin.IN)

        # RP2350 では入力として初期化していないパッドは入力イネーブルが
        # 立たず PIO からも読めない。PIO が参照する全信号を明示的に入力化する
        self.pclk_pin = Pin(pclk, Pin.IN)
        self.href_pin = Pin(href, Pin.IN)
        self._data_pins = [Pin(d0 + i, Pin.IN) for i in range(8)]

        # --- XCLK 供給 (SCCB 通信にも XCLK が必要な点に注意) ---
        self._pwm = PWM(Pin(xclk), freq=xclk_freq, duty_u16=32768)
        time.sleep_ms(10)

        # --- SCCB (I2C) ---
        self._i2c = I2C(i2c_id, sda=Pin(sda), scl=Pin(scl), freq=100_000)

        # --- PIO ステートマシン ---
        self._sm_id = sm_id
        self._sm = rp2.StateMachine(
            sm_id, _make_capture_prog(pclk, href, vsync), in_base=Pin(d0, Pin.IN)
        )

        # --- DMA (PIO RX FIFO → フレームバッファ) ---
        pio_num = sm_id // 4
        sm_num = sm_id % 4
        rxf_addr = 0x5020_0000 + pio_num * 0x10_0000 + 0x020 + 4 * sm_num
        dreq_rx = pio_num * 8 + 4 + sm_num
        self._rxf_addr = rxf_addr
        self._dma = rp2.DMA()
        self._dma_ctrl = self._dma.pack_ctrl(
            size=2,            # 32bit 単位
            inc_read=False,    # 読み元は FIFO 固定
            inc_write=True,    # 書き先はバッファを進める
            treq_sel=dreq_rx,  # PIO RX の DREQ でペーシング
        )

    # ------------------------------------------------------------
    # SCCB アクセス
    # ------------------------------------------------------------

    def sccb_write(self, reg, val):
        """レジスタ reg に val を書き込む."""
        self._i2c.writeto(SCCB_ADDR, bytes([reg, val]))
        time.sleep_ms(1)

    def sccb_read(self, reg):
        """レジスタ reg を読み出す (SCCB は write→read の 2 段階)."""
        self._i2c.writeto(SCCB_ADDR, bytes([reg]))
        return self._i2c.readfrom(SCCB_ADDR, 1)[0]

    def probe(self):
        """デバイス ID を読み (PID, VER) のタプルで返す. 正常なら (0x76, 0x73)."""
        return (self.sccb_read(_REG_PID), self.sccb_read(_REG_VER))

    # ------------------------------------------------------------
    # 初期化
    # ------------------------------------------------------------

    def init_qqvga_rgb565(self, clkrc=None):
        """ソフトリセット後、QQVGA RGB565 設定を書き込む."""
        self.sccb_write(_REG_COM7, 0x80)  # ソフトリセット
        time.sleep_ms(50)
        if clkrc is None:
            clkrc = 0x03
        self.sccb_write(_REG_CLKRC, clkrc & 0x3F)
        for reg, val in _REGS_QQVGA_RGB565:
            self.sccb_write(reg, val)
        time.sleep_ms(300)  # AGC/AEC が落ち着くまで待つ

    # ------------------------------------------------------------
    # フレーム取り込み
    # ------------------------------------------------------------

    def capture(self, buf, timeout_ms=5000):
        """1 フレームを buf へ取り込む.

        :param buf: FRAME_BYTES バイト以上・4 の倍数長の bytearray
        :param timeout_ms: タイムアウト (PCLK/VSYNC が来ない場合の検出用)
        :return: 取り込みに要した時間 [ms]
        """
        n_words = len(buf) // 4

        self._sm.active(0)
        self._sm.restart()          # プログラム先頭 (行バイト数待ち) に戻す
        while self._sm.rx_fifo():   # 前回の残りを捨てる
            self._sm.get()
        self._sm.put(FRAME_W * 2 - 1)  # 1行のバイト数-1 (QQVGA RGB565: 319)

        self._dma.config(
            read=self._rxf_addr,
            write=buf,
            count=n_words,
            ctrl=self._dma_ctrl,
            trigger=True,
        )
        t0 = time.ticks_ms()
        self._sm.active(1)

        while self._dma.active():
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                self._sm.active(0)
                self._dma.active(0)
                raise RuntimeError(
                    "capture timeout: VSYNC/PCLK が届いていない可能性 "
                    "(配線・XCLK・レジスタ設定を確認)"
                )
        elapsed = time.ticks_diff(time.ticks_ms(), t0)
        self._sm.active(0)
        return elapsed

    def deinit(self):
        """PWM/DMA/ステートマシンを解放する."""
        self._sm.active(0)
        self._dma.close()
        self._pwm.deinit()
