"""model.nnb と test.bmp (28x28, 32bpp BGRA グレースケール) を使った推論サンプル.

test.bmp はボトムアップ格納の32bpp BMP (BITMAPFILEHEADER 14byte +
BITMAPINFOHEADER 40byte = オフセット54) を想定する。
B=G=R のグレースケール画像として G チャンネルを読み、
0.0-1.0 に正規化して model.input_shape(0) (例: (1,1,28,28)) の
順序 (行優先、上から下) に並べて set_input() へ渡す。

G チャンネルを使うのは、人の目の感度がG(緑)に最も高く、画像認識用途では
グレースケール化の代表値としてGを用いるのが通例であるため。
"""

import dnnrt_loader


def load_bmp_gray(path):
    """32bpp BGRA グレースケールBMPを読み込み、0.0-1.0のfloatリストを返す.

    :param path: BMPファイルのパス
    :return: 上から下・左から右の行優先で並んだ画素値 (0.0-1.0) のリスト
    """
    with open(path, "rb") as f:
        data = f.read()

    data_offset = int.from_bytes(data[10:14], "little")
    width = int.from_bytes(data[18:22], "little")
    height = int.from_bytes(data[22:26], "little")
    bpp = int.from_bytes(data[28:30], "little")
    if bpp != 32:
        raise ValueError("expected 32bpp BMP, got %dbpp" % bpp)

    row_size = width * 4
    pixels = [0.0] * (width * height)
    for y in range(height):
        # BMPは下から上に格納されているため、出力の上端(y=0)はBMPの最終行になる
        src_row = data_offset + (height - 1 - y) * row_size
        for x in range(width):
            # BGRA順の2バイト目 = G(緑)チャンネル
            g = data[src_row + x * 4 + 1]
            pixels[y * width + x] = g / 255.0
    return pixels


model = dnnrt_loader.load_model("model.nnb")
print(dnnrt_loader.summary(model))

img = load_bmp_gray("test.bmp")
print("input pixels:", len(img))

model.set_input(0, img)
model.forward()

out = model.get_output(0)
print("output:", out)

best = 0
for i in range(1, len(out)):
    if out[i] > out[best]:
        best = i
print("predicted class:", best, "score:", out[best])

model.close()
