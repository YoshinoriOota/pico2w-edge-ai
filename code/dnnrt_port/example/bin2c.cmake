# バイナリファイルをCのバイト配列定義(.h)へ変換するCMakeスクリプト。
#
# code/dnnrt_port/resource/ の model.nnb / test.bmp はファイルシステムを
# 持たないベアメタル版では読み込めないため、ビルド時にCの配列として
# 埋め込むために使用する。
#
# 使い方 (cmakeスクリプトモード):
#   cmake -DINPUT_FILE=<入力バイナリ> -DOUTPUT_FILE=<出力ヘッダ> \
#         -DARRAY_NAME=<配列名> -P bin2c.cmake
#
# 生成される配列は4バイトアライメント付きで宣言される
# (nn_network_t* へキャストして使うため)。

file(READ "${INPUT_FILE}" hex_content HEX)
string(LENGTH "${hex_content}" hex_length)
math(EXPR array_length "${hex_length} / 2")
string(REGEX REPLACE "(..)" "0x\\1," hex_array "${hex_content}")

file(WRITE "${OUTPUT_FILE}"
"// このファイルは bin2c.cmake が ${INPUT_FILE} から自動生成したものです。
// 手動で編集しないでください。
#pragma once

static const unsigned char ${ARRAY_NAME}[${array_length}] __attribute__((aligned(4))) = {
${hex_array}
};
")
