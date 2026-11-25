"""dnnrt.Model 用のロードユーティリティ.

model.nnb (NNC で学習し nnabla_cli convert で生成した nnabla-c-runtime
形式のバイナリ) を Pico のフラッシュ上のファイルシステムから読み込み、
dnnrt.Model インスタンスを生成する。

使い方::

    import dnnrt_loader

    model = dnnrt_loader.load_model("model.nnb")
    print(dnnrt_loader.summary(model))

NNB内の重みデータは読み込んだバッファを直接参照するため、
返却された Model が不要になるまでバッファを解放してはならない。
本モジュールは Model オブジェクト自身にバッファの参照を保持させることで
これを保証している (moddnnrt.c 側で nnb_buf として保持)。
"""

import dnnrt

#: nn_data_type_t (network.h) の値を表示用文字列に変換するテーブル
DTYPE_NAMES = {
    dnnrt.DTYPE_FLOAT: "float32",
    dnnrt.DTYPE_INT16: "int16",
    dnnrt.DTYPE_INT8: "int8",
    dnnrt.DTYPE_SIGN: "sign",
}


def load_model(path):
    """model.nnb をファイルシステムから読み込み dnnrt.Model を生成する.

    バッファはファイルサイズちょうどを一度だけ確保し readinto で埋める。
    (f.read() を bytearray() に渡す実装だと一時的に2倍のメモリを要求し、
    大きなモデルでヒープに載るはずのものが MemoryError になる)

    :param path: model.nnb のパス (例: "model.nnb")
    :return: 初期化済みの dnnrt.Model インスタンス
    """
    import os

    size = os.stat(path)[6]
    buf = bytearray(size)
    mv = memoryview(buf)
    n = 0
    with open(path, "rb") as f:
        while n < size:
            k = f.readinto(mv[n:])
            if not k:
                raise OSError("short read: %d/%d" % (n, size))
            n += k
    return dnnrt.Model(buf)


def num_elements(shape):
    """形状タプルから要素数を計算する.

    :param shape: input_shape()/output_shape() が返すタプル
    :return: 要素数 (各次元の積)
    """
    n = 1
    for d in shape:
        n *= d
    return n


def summary(model):
    """モデルの入出力情報を文字列にまとめる (デバッグ表示用).

    :param model: dnnrt.Model インスタンス
    :return: 入出力の形状・データ型・サイズを含む複数行の文字列
    """
    lines = []
    lines.append("nnabla version : %s" % dnnrt.nnabla_version())
    lines.append("runtime version: %s" % dnnrt.runtime_version())
    lines.append("nnb format     : %d" % dnnrt.nnb_version())

    for i in range(model.num_inputs()):
        shape = model.input_shape(i)
        dtype, fp_pos = model.input_dtype(i)
        lines.append(
            "input[%d]  shape=%s dtype=%s fp_pos=%d size=%dbytes"
            % (i, shape, DTYPE_NAMES.get(dtype, dtype), fp_pos, model.input_size(i))
        )

    for i in range(model.num_outputs()):
        shape = model.output_shape(i)
        dtype, fp_pos = model.output_dtype(i)
        lines.append(
            "output[%d] shape=%s dtype=%s fp_pos=%d size=%dbytes"
            % (i, shape, DTYPE_NAMES.get(dtype, dtype), fp_pos, model.output_size(i))
        )

    return "\n".join(lines)
