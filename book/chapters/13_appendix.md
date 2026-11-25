# 付録 — リファレンスと実測データ集

本編で使った API・レジスタ・部品・実測値を、辞書として引ける形にまとめます。網羅性より「本書で使うものを確実に」を優先しています。

## 付録A MicroPython `rp2`/`machine` リファレンス（本書で使うもののみ）

### machine モジュール

| API | 本書での使い方 | 登場章 |
|---|---|---|
| `Pin(n, Pin.IN)` | 入力ピン。**PIO が参照するピンは必ずこれで初期化**（RP2350 の入力有効化） | 4 |
| `Pin("LED", Pin.OUT)` | 基板 LED（CYW43 側にあるため名前指定） | 2, 3 |
| `pin.value()` / `on()` / `off()` / `toggle()` | 読み取り・出力操作 | 2 |
| `PWM(Pin(n), freq=15_000_000, duty_u16=32768)` | OV7670 の XCLK 生成（50% デューティ） | 4 |
| `pwm.deinit()` | XCLK 停止（カメラ休止、実測 -7.5mA） | 10 |
| `I2C(0, sda=Pin(0), scl=Pin(1), freq=100_000)` | SCCB（I2C互換）バス | 4 |
| `i2c.scan()` | アドレス一覧。OV7670 は `[33]`（0x21） | 4 |
| `i2c.writeto(addr, bytes)` / `readfrom(addr, n)` | SCCB の2段読み（リピーテッドスタート不可のため） | 4 |
| `machine.lightsleep(ms)` | 浅い眠り（続きから復帰）。実測 10.1mA | 10 |
| `machine.deepsleep(ms)` | 深い眠り（**復帰＝リセット、main.py 再実行**）。実測 6.0mA | 10 |
| `machine.reset()` / `machine.bootloader()` | 再起動／BOOTSEL モードへ移行（ファーム書き込み時に便利） | 2 |

### rp2 モジュール（PIO と DMA）

`@rp2.asm_pio` デコレータの引数（本書で使うもの）：

| 引数 | 意味 | 本書の設定 |
|---|---|---|
| `in_shiftdir` | 取り込みビットの詰め方向 | `SHIFT_RIGHT`（メモリに届いた順で並ぶ） |
| `autopush` / `push_thresh` | 指定ビット数たまったら自動で FIFO へ | `True` / `32`（4バイト単位で DMA へ） |
| `set_init` | set 対象ピンの初期状態 | `OUT_LOW`（L チカ例のみ） |

PIO アセンブリ命令（本書で使う7種）：

| 命令 | 意味 |
|---|---|
| `wait(1, gpio, n)` | GPIO n が 1（/0）になるまで停止 |
| `in_(pins, 8)` | 基準ピンから連続8本を ISR へ取り込む |
| `jmp(x_dec, "label")` | X を減らしながらラベルへ（ループカウンタ） |
| `mov(x, y)` / `mov(y, osr)` | レジスタ間コピー |
| `pull()` | TX FIFO から OSR へ（CPU から値を受け取る） |
| `set(pins, 1) [31]` | ピン出力＋角括弧は追加待ちクロック |
| `label("name")` / `wrap_target()` / `wrap()` | ジャンプ先／ループ範囲の指定 |

StateMachine と DMA：

| API | 本書での使い方 | 登場章 |
|---|---|---|
| `rp2.StateMachine(0, prog, in_base=Pin(2))` | SM 生成。in_base が `in_(pins,…)` の基準ピン | 4 |
| `sm.active(1/0)` / `sm.restart()` | 実行開始・停止／プログラム先頭へ巻き戻し | 4 |
| `sm.put(v)` / `sm.get()` / `sm.rx_fifo()` | TX へ値を渡す／RX から取る／RX の滞留数 | 4 |
| `rp2.DMA()` | DMA チャネル確保 | 4 |
| `dma.pack_ctrl(size=2, inc_read=False, inc_write=True, treq_sel=4)` | 32bit 単位、読み元固定・書き先前進、PIO0-RX0 のペースで | 4 |
| `dma.config(read=0x50200020, write=buf, count=n, ctrl=c, trigger=True)` | PIO0 SM0 の受信 FIFO 番地から buf へ n 回 | 4 |
| `dma.active()` / `dma.close()` | 転送中の判定／解放 | 4 |

### その他の常連

`time.ticks_ms()` と `time.ticks_diff(t1, t0)`（経過時間の測定。引き算を直接せずticks_diff を使う）、`time.sleep_ms(n)`、`gc.collect()` と `gc.mem_free()`（メモリの家計簿）、`os.stat(path)[6]`（ファイルサイズ）、`sys.stdin.readline()` / `sys.stdout.buffer.write()`（収集ツールのシリアル通信）。

## 付録B OV7670 レジスタ設定一覧

SCCB アドレスは **0x21**（7bit）。ID はレジスタ 0x0A＝0x76、0x0B＝0x73。本書の QQVGA・RGB565 設定の全リストです（`ov7670.py` の実装と同一）。

| レジスタ | 値 | 役割 |
|---|---|---|
| 0x12 COM7 | 0x80 → 0x04 | ソフトリセット（要 50ms 待ち）→ RGB 出力モード |
| 0x11 CLKRC | 0x03 | 内部クロック分周 1/4（XCLK 15MHz → 3.75MHz） |
| 0x0C COM3 | 0x04 | ダウンサンプリング（DCW）有効 |
| 0x3E COM14 | 0x1A | DCW/スケーリング PCLK 有効・手動・PCLK 1/4 分周 |
| 0x70 / 0x71 | 0x3A / 0x35 | スケーリング係数（標準値） |
| 0x72 | 0x22 | 水平・垂直とも 1/4 間引き（VGA→QQVGA） |
| 0x73 | 0xF2 | DSP クロック 1/4 分周 |
| 0xA2 | 0x02 | スケーリング時の PCLK 遅延 |
| 0x15 COM10 | 0x20 | **HBLANK 中は PCLK 停止**（PIO 取り込みの要） |
| 0x40 COM15 | 0xD0 | **RGB565**・出力フルレンジ |
| 0x3A TSLB | 0x04 | 出力シーケンス設定 |
| 0x17 / 0x18 | 0x16 / 0x04 | 水平ウィンドウ開始/終了（HSTART/HSTOP） |
| 0x32 HREF | 0x24 | 水平ウィンドウ微調整 |
| 0x19 / 0x1A | 0x02 / 0x7A | 垂直ウィンドウ開始/終了（VSTRT/VSTOP） |
| 0x03 VREF | 0x0A | 垂直ウィンドウ微調整 |

色調・自動露出（AGC/AEC）関連はデフォルト値のまま使っています。画質を追い込みたい場合は OV7670 のデータシート（実装ガイド）を参照してください — ただし第7章の鉄則により、**レジスタを変えたら学習データも撮り直し**です。

## 付録C NNC レイヤーリファレンス（本書で使うもののみ・DNNRT対応状況付き）

| NNC ブロック | 役割（本書の言葉で） | DNNRT | 登場章 |
|---|---|---|---|
| Input | 入力サイズの宣言（1,28,28） | — | 5, 6 |
| Convolution | 判子押し（パターン検出） | ✅ 実機確認済み | 5, 6 |
| ReLU | マイナスは黙らせる | ✅ 実機確認済み | 5, 6 |
| MaxPooling | 縮めて鈍感に | ✅ 実機確認済み | 5, 6 |
| Affine | 全結合（総合判定）。**パラメータの大食い** | ✅ 実機確認済み | 5, 6, 8 |
| Softmax | 点数→確率 | ✅ 実機確認済み | 5, 9 |
| Tanh | ReLU のご先祖（LeNet で登場） | ✅ 実機確認済み（LeNet .nnb で動作） | 6 |
| CategoricalCrossEntropy | 採点係。**学習専用**（エクスポート時に自動で外れる） | 対象外 | 5, 6 |
| ImageAugmentation | データ拡張。**学習専用**（同上） | 対象外 | 7 |

上記以外のブロックを使うときの確認先は、nnabla-c-runtime の公式対応表 `doc/SUPPORT_STATUS.md`（GitHub: sony/nnabla-c-runtime）です。BatchNormalization、Dropout（学習専用）、Sigmoid など定番どころはおおむね対応していますが、**「編集タブで1ブロック足すたびにチラ見」**を習慣にしてください。未対応レイヤーは .nnb にできても実行時に初めてエラーになります（9.6）。

## 付録D 全回路図・部品購入ガイド

### 配線表（本書標準・第4章より再掲）

| OV7670 | Pico 2 W | | OV7670 | Pico 2 W |
|---|---|---|---|---|
| 3.3V | 3V3(OUT) 36番 | | PCLK | GP10 |
| GND | GND 38番 | | HREF | GP11 |
| SIOD | GP0 | | VSYNC | GP12 |
| SIOC | GP1 | | XCLK | GP13（最短配線） |
| D0〜D7 | GP2〜GP9（順番厳守） | | RESET / PWDN | 3.3V / GND |

```text
                Raspberry Pi Pico 2 W
                ┌──────────────────────┐
   OV7670       │ GP0  ←SIOD    3V3 ──┼── OV7670 3.3V
  ┌────────┐    │ GP1  ←SIOC    GND ──┼── OV7670 GND
  │ D0-D7 ─┼──→│ GP2-GP9              │
  │ PCLK  ─┼──→│ GP10          VSYS ──┼── 電池ボックス(+) 単3×2
  │ HREF  ─┼──→│ GP11          GND  ──┼── 電池ボックス(-)
  │ VSYNC ─┼──→│ GP12                 │
  │ XCLK  ←┼───│ GP13 (PWM 15MHz)     │
  └────────┘    └──────────────────────┘
```

<!-- 図版TODO: 清書した回路図と、PWDN を GP14 + MOSFET 電源遮断の拡張回路図 (第10章の発展用) -->

電池駆動時は、電池ボックス（+）を **VSYS（39番ピン）**へ。VSYS は 1.8〜5.5V を受けるので、単3×2本（約3V）もリチウムイオン電池（第11章）も直結できます。USB と電池の同時接続は基本避けてください（開発時は USB、運用時は電池、と使い分けるのが安全です）。

### 部品購入ガイド

第1章の部品表（必須合計 約3,400円）を基準に、購入時の注意だけ補足します。

- **Pico 2 W**：「2」と「W」の両方を確認。技適マーク付きの国内正規流通品を
- **OV7670**：「FIFO なし」（基板裏に AL422B チップが**ない**もの）。相場より高いものは FIFO 付きの可能性大
- **ジャンパワイヤ**：10cm 程度の短いもの。20cm 超は XCLK/PCLK の安定性に不利
- **購入先の目安**：秋月電子通商・スイッチサイエンス（確実・解説豊富）、Amazon/AliExpress（安価・当たり外れあり）。OV7670 は互換モジュールが多数流通しており、本書の手順はピン配置が同じであれば動作します（ID 読み出し 0x76 が試金石）

## 付録E 消費電流実測データ集

**測定条件**：Pico 2 W 実機、本書の配布ファームウェア、USB 給電経路に電流計を直列挿入して定常値を目視読み取り（2026年7月、筆者測定）。**USB 接続込みの値であり、電池駆動時の真値に対しては上限側の目安**です。

### 状態別消費電流

| 状態 | 実測 | 備考 |
|---|---|---|
| deepsleep | **6.0 mA** | MicroPython 実装の床。復帰＝リセット |
| lightsleep（CYW43 停止後） | 10.1 mA | |
| lightsleep（CYW43 消し忘れ） | 29.2 mA | ⚠ アイドルより高い（10.3 の罠） |
| アイドル（REPL 待機） | 17.7 mA | |
| カメラ待機（XCLK 停止） | 23.0 mA | カメラ残留 約+5.3mA |
| 撮影＋前処理＋推論の連続実行 | 30.5 mA | カメラ稼働＋XCLK 供給込み |
| Wi-Fi 動作中 | 42.0 mA | 接続処理中の値（接続確立+送信時は要再測定） |

### 処理時間（14KB モデル・QQVGA）

| 工程 | 実測 |
|---|---|
| フレーム取得（VSYNC 待ち含む） | 427〜743 ms |
| 前処理（28×28 化、純 Python） | 19 ms |
| 推論 forward（14KB モデル） | 90 ms |
| （参考）推論 forward（LeNet 310KB） | 299 ms |
| Wi-Fi 通知1回（接続〜送信〜切断） | 約 5.5 秒 |

### メモリ（起動直後の空きヒープ 約446KB）

| 構成 | 全確保後のヒープ残 |
|---|---|
| カメラ + 14KB モデル + 中間バッファ | **369 KB** |
| カメラなし + LeNet 310KB + 中間バッファ | 69 KB |

### 電池寿命試算（単3×2本 = 2000mAh、毎サイクル通知の悲観側）

| 撮影間隔 | 平均電流 | 寿命 |
|---|---|---|
| 2分 | 約7.6 mA | 約11日 |
| 10分（本書標準） | 約6.4 mA | **約13日** |
| 60分 | 約6.1 mA | 約14日 |
| 10分 + TPL5110（10.7） | 約0.5 mA | 半年級（試算） |

> **再測定予定**：電池駆動＋精密電流計での測定値（特にスリープ系と「Wi-Fi 接続確立+送信」状態）は、本書サポートサイトで更新予定です。

## 付録F `dnnrt` モジュール API リファレンスと firmware.uf2 自前ビルド手順

### モジュール関数・定数

| 名前 | 説明 |
|---|---|
| `dnnrt.Model(nnb)` | NNB データ（bytes/bytearray）からモデルを初期化 |
| `dnnrt.nnabla_version()` / `runtime_version()` / `nnb_version()` | 各バージョン情報 |
| `dnnrt.DTYPE_FLOAT` / `DTYPE_INT16` / `DTYPE_INT8` / `DTYPE_SIGN` | テンソルのデータ型定数 |

### `dnnrt.Model` のメソッド

| メソッド | 説明 |
|---|---|
| `num_inputs()` / `num_outputs()` | 入出力テンソルの数 |
| `input_shape(i)` / `output_shape(i)` | 形状（タプル。例 `(1, 1, 28, 28)`） |
| `input_size(i)` / `output_size(i)` | バイトサイズ |
| `input_dtype(i)` / `output_dtype(i)` | `(dtype, fp_pos)` のタプル |
| `set_input(i, data)` | 入力セット。`data` は float の list/tuple（自動変換）または入力サイズちょうどの生バイト列（高速パス） |
| `forward()` | 推論実行 |
| `get_output(i)` | 出力を float の list で取得 |
| `get_output_bytes(i)` | 出力を生バイト列で取得（DTYPE_SIGN 等の非対応型用） |
| `close()` | コンテキスト解放（GC 任せにもできるが明示推奨） |

メモリに関する注意：NNB バッファ全体と中間バッファは MicroPython の GC ヒープから確保されます。`Model` は NNB バッファへの参照を保持し続けるので、`close()` するまで解放されません。読み込みは `dnnrt_loader.load_model()`（`readinto` 方式）を使ってください — `bytearray(f.read())` は一時的に2倍のメモリを要求します（8.3 のコラム）。

### firmware.uf2 の自前ビルド手順（Linux / WSL）

配布ファームウェアで足りている読者には不要な工程です。dnnrt モジュールを改造したい人向けの要約（詳細はサポートリポジトリ `code/dnnrt_upy/README.md`）：

```sh
# 1. 材料の取得
git clone https://github.com/micropython/micropython.git
git clone <本書サポートリポジトリ>       # nnabla-c-runtime のソース参照が必要

# 2. クロスコンパイラ等 (Ubuntu/Debian の例)
sudo apt install cmake ninja-build gcc-arm-none-eabi libnewlib-arm-none-eabi

# 3. ビルド (dnnrt を USER_C_MODULES として組み込む)
cd micropython && make -C mpy-cross
cd ports/rp2
make BOARD=RPI_PICO2_W \
     USER_C_MODULES=<リポジトリ>/code/dnnrt_upy/micropython.cmake submodules
make BOARD=RPI_PICO2_W \
     USER_C_MODULES=<リポジトリ>/code/dnnrt_upy/micropython.cmake

# 4. ports/rp2/build-RPI_PICO2_W/firmware.uf2 を BOOTSEL で書き込み
```

ビルドが通ったら `import dnnrt; dnnrt.nnabla_version()` で組み込みを確認してください。ここまで来たあなたは、もう第12章の「道2」を歩き始めています。
