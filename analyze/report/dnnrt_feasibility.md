# DNNRT (nnabla-c-runtime) RP2350 移植可能性調査レポート

## 0. 調査概要

### 0.1 調査対象パスについて(注意)

依頼で指定されたパス `analyze/dnnrt_sdk/sdk/externals/nnablart/` は実際には存在しない。
実際のソースは1階層上の以下に配置されている。

```
analyze/dnnrt_sdk/externals/nnablart/nnabla-c-runtime/
```

本レポートはこのディレクトリ以下(約140ファイル、`.c`/`.h`が中心)を対象に調査した。

### 0.2 ディレクトリ構成(主要部分)

```
nnabla-c-runtime/
├── include/nnablart/
│   ├── network.h        # NNBバイナリのデータ構造定義(自動生成)
│   ├── runtime.h         # 公開API (rt_*)
│   ├── functions.h        # 関数(レイヤ)構造体定義
│   └── config.h           # CONFIG_XXXXX フィーチャーフラグ(自動生成)
├── src/
│   ├── runtime/
│   │   ├── runtime.c           # コアランタイム実装
│   │   ├── runtime_internal.c/.h  # NNBアクセス用マクロ・ヘルパ
│   │   ├── context.h           # 内部コンテキスト構造体
│   │   └── function_context.c  # 関数別ローカルコンテキスト割当(自動生成・巨大switch)
│   ├── functions/
│   │   ├── utilities/   # accessor, shape, list, fixedpoint など
│   │   └── implements/  # 各レイヤの実装(activation/arithmetic/array/logical/math/
│   │                     #   neural_network/normalization/quantization/reduction/
│   │                     #   stochasticity)。.cファイル75本
│   └── nnablart/
│       ├── main.c   # CLIエントリポイント (dump/infer/version)
│       └── infer.c  # CLI推論ドライバ(ファイルI/O)
├── examples/callback/callback.c  # NNBを配列として埋め込む使用例
└── doc/ (FILE_FORMAT.md, USAGE.md, BUILD.md, SUPPORT_STATUS.md, ...)
```

---

## 1. NuttX依存の箇所(ファイルI/O・メモリアロケータ・割り込み)

### 結論: コアランタイム本体(`src/runtime/`, `src/functions/`)にNuttX依存は一切ない。

`nuttx|NuttX|sys/types|unistd|fcntl|fopen|fread|FILE \*|sys/stat` でソース全体をgrepした結果、ヒットしたのは以下の2ファイルのみ。

- `src/nnablart/main.c`
- `src/nnablart/infer.c`

いずれも**CLIサンプルツール**(NNBファイルの読み込み・推論結果のファイル書き出しを行うデバッグ用コマンド)であり、ランタイム本体には含まれない。RP2350移植時はこの2ファイルをまるごと不要として除外できる。

#### ファイルI/Oの実態(main.c / infer.c)

- `main.c` L43-57: `fopen`/`fread`でNNBファイル全体を`malloc`バッファへ読み込み、`(nn_network_t*)`にキャストしてランタイムへ渡す。
- `infer.c` L74-143: 入力データを`fopen`/`fread`でファイルから読み込み`rt_input_buffer()`へコピー。
- `infer.c` L151-216: 推論結果を`fopen`/`fwrite`でファイル出力。

これらは「NNBやテストデータをホストPCのファイルシステムから読む」という**開発用ツールの都合**であり、ランタイムAPI(`rt_initialize_context`, `rt_forward`など)自体はファイルI/Oに一切依存しない(後述4節)。

### メモリアロケータ

`src/runtime/runtime.c` L24-28 で、ランタイム全体のメモリ確保はグローバル関数ポインタ経由になっている。

```c
void *(*rt_variable_malloc_func)(size_t size) = malloc;
void (*rt_variable_free_func)(void *ptr) = free;
void *(*rt_malloc_func)(size_t size) = malloc;
void (*rt_free_func)(void *ptr) = free;
```

- `rt_set_malloc()` / `rt_set_free()`(L58-72): ランタイム管理構造体(`rt_context_t`, `rt_function_context_t`等)用アロケータの差し替え
- `rt_set_variable_malloc()` / `rt_set_variable_free()`(L42-56): 中間バッファ(アクティベーション)用アロケータの差し替え

デフォルトは標準`malloc`/`free`だが、**RP2350側で独自のヒープ(静的プールやPSRAM領域)に差し替えることが可能**。`malloc`/`free`自体はPico SDK(newlib)が提供するため、差し替えなしでもまずビルド・動作する。

### 割り込み・OSプリミティブ

- `src/runtime/`, `src/functions/`全体に、割り込みハンドラ・排他制御(mutex/semaphore)・タスク/スレッドAPI・NuttX固有ヘッダの参照は一切なし。
- `rt_forward()`(runtime.c L373-395)は単純なシーケンシャルループで全関数を実行するのみで、非同期実行やコールバック割り込みの仕組みは持たない。

→ **RTOS非依存。ベアメタル/Pico SDKのシングルスレッドループから直接呼び出せる。**

---

## 2. CXD5602固有命令・DSP最適化の有無

### 結論: CXD5602固有コード・DSP命令・SIMD intrinsicsは一切見つからなかった。

`asm|__asm__|intrinsic|__builtin|CXD5602|cxd56|DSP|neon|arm_math` で大文字小文字無視の全文grepを`src/`配下に実施した結果、**0件**。アセンブリファイル(`.S`/`.asm`)も存在しない(3節参照)。

### 固定小数点演算の実装(`src/functions/utilities/fixedpoint.h`)

CXD5602のDSPアクセラレータの代わりに、**ソフトウェアによる固定小数点(Qフォーマット)演算**が`inline`関数として実装されている。すべて標準Cのシフト・乗算・分岐のみで構成され、プラットフォーム依存命令はない。

- `sum_acc_sat8/16/32`, `sum_sat8/16`, `sub_sat8/16`: オーバーフロー検出付き飽和加減算
- `saturate16_to_8`, `saturate32_to_8/16`, `saturate64_to_16/32`: ビット幅縮小時の飽和変換
- `rescale_fixed8/16`, `rescale_scalar_fixed*`: 小数点位置(precision bits)の変換
- `fixed8_to_float` / `float_to_fixed8` 等: float ⇔ 固定小数点の相互変換

例として`affine_fixed8.c`(int8固定小数点Affineレイヤの実装、全104行)を確認したが、内容は`int8_t`/`int32_t`の配列に対する素朴な三重ループ(積和→`saturate32_to_8`によるスケーリング)であり、特殊命令は使っていない。

### RP2350視点での補足

- RP2350(Cortex-M33)は単精度FPUを内蔵しているため、**FLOAT32実装(`*_float.c`系)はハードウェアFPUで動作可能**。
- INT8/INT16固定小数点実装(`affine_fixed8/16.c`, `convolution_int8/16.c`)はDSP命令前提ではない素のCなので、Cortex-M33上でもそのまま動作する(SIMD命令`__SADD8`等を使えばさらに高速化できる余地はあるが、**移植の必須要件ではない**)。
- `nn_function_implement_t`(network.h)で定義される`NN_FUNCTION_IMPLEMENT_FIXED16`(102)/`FIXED8`(103)は、`doc/USAGE.md`では「汎用ディスパッチとしてはNOT IMPLEMENTED」と記載されているが、Affine・Convolution等**個別レイヤごとに`_fixed8`/`_fixed16`/`_int8`/`_int16`という専用ソースファイルが用意されており**、コード生成時にどの実装を使うかが`function_context.c`の`#ifdef CONFIG_XXXXX`分岐で決まる。

---

## 3. 純粋なCのみで書かれているか

### 結論: Yes。`.c`/`.h`以外のソースコードファイルは存在しない。

- 拡張子の全件確認の結果、`src/`・`include/`・`examples/`配下は`.c`/`.h`のみ。`.S`/`.asm`/`.cpp`/`.cc`は0件。
- 各ヘッダは`#ifdef __cplusplus extern "C" { ... }`ガードを持ち、C99/C11準拠でC++からの呼び出しにも対応した書き方になっている(組込み向けにC++プロジェクトへ混在させることも容易)。
- ビルドツール類(`build-tools/code-generator/`など)はPython製だが、これは**開発時にNNBや`network.h`/`config.h`/`function_context.c`を生成するためのオフラインツール**であり、ターゲット(RP2350)上で動作させる必要はない。
- `printf`/`snprintf`(エラー・警告メッセージ用、runtime.c L120-128, L383-388, L403-408)を除けば標準ライブラリ依存も`malloc/free/memcpy/memset/string.h/stdint.h/math.h`程度に収まる。`math.h`は`fixedpoint.h`の`roundf()`でのみ使用。

→ **Pico C SDK 2.x (arm-none-eabi-gcc) でクロスコンパイル可能な、移植性の高いコードベース。**

---

## 4. NNBファイルのロード方式(ファイルシステム依存か、配列で持てるか)

### 結論: ファイルシステム非依存。NNB全体を1つのconst配列(flash常駐)として保持し、そのままランタイムに渡せる。

### 4.1 NNBのメモリレイアウト

`src/runtime/runtime_internal.h` L24-53 に、NNBバイナリの構造を定義するマクロがある。

```c
#define NN_NETWORK_INDEX_SIZE(xNetwork) \
  ((xNetwork)->memory.num_of_data * sizeof(pointer_index_t))
#define NN_NETWORK_DATA_SIZE(xNetwork) ((xNetwork)->memory.data_size)
#define NN_NETWORK_SIZE(xNetwork) \
  (sizeof(nn_network_t) + NN_NETWORK_INDEX_SIZE(xNetwork) + NN_NETWORK_DATA_SIZE(xNetwork))
#define NN_NETWORK_INDEX_POINTER(xNetwork) \
  ((pointer_index_t *)(((uint8_t *)xNetwork) + sizeof(nn_network_t)))
#define NN_NETWORK_DATA_POINTER(xNetwork) \
  ((uint8_t *)NN_NETWORK_INDEX_POINTER(xNetwork) + NN_NETWORK_INDEX_SIZE(xNetwork))
#define NN_GET(xNetwork, xIndex) \
  (NN_NETWORK_DATA_POINTER(xNetwork) + NN_NETWORK_INDEX_POINTER(xNetwork)[xIndex])
```

つまりNNBは

```
[ nn_network_t ヘッダ ][ pointer_index_t インデックス配列 ][ データ領域(重み・形状情報など) ]
```

という**単一の連続バイナリブロブ**であり、すべてのアクセスは「先頭ポインタ + オフセット」のみで完結する(`doc/FILE_FORMAT.md`にも"platform independent and portable binary file format"と明記)。

### 4.2 ランタイム初期化時の扱い(`rt_initialize_context`, runtime.c L104-246)

- `n->version`(L111-114)・`n->api_level`(L118-129)のチェック後、
- `n->buffers`に基づき**中間バッファ(アクティベーション用)のみ**を`rt_variable_malloc_func`でRAM確保(L163-180)
- 各`nn_variable_t`について、`var->data_index < 0`なら確保したバッファを指し、`>= 0`なら**`NN_GET(n, var->data_index)`でNNBブロブ内のデータを直接指す**(L203-211)。つまり**重みデータはNNBから一切コピーされない**。

→ NNBブロブを`const uint8_t[]`としてflashに置けば、重みは追加コピーなしでflashから直接読み出され、RAMには中間バッファ分(モデル依存サイズ)だけ確保すればよい。

### 4.3 配列埋め込みの実例(`examples/callback/callback.c`)

```c
static unsigned char affine_nnb[] = {
    0x3f, 0x20, 0x21, 0x00, 0x02, 0x00, 0x00, 0x00, ... (NNBバイナリの内容)
};
...
nn_network_t *net = (nn_network_t *)affine_nnb;
ret = rt_initialize_context(context, net);
```

コメント(L70-73)に生成手順が明記されている。

```sh
$ nnabla_cli convert ... Affine_000.nnb
$ xxd -i Affine_000.nnb > Affine_000.c   # NNB→Cソース配列へ変換
```

`doc/FILE_FORMAT.md`にも「Embed NNB into source code」という見出しが用意されている(本文は空だが、意図された使い方であることを示す)。

### 4.4 RP2350移植時の方針

1. PC側で `nnabla_cli convert` によりNNCモデル(.nnp)を`.nnb`へ変換。
2. `xxd -i` または同等のツールで`.nnb`を`const uint8_t nnb_data[] = {...}`形式のCソースに変換し、flashに配置(`__attribute__((aligned(4)))`を付与しアライメント保証)。
3. `(nn_network_t *)nnb_data` にキャストして `rt_allocate_context` → `rt_initialize_context` → `rt_forward` を呼ぶだけで推論可能。
4. `main.c`/`infer.c`のファイルI/Oは一切不要。

---

## 5. 移植に必要な作業量の概算

前提: OV7670からの画像データを入力に、NNCで設計・学習したモデル(NNB化済み)をRP2350上で推論する用途を想定。

### 5.1 作業項目と見積り

| # | 作業項目 | 内容 | 目安工数 |
|---|---------|------|---------|
| 1 | ソース取り込み・CMake統合 | `include/nnablart/`, `src/runtime/`, `src/functions/utilities/`, 必要な`src/functions/implements/**`をPico SDKプロジェクトに追加し、`CMakeLists.txt`に組み込む。既存の`src/*/CMakeLists.txt`は参考程度(NNablaビルド全体に依存するため流用不可)。 | 1〜2日 |
| 2 | モデル別コード生成 | 対象NNCモデルから`nnabla_cli`で`.nnb`生成、さらに`network.h`/`config.h`/`function_context.c`を**そのモデル専用に再生成**(使う関数だけに絞ることでflashサイズ削減)。生成自体はPC上のPython環境で行うためRP2350側の作業は軽微。 | 0.5〜1日 |
| 3 | NNB埋め込み | `xxd -i`等で`.nnb`を`const uint8_t[]`化し、flash(XIP領域)に配置。アライメント・配置セクションの確認。 | 0.5日 |
| 4 | アロケータ接続 | `rt_set_malloc`/`rt_set_variable_malloc`等を使うか、デフォルトのnewlib `malloc`のままにするかを決定。RP2350 SRAM 520KBに対し、中間バッファ(`n->buffers`合計サイズ)+ランタイム管理構造体のSRAM使用量を見積り、ヒープサイズを調整。 | 0.5〜1日 |
| 5 | CLIツール除去・推論呼び出し実装 | `main.c`/`infer.c`は除外し、`examples/callback/callback.c`相当の最小コード(`rt_allocate_context`→`rt_initialize_context`→入力コピー→`rt_forward`→出力読み出し)をカメラフレーム取得ループに組み込む。 | 0.5〜1日 |
| 6 | 動作検証 | NNabla側で生成した期待出力(テストベクタ)と、RP2350上の推論結果を比較して数値一致(または許容誤差内)を確認。`printf`はPico SDKのUSB/UART stdioで代替可能。 | 1〜2日 |
| **小計** | | | **約4〜7日(1人week程度)** |

### 5.2 モデルが使用する関数の対応状況によるリスク

`doc/SUPPORT_STATUS.md`によれば、nnabla-c-runtimeは全216関数のうち**62関数のみ実装済み**(残りは`unimplemented.c`で`RT_FUNCTION_ERROR_UNIMPLEMENTED`を返すスタブ)。エッジ向けCNNでよく使う以下は実装済み(float/genericとも"yes"):

- **レイヤ系**: Affine, Convolution, DepthwiseConvolution, Deconvolution, MaxPooling, AveragePooling, SumPooling, Unpooling
- **活性化**: Sigmoid, Swish, Tanh, ReLU, LeakyReLU, Softmax, ELU, SELU, CReLU, CELU, PReLU
- **正規化**: BatchNormalization, MeanSubtraction
- **算術/論理**: Add2/Sub2/Mul2/Div2/Pow2、各種Scalar演算、Sign/Minimum2/Maximum2等
- **配列操作**: Concatenate, Split, Stack, Slice, Pad, Transpose, Flip, Shift, Reshape等
- **量子化**: BinarySigmoid/BinaryTanh/BinaryConnect(Affine/Convolution)/BinaryWeight(Affine/Convolution)

一方、**未実装**(スタブのみ): RNN/LSTM/GRU、FusedConvolution、GlobalAveragePooling、GELU/Mish/ReLU6等の新しい活性化、LayerNorm/GroupNorm等の正規化、FFT/STFT、各種Loss関数、Gather/Scatter系など。

→ **書籍で扱うCNN(Affine+Convolution+Pooling+ReLU/Softmax+BatchNorm程度の構成)であれば、追加実装はほぼ不要**で上記5.1の見積りに収まる。RNN/LSTMや新しい活性化関数(GELU等)をモデルに採用する場合は、該当関数を`fixedpoint.h`と同様の素のCで追加実装する必要があり、**1関数あたり数日〜1週間程度**の追加工数を見込む。

### 5.3 SRAM(520KB)に関する考慮事項

- 重み・定数データはflash上のNNB配列から直接参照されるため、**SRAM消費に重みサイズは(基本的に)含まれない**。
- SRAM消費の主な内訳は次の通り:
  - 中間バッファ(`n->buffers`の合計、`rt_variable_malloc_func`で確保): モデルの中間特徴マップサイズに依存。最も大きい層(例: 高解像度の畳み込み出力)が支配的。
  - `rt_context_t`本体・`rt_variable_t[]`・`rt_function_context_t[]`・各関数の`local_context`: 関数数・変数数に比例するが、通常は数KB程度。
- OV7670の画像バッファ(QVGA時 320×240×2byte ≈ 150KB、QQVGA 160×120×2byte ≈ 38KB)+WiFi(CYW43439)用バッファとDNNRT中間バッファが520KBのSRAMを共有するため、**入力解像度を下げる/中間特徴マップが小さくなるモデル設計**が現実的(NNC側でのモデル設計時に考慮すべき制約として、書籍側にもフィードバック推奨)。

---

## 6. まとめ

| 観点 | 結論 |
|------|------|
| 1. NuttX依存 | コア(`src/runtime/`, `src/functions/`)は依存なし。`fopen`等を使うのはCLIツール(`main.c`/`infer.c`)のみで移植時は除外可。malloc/freeは`rt_set_*`で完全に差し替え可能。割り込み・OS APIへの依存は皆無。 |
| 2. CXD5602/DSP | 該当コードなし(grep 0件)。固定小数点演算もすべて移植性の高いC実装(`fixedpoint.h`)で、RP2350のFPU/Cortex-M33上でそのまま動作可能。 |
| 3. 純粋C | Yes。`.c`/`.h`のみ、C99/C11+`extern "C"`対応。Pico SDK(arm-none-eabi-gcc)で問題なくビルド可能と判断。 |
| 4. NNBロード | ファイルシステム非依存。NNBは単一連続バイナリで`NN_GET`マクロにより base+offset アクセスのみ。`xxd -i`で`const uint8_t[]`化しflashに配置すれば、重みはflashから直接参照され追加コピー不要(`examples/callback/callback.c`が実例)。 |
| 5. 工数概算 | 一般的なCNN(Affine/Convolution/Pooling/ReLU系/BatchNorm/Softmax)であれば**約1人week(4〜7日)**でPoCレベルの移植が可能。未実装関数(RNN/LSTM、GELU等)を使う場合は関数ごとに数日〜1週間の追加実装が必要。SRAM 520KBは中間バッファ+カメラバッファ+WiFiバッファの合計で収まるようモデル側のサイズ設計が必要。 |

総合的に、**nnabla-c-runtime(DNNRT)はRP2350への移植難易度が低く、「世界初のSony DNNRT移植」というアプローチは技術的に十分実現可能**と評価する。最大の論点は移植作業そのものよりも、**520KB SRAM内に収まるモデルサイズ・中間バッファサイズでNNC側のモデルを設計できるか**という点に移る。
