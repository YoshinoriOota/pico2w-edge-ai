/**
 * @file infer_example.c
 * @brief DNNRT (nnabla-c-runtime) RP2350 推論サンプル (model.nnb + test.bmp)
 *
 * code/dnnrt_port/resource/model.nnb (28x28x1 float32入力 / 11クラス
 * float32出力) と code/dnnrt_port/resource/test.bmp (28x28, 32bpp BGRA
 * グレースケール) を、ビルド時に bin2c.cmake でCの配列
 * (model_nnb.h / test_bmp.h) として埋め込み、以下のDNNRT APIを
 * RP2350 (Pico2 W) 上で実行する。
 *
 *   rt_allocate_context -> rt_initialize_context -> rt_forward ->
 *   rt_free_context
 *
 * test.bmpの画素データをグレースケール(0.0-1.0)に変換して入力テンソルへ
 * 書き込み、推論結果(11クラスのスコアと予測クラス)をUSBシリアルへ出力する。
 * code/dnnrt_upy/examples/infer_bmp_demo.py と同じ前処理であり、
 * 同じ結果(クラス3, 約99.8%)が得られることを期待値とする。
 */

#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "pico/stdlib.h"

#include <nnablart/network.h>
#include <nnablart/runtime.h>

#include "model_nnb.h"
#include "test_bmp.h"

/// @brief BITMAPFILEHEADER/BITMAPINFOHEADER内のフィールドオフセット
#define BMP_OFFSET_DATA_OFFSET (10)
#define BMP_OFFSET_WIDTH (18)
#define BMP_OFFSET_HEIGHT (22)
#define BMP_OFFSET_BPP (28)

/// @brief 入力画素バッファの最大要素数 (28x28を想定)
#define MAX_INPUT_PIXELS (32 * 32)

/**
 * @brief リトルエンディアンの32bit符号なし整数を読み出す
 * @param p 読み出し位置
 * @return 値
 */
static uint32_t read_u32le(const unsigned char *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
         ((uint32_t)p[3] << 24);
}

/**
 * @brief 32bpp BGRAグレースケールBMPを0.0-1.0のfloat配列に変換する
 *
 * BMPは下から上に格納されているため、出力は上端(y=0)から行優先で並べる。
 * B=G=Rのグレースケール画像を前提に、Gチャンネル(人の目の感度が最も高い
 * チャンネル)を255.0で正規化する。
 *
 * @param bmp   BMPファイルデータ
 * @param out   変換結果を書き込む先 (width*height要素)
 * @param max_n out の要素数
 * @return 変換した画素数 (width*height)。bpp!=32 または max_n超過時は-1
 */
static int bmp32_to_gray_float(const unsigned char *bmp, float *out, int max_n) {
  uint32_t data_offset = read_u32le(bmp + BMP_OFFSET_DATA_OFFSET);
  int32_t width = (int32_t)read_u32le(bmp + BMP_OFFSET_WIDTH);
  int32_t height = (int32_t)read_u32le(bmp + BMP_OFFSET_HEIGHT);
  uint16_t bpp = (uint16_t)(bmp[BMP_OFFSET_BPP] | (bmp[BMP_OFFSET_BPP + 1] << 8));

  if (bpp != 32 || width <= 0 || height <= 0 || width * height > max_n) {
    return -1;
  }

  int row_size = width * 4;
  for (int32_t y = 0; y < height; y++) {
    const unsigned char *row = bmp + data_offset + (size_t)(height - 1 - y) * row_size;
    for (int32_t x = 0; x < width; x++) {
      /* BGRA順の2バイト目 = G(緑)チャンネル */
      out[y * width + x] = (float)row[x * 4 + 1] / 255.0f;
    }
  }
  return width * height;
}

/**
 * @brief エントリポイント
 *
 * model.nnb を rt_initialize_context() でロードし、test.bmp から作成した
 * 入力テンソルで rt_forward() を実行、出力テンソル(11クラス)とその中で
 * 最大のクラスをUSBシリアルへ出力する。
 *
 * @return 使用しない (組み込みのため戻らない)
 */
int main(void) {
  stdio_init_all();

  /* USBシリアル接続待ち */
  sleep_ms(3000);

  printf("=== DNNRT RP2350 inference example (model.nnb + test.bmp) ===\n");
  printf("NNabla version    : %s\n", rt_nnabla_version());
  printf("C-Runtime version : %s\n", rt_c_runtime_version());
  printf("NNB format version: %d\n", rt_nnb_version());

  rt_context_pointer context = 0;
  rt_return_value_t ret = rt_allocate_context(&context);
  if (ret != RT_RET_NOERROR) {
    printf("rt_allocate_context failed (%d)\n", (int)ret);
    while (1) {
      tight_loop_contents();
    }
  }

  nn_network_t *net = (nn_network_t *)model_nnb;
  ret = rt_initialize_context(context, net);
  if (ret != RT_RET_NOERROR) {
    printf("rt_initialize_context failed (%d)\n", (int)ret);
    while (1) {
      tight_loop_contents();
    }
  }

  printf("inputs : %d\n", rt_num_of_input(context));
  printf("outputs: %d\n", rt_num_of_output(context));

  nn_variable_t *in_var = rt_input_variable(context, 0);
  int in_elems = rt_input_size(context, 0);
  printf("input[0]  elements=%d dtype=%d fp_pos=%d\n", in_elems,
         (int)in_var->type, (int)in_var->fp_pos);

  static float input_pixels[MAX_INPUT_PIXELS];
  int n = bmp32_to_gray_float(test_bmp, input_pixels, MAX_INPUT_PIXELS);

  if (n != in_elems || in_var->type != NN_DATA_TYPE_FLOAT) {
    printf("input size/dtype mismatch (bmp pixels=%d, model elements=%d, "
           "dtype=%d)\n",
           n, in_elems, (int)in_var->type);
    while (1) {
      tight_loop_contents();
    }
  }

  memcpy(rt_input_buffer(context, 0), input_pixels, sizeof(float) * (size_t)in_elems);

  ret = rt_forward(context);
  printf("rt_forward: %s\n", (ret == RT_RET_NOERROR) ? "OK" : "NG");

  int out_elems = rt_output_size(context, 0);
  const float *out = (const float *)rt_output_buffer(context, 0);

  int best = 0;
  for (int i = 0; i < out_elems; i++) {
    printf("output[%d] = %f\n", i, (double)out[i]);
    if (out[i] > out[best]) {
      best = i;
    }
  }
  printf("predicted class: %d (score=%f)\n", best, (double)out[best]);

  rt_free_context(&context);

  printf("=== done ===\n");

  while (1) {
    tight_loop_contents();
  }
}
