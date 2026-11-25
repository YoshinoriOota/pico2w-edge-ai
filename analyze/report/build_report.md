# DNNRT (nnabla-c-runtime) RP2350 ビルドレポート

## 1. 概要

`code/dnnrt_port/` に作成したCMakeプロジェクト(`dnnrt_runtime`静的ライブラリ + `dnnrt_test`実行ファイル)を、
RP2350 (Pico2 W) 向けに実際にビルドし、UF2まで生成できることを確認した。

- 対象: `code/dnnrt_port/CMakeLists.txt`
- テストプログラム: `code/dnnrt_port/src/dnnrt_test.c`
- 結果: **227/227ターゲット ビルド成功、エラー・警告なし**

---

## 2. ビルド環境

ユーザー環境変数 `PICO_SDK_PATH` は `C:\Users\yyyy_\.pico-sdk\sdk\2.2.0` を指していた
(Raspberry Pi Pico VS Code拡張がインストールした構成)。これに合わせ、以下のツール一式を使用した。

| ツール | バージョン | パス |
|---|---|---|
| Pico SDK | 2.2.0 | `C:\Users\yyyy_\.pico-sdk\sdk\2.2.0` |
| ツールチェーン | arm-none-eabi-gcc 14.2.1 (14_2_Rel1) | `C:\Users\yyyy_\.pico-sdk\toolchain\14_2_Rel1\bin` |
| CMake | 3.31.5 | `C:\Users\yyyy_\.pico-sdk\cmake\v3.31.5\bin` |
| Ninja | 1.12.1 | `C:\Users\yyyy_\.pico-sdk\ninja\v1.12.1` |
| picotool | 2.2.0-a4 (プリビルド版) | `C:\Users\yyyy_\.pico-sdk\picotool\2.2.0-a4\picotool` |

ビルド設定:
- `PICO_BOARD = pico2_w`
- `PICO_PLATFORM = rp2350-arm-s` (pico2_wから自動判定)
- `PICO_COMPILER = pico_arm_cortex_m33_gcc`
- ビルドタイプ: `Release` (デフォルト)

---

## 3. ビルド手順

```powershell
$env:PICO_SDK_PATH = "C:\Users\yyyy_\.pico-sdk\sdk\2.2.0"
$env:PATH = "C:\Users\yyyy_\.pico-sdk\toolchain\14_2_Rel1\bin;C:\Users\yyyy_\.pico-sdk\cmake\v3.31.5\bin;C:\Users\yyyy_\.pico-sdk\ninja\v1.12.1;$env:PATH"

cmake -G Ninja -S code\dnnrt_port -B code\dnnrt_port\build `
    -Dpicotool_DIR="C:/Users/yyyy_/.pico-sdk/picotool/2.2.0-a4/picotool"

cmake --build code\dnnrt_port\build
```

`-Dpicotool_DIR=...` の指定理由は4.2節を参照。

---

## 4. 発生した問題と対応

### 4.1 `PICO_BOARD` の設定順序の誤り

**症状**: 初回configure時、明示的に `set(PICO_BOARD pico2_w CACHE STRING "Board type")` を
記述していたにもかかわらず、ログに以下が出力され、RP2040 (`pico`) としてconfigureされていた。

```
Defaulting platform (PICO_PLATFORM) to 'rp2040' since not specified.
Defaulting target board (PICO_BOARD) to 'pico' since not specified.
```

**原因**: `code/dnnrt_port/CMakeLists.txt` で

```cmake
include(pico_sdk_import.cmake)   # ← ボード判定はここで確定する
set(PICO_BOARD pico2_w CACHE STRING "Board type")
project(dnnrt_port C CXX ASM)
```

の順になっていた。`pico_sdk_import.cmake` が読み込む `pico_sdk_init.cmake` 内で
`PICO_BOARD`/`PICO_PLATFORM` のデフォルト解決とツールチェーンファイルの設定が行われるため、
`set(PICO_BOARD ...)` は **`include(pico_sdk_import.cmake)` より前** に書く必要がある。

**対応**: 順序を入れ替えた。

```cmake
cmake_minimum_required(VERSION 3.13)

set(PICO_BOARD pico2_w CACHE STRING "Board type")

include(pico_sdk_import.cmake)

project(dnnrt_port C CXX ASM)
```

修正後、ログは以下のように正しくpico2_w/RP2350として解決された。

```
Target board (PICO_BOARD) is 'pico2_w'.
Using board configuration from .../boards/pico2_w.h
Auto-converting non-specific PICO_PLATFORM='rp2350' to 'rp2350-arm-s'
Defaulting platform (PICO_PLATFORM) to 'rp2350-arm-s' based on PICO_BOARD setting.
Defaulting compiler (PICO_COMPILER) to 'pico_arm_cortex_m33_gcc' since not specified.
```

### 4.2 picotoolのソースビルド失敗

**症状**: `pico_add_extra_outputs(dnnrt_test)` が内部で要求する picotool (バージョン2.1.1) が
見つからず、CMakeが picotool をソースから取得・ビルドしようとして以下のエラーで失敗した。

```
CMake Warning: No installed picotool with version 2.1.1 found - building from source
...
The C compiler "D:/Renesas/LLVM for Renesas RISC-V 19.1.7.202501/bin/clang.exe" is not able to
compile a simple test program.
...
ld.lld: error: unable to find library -lkernel32
...
```

**原因**: picotoolはホスト(Windows)向けのネイティブツールとしてビルドされる。
そのホスト用Cコンパイラの自動検出で、PATH上にあった **Renesas RISC-V向けLLVM/Clang**
(`D:\Renesas\LLVM for Renesas RISC-V 19.1.7.202501`) が選択されてしまい、
Win32向けのリンク(`-lkernel32`等)に必要なライブラリ・リンカオプションを認識できず失敗した。
これはRP2350向けクロスビルド設定とは無関係の、ホスト環境側の問題。

**対応**: Pico VS Code拡張が `C:\Users\yyyy_\.pico-sdk\picotool\2.2.0-a4\picotool` に
プリビルド済みpicotool (picotoolConfig.cmake付き) を配置済みだったため、これを
`-Dpicotool_DIR=...` で明示的に指定し、ソースビルドを回避した。
(`picotoolConfigVersion.cmake` のメジャーバージョン一致判定により、要求バージョン2.1.1に対し
2.2.0-a4は互換ありと判定される)

```
Using picotool from C:/Users/yyyy_/.pico-sdk/picotool/2.2.0-a4/picotool/picotool.exe
```

> **注意**: `picotool_DIR` はコマンドラインキャッシュ変数として渡しており、
> `build/`ディレクトリを削除して再configureする場合は再度同じ指定が必要。
> 恒久化したい場合は `CMakeLists.txt` または `CMakeUserPresets.json` に追記する。

---

## 5. ビルド結果

```
[227/227] Linking CXX executable dnnrt_test.elf
```

生成物 (`code/dnnrt_port/build/`):

| ファイル | サイズ |
|---|---|
| `dnnrt_test.elf` | 1,661,464 bytes |
| `dnnrt_test.uf2` | 253,952 bytes |
| `dnnrt_test.bin` | 126,680 bytes |
| `dnnrt_test.hex` | 356,388 bytes |
| `dnnrt_test.elf.map` | 726,185 bytes |
| `dnnrt_test.dis` | 2,057,801 bytes |

`dnnrt_test.uf2` をBOOTSELモードのPico2 Wにドラッグ&ドロップすることでフラッシュ書き込み可能。

---

## 6. メモリ使用量 (`arm-none-eabi-size`)

### 6.1 `dnnrt_test.elf` 全体

| text (Flash) | data | bss (SRAM) | 合計 |
|---|---|---|---|
| 130,776 bytes (約128KB) | 0 | 3,776 bytes (約3.7KB) | 134,552 bytes |

RP2350のSRAM 520KBに対し `.bss` は約3.7KBのみ。
DNNRTの変数バッファは `rt_initialize_context()` 実行時に**ヒープ(malloc)**から動的確保されるため、
静的な `.bss` には現れない。今回の `affine_nnb` (Affine 1層・小規模) では、
ヒープ使用量はNNBの `memory.data_size` 相当(数KB程度)と見積もられる。

### 6.2 `dnnrt_runtime` 静的ライブラリの内訳(主な.oファイル, text部)

| オブジェクト | text |
|---|---|
| `function_context.c.obj` (関数別ローカルコンテキスト割当: 巨大switch) | 12,992 bytes |
| `arithmetic_fixed.c.obj` | 6,280 bytes |
| `runtime.c.obj` | 2,126 bytes |
| `arithmetic_generic.c.obj` | 1,376 bytes |
| `arithmetic.c.obj` | 1,348 bytes |
| `runtime_internal.c.obj` | 284 bytes |

`function_context.c.obj`(216関数分のディスパッチテーブル)が最大だが、
それでも13KB程度であり、フラッシュ容量上の懸念は小さい。

---

## 7. 今後の課題

1. **実機での動作確認**: `dnnrt_test.uf2` を実機に書き込み、USBシリアル(`printf`出力)で
   `rt_allocate_context` 〜 `rt_free_context` の一連のAPIが正常終了することを確認する。
2. **picotool依存の恒久対応**: `-Dpicotool_DIR` 指定をCMakeUserPresets.json等に組み込み、
   毎回のコマンドライン指定を不要にする。
3. **実モデルでの検証**: `affine_nnb` はコールバック経由のダミー実行(`impl=1`)のため、
   実際の演算は行われていない。`impl=AUTO/FLOAT`で変換したNNBを用いて、
   `exec_affine`等の組み込み実装による実演算・SRAM使用量を計測する。
