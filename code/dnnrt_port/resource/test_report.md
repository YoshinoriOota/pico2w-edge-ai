# dnnrt_upy 推論テストレポート

実行日: 2026-06-12
対象: `code/dnnrt_upy`（DNNRT MicroPythonラッパー）/ 実機 Pico2 W (RP2350, COM17)
使用リソース: `code/dnnrt_port/resource/model.nnb`, `code/dnnrt_port/resource/test.bmp`

## 1. BOOTSELで起動し直す必要はあるか

- **当初は不要**。ファームウェアは前回のセッションで `dnnrt` usermod組み込み版を
  書き込み済みで、ボード(COM17)は通常モードで稼働中だった。
  `model.nnb`/`test.bmp`/テストスクリプトの転送・実行は mpremote のシリアル
  REPL経由で、BOOTSELなしで実施できた。
- ただし、テスト中に `moddnnrt.c` の不具合（後述）を発見・修正したため、
  **今回は1回だけファームウェアの再ビルド・再書き込みが必要**になった。
  - 物理的なBOOTSELボタン操作は不要で、稼働中のボードに対し
    ```python
    import machine; machine.bootloader()
    ```
    をリモート実行することでBOOTSEL(マスストレージ)モードに遷移させ、
    `firmware.uf2` をコピーして再起動した。
- 今後、`model.nnb` やPythonスクリプトの入れ替えのみであれば、現在の
  ファームウェアのままBOOTSEL不要でテスト可能。

## 2. model.nnb の内容確認

`dnnrt_loader.summary()` の出力（修正後のファームウェアでの再確認結果）:

```
nnabla version : 1.24.0.dev1
runtime version: 1.2.0.dev1_c1
nnb format     : 3
input[0]  shape=(1, 1, 28, 28) dtype=float32 fp_pos=0 size=3136bytes
output[0] shape=(1, 11) dtype=float32 fp_pos=0 size=44bytes
```

- 入力: (1,1,28,28) float32 = 784要素 = 3136byte。28×28の1チャンネル
  画像（MNIST形式）に対応。
- 出力: (1,11) float32 = 11要素 = 44byte。11クラス分類器。

`test.bmp` は 28×28, 32bpp BGRA グレースケール（B=G=R, A=255固定、
画素値レンジ 65-255）。`model.nnb` の入力形状と一致する。

## 3. 発見した不具合と修正

### 不具合: `input_size()`/`output_size()` が「要素数」を「バイト数」として
扱っていた

`nnabla-c-runtime` の `rt_input_size()`/`rt_output_size()`
(`analyze/dnnrt_sdk/.../src/runtime/runtime.c`) は、形状の各次元の積
（**要素数**）を返す関数だが、`code/dnnrt_upy/src/moddnnrt.c` はこの値を
**バイト数**として `input_size()`/`output_size()` の戻り値や、
`set_input()`/`get_output()`/`get_output_bytes()` のバッファサイズ検証に
そのまま使っていた。

FLOAT32 (4byte/要素) の場合、要素数 ≠ バイト数 となるため、修正前は
以下のように `set_input()` が正しく動作しなかった（実機で確認）:

```
input_size(0) = 784                 # 本来は 3136 (=784*4byte) であるべき
output_size(0) = 11                 # 本来は 44 (=11*4byte) であるべき
set_input list[784]      -> ValueError('input element count mismatch')
set_input bytearray(3136) -> ValueError('input buffer size mismatch')
set_input bytearray(784)  -> OK（だが3136byteバッファの先頭784byteのみ
                                書き込まれ、残りは未初期化のまま＝結果不正）
```

INT8モデル（1byte=1要素）は偶然この不一致が発生しないため、これまでの
ビルド検証では問題が表面化していなかった。

### 修正内容 (`code/dnnrt_upy/src/moddnnrt.c`)

- `dnnrt_var_byte_size(var, elem_count)` を追加し、dtypeごとの
  実バイト数（FLOAT=×4, INT16=×2, INT8=×1, SIGN=⌈要素数/8⌉）を計算する
  ようにした。
- `input_size()`/`output_size()` は `dnnrt_var_byte_size()` の結果
  （正しいバイト数）を返すよう修正。README記載の「バイトサイズ」という
  仕様に一致させた。
- `dnnrt_pack_values`/`dnnrt_unpack_values` は要素数 (`elem_count`) を
  直接受け取り、`list`/`tuple` の長さと要素数を比較するよう修正。
- `set_input()`/`get_output_bytes()` の生バイト列パスは、修正後の
  `input_size()`/`output_size()`（= 正しいバイト数）と比較するよう修正。

修正後、ファームウェアを再ビルド・再書き込みし、実機で再確認:

```
input_size(0) = 3136
output_size(0) = 44
set_input list[784]       -> OK
set_input bytearray(3136) -> OK
set_input bytearray(784)  -> ValueError('input buffer size mismatch')  (正しく拒否)
```

## 4. 推論テスト結果

新規作成した `code/dnnrt_upy/examples/infer_bmp_demo.py` を実行
（`test.bmp` を28x28グレースケール・0.0-1.0正規化の784要素floatリストに
変換し、`set_input(0, ...)` → `forward()` → `get_output(0)`）。

```
input pixels: 784
output: [4.584991e-06, 4.0351e-06, 0.0006398771, 0.99801192, 4.571818e-06,
         0.00052035184, 6.94331968e-07, 4.20222136e-07, 0.0007206803,
         9.264654e-05, 1.5216736e-11]
predicted class: 3   score: 0.99801192
```

出力11要素の合計は約1.0（softmax相当）であり、クラス3に99.8%という
非常にシャープな分布が得られた。`/255.0` 正規化の仮定がモデルの学習時
前処理と一致していると考えられる。`set_input` → `forward` → `get_output`
が一連で正しく動作することを実機で確認できた。

## 5. 変更ファイル一覧

- `code/dnnrt_upy/src/moddnnrt.c` — `input_size`/`output_size`/
  `set_input`/`get_output`/`get_output_bytes` のサイズ計算修正
- `code/dnnrt_upy/examples/infer_bmp_demo.py` — BMP画像を使った推論サンプル
  （新規）
- `code/dnnrt_port/resource/test_report.md` — 本レポート（新規）

## 6. まとめ

- `model.nnb`（28x28x1 float32入力 / 11クラスfloat32出力）は
  `rt_initialize_context` 〜 `rt_forward` まで実機上で正常に動作することを
  確認した（本リポジトリで初めてエンドツーエンド推論に成功したモデル）。
- テスト過程で発見した `moddnnrt.c` のサイズ計算バグ（FLOAT32モデルで
  `set_input`/`get_output` が機能しない不具合）を修正し、ファームウェアを
  再ビルド・再書き込みして検証済み。
- `model.nnb`/`test.bmp` は今後の `dnnrt_upy` 改修時の回帰テスト用
  リファレンス（「クラス3・99.8%」が再現すればOK）として利用できる。
