# ov7670_pio — MicroPython PIO+DMA による OV7670 フレーム取り込み（V1検証）

技術検証ポイント V1（書籍第4章に対応）の検証用コード一式です。
QQVGA (160x120) RGB565 の 1 フレームを PIO+DMA で取り込み、PC で目視確認します。

## ファイル構成

```
ov7670_pio/
├── README.md            # 本ドキュメント
├── ov7670.py             # ドライバ (Pico に転送する)
├── v1_capture_test.py     # V1 検証スクリプト (mpremote run で実行)
├── pc/
│   └── convert_frame.py   # frame.raw → PNG 変換 (PC 側)
└── resource/
    ├── v1_test_report.md    # V1 実機検証レポート (2026-07-08, 7/7 成功)
    ├── sample_frame.raw     # 検証時の取得フレーム (回帰テスト用リファレンス)
    └── sample_frame.png     # 上記の PNG 変換結果
```

## 配線

| OV7670 ピン | Pico 2 W | 機能 |
|---|---|---|
| 3.3V | 3V3(OUT) | 電源（モジュールにレギュレータがある場合もまず 3.3V で） |
| GND | GND | グランド |
| SIOD | GP0 (I2C0 SDA) | SCCB データ |
| SIOC | GP1 (I2C0 SCL) | SCCB クロック |
| D0–D7 | GP2–GP9 | 画素データ（**連続 8 本・順番厳守**。PIO の in_base=GP2） |
| PCLK | GP10 | ピクセルクロック |
| HREF | GP11 | 行有効（行頭の再同期に使用） |
| VSYNC | GP12 | フレーム同期 |
| XCLK | GP13 (PWM) | 入力クロック 15MHz を PWM で供給（**配線は最短に**） |
| RESET | 3.3V | リセット解除（プルアップ済みモジュールは未接続可） |
| PWDN | GND | パワーダウン解除（プルダウン済みモジュールは未接続可） |

## 設計メモ

- PIO プログラムは **HREF 同期方式**（11 命令）: VSYNC 立ち下がりでフレーム
  同期した後、行ごとに HREF 立ち上がりで再同期し、X レジスタで 1 行きっかり
  320 byte をカウントして PCLK 立ち上がりごとに 8bit 取り込む。
  行頭で毎回再同期するため、ブランキング境界の余分な PCLK エッジがあっても
  行のバイトずれ（縞・斜めシアー）が起きない（v1_test_report.md 参照）。
- **COM10 (0x15) = 0x20**（HBLANK 中は PCLK 停止）も併用し、ブランキング中の
  無効クロックを減らしている。
- フレーム全体のバイト数の管理は DMA の転送カウント (38400 byte = 9600 ワード) に任せる。
- **RP2350 の注意**: PIO が参照するピンはすべて `Pin(n, Pin.IN)` で明示的に
  入力初期化すること。入力イネーブルが立っていないパッドは PIO から見えず、
  `wait(gpio)` が永遠に待つ（ドライバ内で対応済み。v1_test_report.md 参照）。
- クロック設計: XCLK 15MHz (PWM) → CLKRC 1/4 → COM14/SCALING_PCLK_DIV 1/4
  → PCLK ≒ 0.94MHz。1 フレーム約 41ms + ブランキング。間欠動作カメラ用途
  なので意図的に遅くしてある（ジッタ・配線耐性優先）。
- SCCB の ID 読み出しには XCLK 供給が必須。V1-1 が通れば XCLK も正常。

## 実行手順

事前条件: Pico 2 W に `code/dnnrt_upy/firmware/firmware.uf2`（dnnrt 組み込み・
`rp2.DMA` 対応ビルド）を書き込み済みであること。

```sh
cd ~/ドキュメント/開発/pico2w-edge-ai

# 1. ドライバを Pico へ転送
.venv/bin/mpremote cp code/ov7670_pio/ov7670.py :ov7670.py

# 2. V1 検証スクリプトを実行（チェックリスト結果が表示される）
.venv/bin/mpremote run code/ov7670_pio/v1_capture_test.py

# 3. 取得フレームを PC へ回収して PNG 化
.venv/bin/mpremote cp :frame.raw frame.raw
.venv/bin/python code/ov7670_pio/pc/convert_frame.py frame.raw
# → frame.png (480x360, 3倍拡大) を画像ビューアで確認
```

## V1 チェックリストとの対応

| 検証項目 | スクリプト内 |
|---|---|
| PWM で XCLK を安定供給できるか | V1-1（ID 読み出し成功 = XCLK 正常） |
| SCCB でレジスタ読み書き（ID 0x76） | V1-1 |
| PIO で VSYNC/PCLK 同期 8bit 取り込み | V1-5 |
| DMA で PIO FIFO → フレームバッファ転送 | V1-5 |
| QQVGA RGB565 1 フレームが乱れなく取れるか | V1-6 + PNG 目視 |
| フレームバッファ確保後のヒープ残量 | V1-4 |
| シリアル経由で PC 転送・目視確認 | 手順 3 |

## トラブルシュート

- **mpremote が `no device found`（Linux）**: デバイスは見えているのに開けない
  場合、シリアルポートの権限不足が典型。`ls -l /dev/ttyACM0` が
  `root dialout` で、自分が dialout グループに入っていないなら
  `sudo usermod -aG dialout $USER` して再ログイン
  （即席なら `sudo chmod 666 /dev/ttyACM0`。抜き差しで戻る）。
- **V1-1 で失敗**: SIOD/SIOC の配線、XCLK（GP13）の配線を確認。
  XCLK が届いていないと SCCB は一切応答しない。
- **V1-5 でタイムアウト**: PCLK/VSYNC の配線を確認。V1-3 の VSYNC エッジ数が
  0 ならカメラがフレームを出していない（レジスタ初期化失敗の可能性）。
- **画像が縞模様・ズレる**: D0–D7 の順番違いが典型。GP2=D0 … GP9=D7 を確認。
- **色がおかしい**: `--swap` オプションでバイト順を入れ替えて再変換してみる。
- **画が暗い/明るすぎ**: AGC/AEC の整定前に撮っている可能性。数フレーム
  取り込んでから保存する、または照明を調整する。
