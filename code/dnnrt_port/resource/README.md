# model.nnb + test.bmp 推論サンプル (dnnrt_port / ベアメタル版)

`code/dnnrt_port/example/` には、このフォルダの `model.nnb` と `test.bmp` を
使って実際に推論を行うサンプルプログラム `dnnrt_infer_example` が含まれます。

`code/dnnrt_upy/examples/infer_bmp_demo.py` (MicroPython版) と同じ前処理・
同じモデルを使用し、同じ結果 (クラス3, 約99.8%) が得られることを実機で
確認済みです。詳細な検証経緯は `test_report.md` を参照してください。

## モデル/画像の内容

- `model.nnb`: 入力 `(1,1,28,28) float32` (=784要素=3136byte) /
  出力 `(1,11) float32` (=11要素=44byte) の11クラス分類器
- `test.bmp`: 28x28, 32bpp BGRA グレースケール画像 (B=G=R, A=255固定)

## 構成

```
code/dnnrt_port/
├── CMakeLists.txt          # add_subdirectory(example) を追加済み
├── example/
│   ├── CMakeLists.txt       # dnnrt_infer_example の定義
│   ├── bin2c.cmake          # バイナリ→Cヘッダ変換スクリプト
│   └── infer_example.c      # サンプル本体
└── resource/
    ├── model.nnb             # NNC学習済みモデル (nnabla-c-runtime形式)
    ├── test.bmp              # テスト画像
    ├── test_report.md        # dnnrt_upy側の検証レポート
    └── README.md             # 本ドキュメント
```

ベアメタル版にはファイルシステムが無いため、`model.nnb`/`test.bmp` は
ビルド時に `bin2c.cmake` でCのバイト配列 (`model_nnb.h`/`test_bmp.h`) に
変換され、`infer_example.c` に静的配列として埋め込まれます。
このフォルダの `model.nnb`/`test.bmp` を別のモデル・画像に置き換えれば、
再ビルド時に自動的に新しい配列が生成されます
(CMakeの`add_custom_command`/`DEPENDS`で依存関係を設定済み)。

ただし `infer_example.c` 側は「28x28, float32入力 / Nクラスfloat32出力,
32bpp BGRA BMP」という前提で書かれているため、入力形状やビット深度が
異なるモデル・画像を使う場合は `infer_example.c` の修正が必要です。

## ビルド手順 (Windows / Pico SDK 2.x ネイティブ環境)

以下のツールがインストール済みであることを前提とします
(パスは一例。環境に合わせて読み替えてください)。

| ツール | パス例 |
|---|---|
| Pico SDK 2.x | `C:\Users\<user>\.pico-sdk\sdk\2.2.0` |
| arm-none-eabi-gcc 14.x | `C:\Users\<user>\.pico-sdk\toolchain\14_2_Rel1\bin` |
| CMake | `C:\Users\<user>\.pico-sdk\cmake\v3.31.5\bin` |
| Ninja | `C:\Users\<user>\.pico-sdk\ninja\v1.12.1` |
| picotool | `C:\Users\<user>\.pico-sdk\picotool\2.2.0-a4\picotool` |

PowerShellで環境変数とPATHを設定します。

```powershell
$env:PICO_SDK_PATH = "C:\Users\<user>\.pico-sdk\sdk\2.2.0"
$env:PATH = "C:\Users\<user>\.pico-sdk\toolchain\14_2_Rel1\bin;" +
            "C:\Users\<user>\.pico-sdk\cmake\v3.31.5\bin;" +
            "C:\Users\<user>\.pico-sdk\ninja\v1.12.1;" + $env:PATH
```

リポジトリルートで configure / build します
(`picotool_DIR` を明示しないと、picotool をソースからビルドしようとして
失敗するため必須です)。

```powershell
cmake -G Ninja -S code\dnnrt_port -B code\dnnrt_port\build `
      -Dpicotool_DIR="C:\Users\<user>\.pico-sdk\picotool\2.2.0-a4\picotool"

cmake --build code\dnnrt_port\build --target dnnrt_infer_example
```

ビルドが成功すると以下が生成されます。

```
code\dnnrt_port\build\example\dnnrt_infer_example.uf2
```

## pico2 / pico2W への書き込み

1. Pico2 / Pico2 W の **BOOTSELボタンを押しながら** PCにUSB接続する
   (リムーバブルディスク `RP2350` が認識される)。
2. `dnnrt_infer_example.uf2` を `RP2350` ドライブにコピーする。

   ```powershell
   Copy-Item code\dnnrt_port\build\example\dnnrt_infer_example.uf2 F:\ -Force
   ```

3. コピー完了後、ボードは自動的に再起動してプログラムが実行される。

すでにこのボードにMicroPython版 (`dnnrt_upy`) を書き込んでいる場合は、
物理的なBOOTSEL操作の代わりに以下でもBOOTSELモードに移行できます。

```python
import machine
machine.bootloader()
```

## 実行結果の確認 (USBシリアル)

`dnnrt_infer_example` は USB CDC シリアル (115200bps, 8N1) に結果を出力します。
お使いのシリアルターミナル (Tera Term, PuTTY など) で、書き込み後に
出現するCOMポートを 115200bps で開いてください。

- プログラムは `stdio_init_all()` 後に **3秒待って**から出力を開始します。
  このタイミングに合わせてターミナルを開いてください。
- ターミナル接続時に **DTR信号がアサートされる**必要があります
  (`tud_cdc_connected()` がDTRを見て出力先の有無を判定するため)。
  Tera Term / PuTTY 等の通常のシリアルターミナルでは接続時に自動で
  アサートされますが、自作のシリアル読み取りスクリプト等を使う場合は
  DTR (および可能ならRTS) を明示的に有効にしてからポートを開いてください。
  DTRがアサートされないまま3秒経過すると、その回の出力は失われます
  (ボードをリセットして再度出力させる必要があります)。

## 期待される出力

`model.nnb` + `test.bmp` で実機確認した実際の出力 (Pico2 W / RP2350):

```
=== DNNRT RP2350 inference example (model.nnb + test.bmp) ===
NNabla version    : 1.24.0.dev1
C-Runtime version : 1.2.0.dev1_c1
NNB format version: 3
inputs : 1
outputs: 1
input[0]  elements=784 dtype=0 fp_pos=0
rt_forward: OK
output[0] = 0.000005
output[1] = 0.000004
output[2] = 0.000640
output[3] = 0.998012
output[4] = 0.000005
output[5] = 0.000520
output[6] = 0.000001
output[7] = 0.000000
output[8] = 0.000721
output[9] = 0.000093
output[10] = 0.000000
predicted class: 3 (score=0.998012)
=== done ===
```

`predicted class: 3 (score=0.998012)` が、`code/dnnrt_upy/examples/infer_bmp_demo.py`
(MicroPython版、`predicted class: 3 score: 0.99801192`) と一致していれば、
ベアメタル版でも正しく推論できていることになります。
