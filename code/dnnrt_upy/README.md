# dnnrt_upy — DNNRT (nnabla-c-runtime) MicroPython ラッパー

Pico2 W (RP2350) 上の MicroPython から、Sony Neural Network Console (NNC) で
学習・変換した `model.nnb` を読み込み、DNNRT (nnabla-c-runtime) で推論を
実行するためのラッパーモジュールです。

`code/dnnrt_port/` (Pico C SDK のベアメタルアプリ) とは独立した
**MicroPython user C module** として構成されており、pico-sdk のソースとは
混在しません。DNNRT 本体のソース (`analyze/dnnrt_sdk/externals/nnablart/`)
はコピーせず、ビルド時に参照するだけです。

## ディレクトリ構成

```
code/dnnrt_upy/
├── README.md            # 本ドキュメント
├── micropython.cmake     # MicroPython user C module 登録用 (USER_C_MODULES)
├── src/
│   └── moddnnrt.c         # Cエクステンションモジュール本体 (dnnrtモジュール)
├── lib/
│   └── dnnrt_loader.py     # model.nnb 読み込み・情報表示ヘルパ (Pico側に転送する)
├── examples/
│   ├── infer_demo.py        # 使用例 (Pico側に転送して実行する)
│   └── infer_bmp_demo.py     # model.nnb + test.bmp を使った推論サンプル
└── firmware/
    └── firmware.uf2          # ビルド済みファームウェア (下記参照)
```

## ビルド済みファームウェア

`firmware/firmware.uf2` は、本READMEの手順でビルド済みの `dnnrt` モジュール
組み込みファームウェアです (RPI_PICO2_W向け、`code/dnnrt_port/resource/model.nnb`
+ `test.bmp` での推論検証済み、[[project-dnnrt-upy-first-e2e-test]])。

BOOTSELモードで接続したPico2 Wに、このファイルをそのままドラッグ&ドロップ
すれば、ソースからビルドせずに `import dnnrt` を試すことができます。

```powershell
Copy-Item code\dnnrt_upy\firmware\firmware.uf2 F:\ -Force
```

`moddnnrt.c` を変更した場合は、下記のビルド手順で再生成してください。

`micropython.cmake` は `analyze/dnnrt_sdk/externals/nnablart/nnabla-c-runtime`
以下のソースを `code/dnnrt_port/CMakeLists.txt` と同じ方法で直接参照します。

## 前提条件

- [MicroPython](https://github.com/micropython/micropython) ソースツリー
  (Pico2 W / RP2350 対応版、v1.24 以降を推奨)
- arm-none-eabi-gcc, cmake, ninja (pico-sdk のビルド環境と共通)
- このリポジトリ (`pico2w-edge-ai`) を clone 済みであること
  (`analyze/dnnrt_sdk/externals/nnablart/nnabla-c-runtime` を参照するため)

MicroPython 本体・pico-sdk はこのリポジトリには含まれていません。
別途任意の場所に clone してください。

## ビルド手順

```sh
# MicroPython を取得 (例)
git clone https://github.com/micropython/micropython.git
cd micropython
make -C mpy-cross

cd ports/rp2
make BOARD=RPI_PICO2_W \
     USER_C_MODULES=<pico2w-edge-aiのパス>/code/dnnrt_upy/micropython.cmake \
     submodules

make BOARD=RPI_PICO2_W \
     USER_C_MODULES=<pico2w-edge-aiのパス>/code/dnnrt_upy/micropython.cmake
```

ビルドが成功すると `ports/rp2/build-RPI_PICO2_W/firmware.uf2` が生成されます。
これを BOOTSEL ボタンを押しながら接続した Pico2 W にドラッグ&ドロップして
書き込みます。

書き込み後、`import dnnrt` が成功すれば組み込み完了です。

```
>>> import dnnrt
>>> dnnrt.nnabla_version()
'1.24.0.dev1'
```

## model.nnb の準備

1. NNC (Neural Network Console) でモデルを設計・学習し `.nnp` を出力する。
2. PC上で `nnabla_cli` を使い `.nnb` (nnabla-c-runtime形式) に変換する。

   ```sh
   nnabla_cli convert model.nnp model.nnb
   ```

3. 生成した `model.nnb` を、`mpremote` 等で Pico のファイルシステムへ
   コピーする。

   ```sh
   mpremote cp model.nnb :model.nnb
   mpremote cp code/dnnrt_upy/lib/dnnrt_loader.py :dnnrt_loader.py
   mpremote cp code/dnnrt_upy/examples/infer_demo.py :infer_demo.py
   ```

`model.nnb` をフラッシュ上のファイルとして配置することで、**ファームウェアを
再ビルドせずにモデルだけを入れ替える**ことができます。

## Python API リファレンス

### モジュール関数・定数 (`dnnrt`)

| 名前 | 説明 |
|---|---|
| `dnnrt.Model(nnb)` | NNBデータ (`bytes`/`bytearray`等) からモデルを初期化する |
| `dnnrt.nnabla_version()` | NNablaのバージョン文字列を返す |
| `dnnrt.runtime_version()` | nnabla-c-runtime のバージョン文字列を返す |
| `dnnrt.nnb_version()` | NNBフォーマットのバージョン番号を返す |
| `dnnrt.DTYPE_FLOAT` / `DTYPE_INT16` / `DTYPE_INT8` / `DTYPE_SIGN` | `network.h` の `nn_data_type_t` に対応するデータ型定数 |

### `dnnrt.Model`

`model.nnb` をメモリ上に展開し、推論コンテキストを保持するクラス。
内部では `rt_allocate_context` → `rt_initialize_context` までを
コンストラクタで実行する。

| メソッド | 説明 |
|---|---|
| `num_inputs()` | 入力テンソルの数 |
| `num_outputs()` | 出力テンソルの数 |
| `input_shape(i)` | 入力テンソル `i` の形状 (タプル) |
| `output_shape(i)` | 出力テンソル `i` の形状 (タプル) |
| `input_size(i)` | 入力テンソル `i` のバイトサイズ |
| `output_size(i)` | 出力テンソル `i` のバイトサイズ |
| `input_dtype(i)` | 入力テンソル `i` の `(dtype, fp_pos)` |
| `output_dtype(i)` | 出力テンソル `i` の `(dtype, fp_pos)` |
| `set_input(i, data)` | 入力テンソル `i` にデータを設定する (下記参照) |
| `forward()` | 推論を実行する (`rt_forward`) |
| `get_output(i)` | 出力テンソル `i` を `float` の `list` として取得する |
| `get_output_bytes(i)` | 出力テンソル `i` を生バイト列 (`bytes`) として取得する |
| `close()` | コンテキストを解放する (`rt_free_context`)。呼び忘れても内部バッファはGCヒープ経由で確保されているため最終的にはGCで回収されるが、解放タイミングを確定させたい場合は明示的に呼ぶこと |

#### `set_input(i, data)` の `data` について

`data` には2種類の形式を指定できる。

- **`list`/`tuple` of `float`**: `input_dtype(i)` の `dtype`/`fp_pos` に
  応じて自動的に変換される。
  - `DTYPE_FLOAT`: そのまま `float32` として書き込む
  - `DTYPE_INT16`/`DTYPE_INT8`: `value * 2**fp_pos` を四捨五入・範囲制限して
    固定小数点形式で書き込む
- **`bytes`/`bytearray`/`array` などバッファプロトコル対応オブジェクト**:
  `input_size(i)` バイトちょうどであれば、NNBが要求する生バイナリ形式として
  そのままコピーする。カメラ画像など、あらかじめ正しい形式に整形済みの
  データを高速に渡す場合に使う。

`get_output(i)` も同様に `dtype`/`fp_pos` に応じて `float` へ変換した
`list` を返す (`DTYPE_SIGN` 等、変換に対応していない型では
`get_output_bytes(i)` を使うこと)。

## サンプルプログラム

`examples/infer_demo.py` (`lib/dnnrt_loader.py` を併せて転送して使用):

```python
import dnnrt
import dnnrt_loader

model = dnnrt_loader.load_model("model.nnb")
print(dnnrt_loader.summary(model))

in_shape = model.input_shape(0)
n = dnnrt_loader.num_elements(in_shape)
model.set_input(0, [0.0] * n)

model.forward()

for i in range(model.num_outputs()):
    print("output[%d] =" % i, model.get_output(i))

model.close()
```

## メモリに関する注意事項

- `model.nnb` は `dnnrt_loader.load_model()` でファイルシステムから
  `bytearray` として読み込み、その全体を RAM に保持する。NNB内の重み
  データはこの `bytearray` を直接参照するため、`dnnrt.Model` インスタンスは
  内部でこのバッファへの参照を保持し続ける (`close()` するまで解放されない)。
- 中間バッファ (アクティベーション) は MicroPython の GCヒープから確保される
  (`rt_set_variable_malloc`/`rt_set_malloc` を `gc_alloc`/`gc_free` に
  差し替えている)。モデルの中間特徴マップサイズが大きい場合、
  MicroPythonのヒープを圧迫するので注意する。
- RP2350 のSRAM (520KB) は、`model.nnb` 本体 + 中間バッファ +
  MicroPythonインタプリタ + (使う場合) カメラ/WiFiバッファを
  すべて共有する。入力解像度・モデルサイズの設計時はこれを考慮すること。

## 制約・既知の制限

- `nnabla-c-runtime` は全関数のうち一部のみ実装されている
  (詳細は `analyze/report/dnnrt_feasibility.md` および
  `analyze/dnnrt_sdk/externals/nnablart/nnabla-c-runtime/doc/SUPPORT_STATUS.md`
  を参照)。NNC側のモデルは実装済みの関数のみで構成する必要がある。
- `set_input`/`get_output` の `list`/`tuple` 変換は
  `DTYPE_FLOAT`/`DTYPE_INT16`/`DTYPE_INT8` のみ対応。`DTYPE_SIGN`
  (1bit) は `get_output_bytes`/生バイナリの `set_input` のみ対応。
- 1つのプロセス内で `rt_set_*alloc`/`rt_set_*free` はグローバルに
  共有されるため、複数の `dnnrt.Model` を同時に使う場合もすべて同じ
  アロケータ (MicroPython GCヒープ) を使用する。
