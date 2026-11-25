# NNC 3.50 直接エクスポート .nnb の Pico 実機 E2E 検証レポート

実行日: 2026-07-08
対象: NNC 3.5.9378 の LeNet サンプル（Fashion-MNIST、10エポック学習済み、
Accuracy 0.9016）を「エクスポート → NNB (NNabla C Runtime file format)」で
直接出力した model.nnb（316,936 byte）を、Pico 2 W の dnnrt で実行。

## 結論

- **NNC 3.50 の直接エクスポート .nnb は、無変換で Pico の DNNRT で動作する**
  （nnb format 3、nnabla_cli 不要）。書籍ワークフローの「変換ステージ廃止」を実機で裏付け
- エクスポート経路: 学習/評価タブの学習結果を右クリック → エクスポート →
  **NNB (NNabla C Runtime file format)**（図版 book/figures/nnc/09_nnc_export_nnb.png）

## 実測値（LeNet 310KB モデル）

| 項目 | 値 | 参考: 本書14KBモデル (V2) |
|---|---|---|
| model.nnb サイズ | 316,936 byte | 13,964 byte |
| ロード+コンテキスト後のヒープ残 | **69,488 byte** | 369,408 byte |
| forward 1回 | **299 ms** | 90 ms |
| 出力 | (1,10) float32、Softmax 合計 1.0 | (1,11) |

LeNet 級（パラメータ7.9万）でも動作はするが、ヒープ残 69KB では
カメラのフレームバッファ（38.4KB）や Wi-Fi との同居が危うい。
**第8章「モデルをマイコンサイズにする」の動機付けの実測データとして使用する。**

## 発見・修正した問題

### dnnrt_loader.load_model() の一時2倍メモリ確保

旧実装 `bytearray(f.read())` は、read() の bytes とコピー先 bytearray で
一時的に **ファイルサイズの2倍**（LeNet では 634KB）を要求し、
ヒープに載るはずのモデルで MemoryError になっていた。
`os.stat` でサイズ取得 → `bytearray(size)` を1回だけ確保 → `readinto` で
充填する実装に修正（code/dnnrt_upy/lib/dnnrt_loader.py）。

小モデル（14KB）では顕在化しない罠であり、書籍第8章のコラム
「大きなモデルで MemoryError が出たら」の素材にする。

## 数値一致検証（2026-07-08 追記・完了）

Fashion-MNIST テストセット先頭画像（label=9, Ankle boot。公開データから取得、
NNC サンプルの validation/Ankle boot/0.png と同一）を 1/255 正規化で
Pico 実機の LeNet .nnb に入力し、NNC 評価タブの出力と突き合わせた。

| | y'_0 (T-shirt クラスの確率) | 判定 |
|---|---|---|
| NNC 評価タブ（スクリーンショット 06） | 9.9516555e-08 | class 9 |
| Pico 実機（dnnrt） | 9.951655e-08 | class 9 (prob 0.999909) |

**float32 の有効桁（7桁）で完全一致。** PC の学習結果とマイコンの推論結果の
数値的等価性を実証（書籍 9.5 節の題材）。
