"""dnnrt (DNNRT MicroPythonラッパー) の使用例.

事前に以下を Pico のフラッシュ (ファイルシステムのルート) へ転送しておくこと。

  - model.nnb        : nnabla_cli convert で生成した推論モデル
  - dnnrt_loader.py  : code/dnnrt_upy/lib/dnnrt_loader.py

mpremote を使う場合の例::

    mpremote cp model.nnb :model.nnb
    mpremote cp ../lib/dnnrt_loader.py :dnnrt_loader.py
    mpremote cp infer_demo.py :infer_demo.py
    mpremote run infer_demo.py

このスクリプトは以下を行う。
  1. model.nnb を読み込み dnnrt.Model を生成
  2. 入出力テンソルの形状・データ型を表示
  3. ダミー入力 (全要素0.0) を設定して推論を実行
  4. 出力テンソルの値を表示
"""

import dnnrt
import dnnrt_loader


def main():
    print("loading model.nnb ...")
    model = dnnrt_loader.load_model("model.nnb")

    print(dnnrt_loader.summary(model))

    # --- ダミー入力 (全要素0.0) を作成して input[0] に設定 ---
    # 実際のアプリケーションでは、カメラフレームやセンサデータを
    # model.input_dtype(0) / model.input_shape(0) に合わせて整形し、
    # model.set_input(0, data) に渡す。
    # data には list[float] の他、bytes/bytearray/array (生バイナリ形式)
    # も指定できる。
    in_shape = model.input_shape(0)
    n = dnnrt_loader.num_elements(in_shape)
    print("set dummy input[0]: shape=%s (%d elements)" % (in_shape, n))
    model.set_input(0, [0.0] * n)

    # --- 推論実行 ---
    model.forward()
    print("forward done")

    # --- 出力テンソルを表示 ---
    for i in range(model.num_outputs()):
        out = model.get_output(i)
        print("output[%d] = %s" % (i, out))

    model.close()


if __name__ == "__main__":
    main()
