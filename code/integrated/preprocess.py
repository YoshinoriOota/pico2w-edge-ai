"""前処理: 160x120 RGB565 フレーム → 28x28 グレースケール 0.0-1.0 (Pico側).

収集ツール (code/collect/collect_tool.py) の保存処理と 1 画素単位で
同一のロジックであること (書籍 第7章 鉄則その1)。変更する場合は必ず両方を
同時に変更すること。
"""


def preprocess(buf, float_out):
    """中央 112x112 を 4 画素間引きし、輝度化して 1/255 正規化する.

    :param buf: QQVGA RGB565 フレーム (38400 byte)
    :param float_out: 784 要素の list (結果を書き込む)
    """
    k = 0
    for j in range(28):
        row = (4 + j * 4) * 160
        for i in range(28):
            idx = (row + 24 + i * 4) * 2
            v = (buf[idx] << 8) | buf[idx + 1]
            r = (v >> 8) & 0xF8
            g = (v >> 3) & 0xFC
            b = (v << 3) & 0xF8
            float_out[k] = ((r + g + g + b) >> 2) / 255.0
            k += 1
