/**
 * @file moddnnrt.c
 * @brief DNNRT (nnabla-c-runtime) を MicroPython から利用するためのバインディング
 *
 * model.nnb (NNC で学習・変換した nnabla-c-runtime 形式のネットワーク定義) を
 * Pico のメモリ上に展開し、Python から以下の操作を行えるようにする。
 *
 *   - dnnrt.Model(buf)    : NNBデータ(bytes/bytearray等)からモデルを初期化
 *   - model.set_input()   : 入力テンソルへデータを設定
 *   - model.forward()     : 推論を実行
 *   - model.get_output()  : 出力テンソルを取得
 *
 * 内部的には rt_allocate_context -> rt_initialize_context -> rt_forward ->
 * rt_free_context という DNNRT のシーケンスをそのまま呼び出す。
 *
 * 中間バッファ(アクティベーション)の確保には MicroPython の GC ヒープ
 * (gc_alloc/gc_free) を使用するように rt_set_*malloc/free で差し替える。
 * これにより DNNRT のメモリ使用量が MicroPython の GC 管理下に入り、
 * newlib 側ヒープと分離して肥大化することを防ぐ。
 */

#include <string.h>
#include <stdint.h>

#include "py/runtime.h"
#include "py/objlist.h"
#include "py/gc.h"

#include <nnablart/network.h>
#include <nnablart/runtime.h>

/// @brief input_shape()/output_shape() で扱える最大次元数
#define DNNRT_MAX_DIM (8)

////////////////////////////////////////////////////////////////////////////
// アロケータ (DNNRT の中間バッファを MicroPython の GC ヒープに割り付ける)
////////////////////////////////////////////////////////////////////////////

/**
 * @brief DNNRT用 malloc (GCヒープから確保)
 * @param size 確保するバイト数
 * @return 確保したメモリへのポインタ (失敗時はNULL)
 */
static void *dnnrt_gc_malloc(size_t size) {
  return gc_alloc(size, 0);
}

/**
 * @brief DNNRT用 free (GCヒープへ返却)
 * @param ptr 解放するメモリへのポインタ
 */
static void dnnrt_gc_free(void *ptr) {
  gc_free(ptr);
}

/**
 * @brief DNNRTのアロケータをGCヒープ版に差し替える(初回のみ)
 *
 * rt_set_*alloc/free はランタイム全体で共有されるグローバル関数ポインタの
 * ため、プロセス内で一度だけ設定すればよい。
 */
static void dnnrt_install_allocator(void) {
  static bool installed = false;
  if (!installed) {
    rt_set_malloc(dnnrt_gc_malloc);
    rt_set_free(dnnrt_gc_free);
    rt_set_variable_malloc(dnnrt_gc_malloc);
    rt_set_variable_free(dnnrt_gc_free);
    installed = true;
  }
}

////////////////////////////////////////////////////////////////////////////
// dnnrt.Model オブジェクト
////////////////////////////////////////////////////////////////////////////

/// @brief dnnrt.Model のインスタンスデータ
typedef struct _dnnrt_model_obj_t {
  mp_obj_base_t base;
  rt_context_pointer context; ///< DNNRTコンテキスト (NULLなら解放済み)
  mp_obj_t nnb_buf;            ///< NNBデータの参照 (GCで解放されないように保持)
} dnnrt_model_obj_t;

const mp_obj_type_t dnnrt_model_type;

/**
 * @brief 解放済みでないModelを取得する
 * @param self_in dnnrt.Model インスタンス
 * @return dnnrt_model_obj_t へのポインタ
 */
static dnnrt_model_obj_t *dnnrt_model_get(mp_obj_t self_in) {
  dnnrt_model_obj_t *self = MP_OBJ_TO_PTR(self_in);
  if (self->context == NULL) {
    mp_raise_msg(&mp_type_RuntimeError, MP_ERROR_TEXT("model is already closed"));
  }
  return self;
}

/**
 * @brief 値を四捨五入し範囲制限した整数に変換する
 * @param v 入力値
 * @param lo 最小値
 * @param hi 最大値
 * @return 範囲制限後の整数値
 */
static int32_t dnnrt_clamp_round(float v, int32_t lo, int32_t hi) {
  float r = v + (v >= 0.0f ? 0.5f : -0.5f);
  int32_t iv = (int32_t)r;
  if (iv < lo) {
    iv = lo;
  }
  if (iv > hi) {
    iv = hi;
  }
  return iv;
}

/**
 * @brief 変数1個あたりの実バイトサイズを計算する (要素数 × 1要素のバイト数)
 *
 * rt_input_size()/rt_output_size() が返す「要素数」(形状の各次元の積) は
 * バイト数ではないため、dtype に応じたバイト数へ変換するために用いる。
 *
 * @param var 対象変数のディスクリプタ (型を持つ)
 * @param elem_count 要素数 (rt_input_size()/rt_output_size() の戻り値)
 * @return バイト数。NN_DATA_TYPE_SIGN は1要素1bitとして詰めたバイト数を返す。
 */
static size_t dnnrt_var_byte_size(const nn_variable_t *var, int elem_count) {
  switch (var->type) {
    case NN_DATA_TYPE_FLOAT:
      return (size_t)elem_count * sizeof(float);
    case NN_DATA_TYPE_INT16:
      return (size_t)elem_count * sizeof(int16_t);
    case NN_DATA_TYPE_INT8:
      return (size_t)elem_count * sizeof(int8_t);
    case NN_DATA_TYPE_SIGN:
      return ((size_t)elem_count + 7) / 8;
    default:
      return (size_t)elem_count;
  }
}

/**
 * @brief Python数値リストをNNBが要求する形式のバイナリへ変換して書き込む
 * @param var  対象変数のディスクリプタ (型・固定小数点位置を持つ)
 * @param dst  書き込み先バッファ (rt_input_buffer)
 * @param elem_count dst の要素数 (rt_input_size() の戻り値)
 * @param items mp_obj_t の配列 (リスト/タプルの要素)
 * @param len items の要素数
 */
static void dnnrt_pack_values(const nn_variable_t *var, void *dst, int elem_count,
                               mp_obj_t *items, size_t len) {
  switch (var->type) {
    case NN_DATA_TYPE_FLOAT: {
      if (len != (size_t)elem_count) {
        mp_raise_ValueError(MP_ERROR_TEXT("input element count mismatch"));
      }
      float *p = (float *)dst;
      for (size_t i = 0; i < len; i++) {
        p[i] = (float)mp_obj_get_float(items[i]);
      }
      return;
    }
    case NN_DATA_TYPE_INT16: {
      if (len != (size_t)elem_count) {
        mp_raise_ValueError(MP_ERROR_TEXT("input element count mismatch"));
      }
      int16_t *p = (int16_t *)dst;
      float scale = (float)(1 << var->fp_pos);
      for (size_t i = 0; i < len; i++) {
        p[i] = (int16_t)dnnrt_clamp_round(mp_obj_get_float(items[i]) * scale, INT16_MIN, INT16_MAX);
      }
      return;
    }
    case NN_DATA_TYPE_INT8: {
      if (len != (size_t)elem_count) {
        mp_raise_ValueError(MP_ERROR_TEXT("input element count mismatch"));
      }
      int8_t *p = (int8_t *)dst;
      float scale = (float)(1 << var->fp_pos);
      for (size_t i = 0; i < len; i++) {
        p[i] = (int8_t)dnnrt_clamp_round(mp_obj_get_float(items[i]) * scale, INT8_MIN, INT8_MAX);
      }
      return;
    }
    default:
      mp_raise_NotImplementedError(MP_ERROR_TEXT("list/tuple input is not supported for this dtype; pass raw bytes instead"));
  }
}

/**
 * @brief NNB形式のバイナリをPythonの数値リストへ変換する
 * @param var 対象変数のディスクリプタ (型・固定小数点位置を持つ)
 * @param src 読み出し元バッファ (rt_output_buffer)
 * @param elem_count src の要素数 (rt_output_size() の戻り値)
 * @return float を要素とする list オブジェクト
 */
static mp_obj_t dnnrt_unpack_values(const nn_variable_t *var, const void *src, int elem_count) {
  size_t n = (size_t)elem_count;
  switch (var->type) {
    case NN_DATA_TYPE_FLOAT: {
      const float *p = (const float *)src;
      mp_obj_t list_obj = mp_obj_new_list(n, NULL);
      mp_obj_list_t *list = MP_OBJ_TO_PTR(list_obj);
      for (size_t i = 0; i < n; i++) {
        list->items[i] = mp_obj_new_float(p[i]);
      }
      return list_obj;
    }
    case NN_DATA_TYPE_INT16: {
      const int16_t *p = (const int16_t *)src;
      float scale = 1.0f / (float)(1 << var->fp_pos);
      mp_obj_t list_obj = mp_obj_new_list(n, NULL);
      mp_obj_list_t *list = MP_OBJ_TO_PTR(list_obj);
      for (size_t i = 0; i < n; i++) {
        list->items[i] = mp_obj_new_float(p[i] * scale);
      }
      return list_obj;
    }
    case NN_DATA_TYPE_INT8: {
      const int8_t *p = (const int8_t *)src;
      float scale = 1.0f / (float)(1 << var->fp_pos);
      mp_obj_t list_obj = mp_obj_new_list(n, NULL);
      mp_obj_list_t *list = MP_OBJ_TO_PTR(list_obj);
      for (size_t i = 0; i < n; i++) {
        list->items[i] = mp_obj_new_float(p[i] * scale);
      }
      return list_obj;
    }
    default:
      mp_raise_NotImplementedError(MP_ERROR_TEXT("get_output() is not supported for this dtype; use get_output_bytes() instead"));
      return mp_const_none;
  }
}

/**
 * @brief dnnrt.Model(nnb) コンストラクタ
 *
 * nnb (bytes/bytearray等、bufferプロトコル対応オブジェクト) を
 * nn_network_t として DNNRT に渡し、rt_allocate_context ->
 * rt_initialize_context までを行う。
 *
 * NNB内の重みデータは nnb バッファを直接指すため、Model が生きている間は
 * nnb への参照を保持し続ける(GCで回収されないようにする)。
 *
 * @param type dnnrt_model_type
 * @param n_args 位置引数の数 (1: nnb)
 * @param n_kw キーワード引数の数 (0)
 * @param args args[0] = nnb データ
 * @return 生成された dnnrt.Model インスタンス
 */
static mp_obj_t dnnrt_model_make_new(const mp_obj_type_t *type, size_t n_args,
                                      size_t n_kw, const mp_obj_t *args) {
  mp_arg_check_num(n_args, n_kw, 1, 1, false);

  mp_buffer_info_t bufinfo;
  mp_get_buffer_raise(args[0], &bufinfo, MP_BUFFER_READ);

  if (bufinfo.len < sizeof(nn_network_t)) {
    mp_raise_ValueError(MP_ERROR_TEXT("nnb data is too small"));
  }
  if (((uintptr_t)bufinfo.buf) & 0x3u) {
    mp_raise_ValueError(MP_ERROR_TEXT("nnb buffer must be 4-byte aligned"));
  }

  dnnrt_install_allocator();

  dnnrt_model_obj_t *self = m_new_obj(dnnrt_model_obj_t);
  self->base.type = type;
  self->context = NULL;
  self->nnb_buf = args[0];

  rt_return_value_t ret = rt_allocate_context(&self->context);
  if (ret != RT_RET_NOERROR) {
    mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("rt_allocate_context failed (%d)"), (int)ret);
  }

  nn_network_t *net = (nn_network_t *)bufinfo.buf;
  ret = rt_initialize_context(self->context, net);
  if (ret != RT_RET_NOERROR) {
    rt_free_context(&self->context);
    mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("rt_initialize_context failed (%d)"), (int)ret);
  }

  return MP_OBJ_FROM_PTR(self);
}

/**
 * @brief 入力テンソルの数を取得する (dnnrt.Model.num_inputs)
 */
static mp_obj_t dnnrt_model_num_inputs(mp_obj_t self_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  return mp_obj_new_int(rt_num_of_input(self->context));
}
static MP_DEFINE_CONST_FUN_OBJ_1(dnnrt_model_num_inputs_obj, dnnrt_model_num_inputs);

/**
 * @brief 出力テンソルの数を取得する (dnnrt.Model.num_outputs)
 */
static mp_obj_t dnnrt_model_num_outputs(mp_obj_t self_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  return mp_obj_new_int(rt_num_of_output(self->context));
}
static MP_DEFINE_CONST_FUN_OBJ_1(dnnrt_model_num_outputs_obj, dnnrt_model_num_outputs);

/**
 * @brief 入力テンソルのバイトサイズを取得する (dnnrt.Model.input_size)
 */
static mp_obj_t dnnrt_model_input_size(mp_obj_t self_in, mp_obj_t index_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  size_t index = (size_t)mp_obj_get_int(index_in);
  int elem_count = rt_input_size(self->context, index);
  nn_variable_t *var = rt_input_variable(self->context, index);
  if (elem_count < 0 || var == NULL) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid input index"));
  }
  return mp_obj_new_int((mp_int_t)dnnrt_var_byte_size(var, elem_count));
}
static MP_DEFINE_CONST_FUN_OBJ_2(dnnrt_model_input_size_obj, dnnrt_model_input_size);

/**
 * @brief 出力テンソルのバイトサイズを取得する (dnnrt.Model.output_size)
 */
static mp_obj_t dnnrt_model_output_size(mp_obj_t self_in, mp_obj_t index_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  size_t index = (size_t)mp_obj_get_int(index_in);
  int elem_count = rt_output_size(self->context, index);
  nn_variable_t *var = rt_output_variable(self->context, index);
  if (elem_count < 0 || var == NULL) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid output index"));
  }
  return mp_obj_new_int((mp_int_t)dnnrt_var_byte_size(var, elem_count));
}
static MP_DEFINE_CONST_FUN_OBJ_2(dnnrt_model_output_size_obj, dnnrt_model_output_size);

/**
 * @brief 入力テンソルの形状を取得する (dnnrt.Model.input_shape)
 * @return 各次元のサイズを格納したタプル
 */
static mp_obj_t dnnrt_model_input_shape(mp_obj_t self_in, mp_obj_t index_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  size_t index = (size_t)mp_obj_get_int(index_in);

  int dim = rt_input_dimension(self->context, index);
  if (dim < 0 || dim > DNNRT_MAX_DIM) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid input index"));
  }

  mp_obj_t items[DNNRT_MAX_DIM];
  for (int i = 0; i < dim; i++) {
    items[i] = mp_obj_new_int(rt_input_shape(self->context, index, (size_t)i));
  }
  return mp_obj_new_tuple((size_t)dim, items);
}
static MP_DEFINE_CONST_FUN_OBJ_2(dnnrt_model_input_shape_obj, dnnrt_model_input_shape);

/**
 * @brief 出力テンソルの形状を取得する (dnnrt.Model.output_shape)
 * @return 各次元のサイズを格納したタプル
 */
static mp_obj_t dnnrt_model_output_shape(mp_obj_t self_in, mp_obj_t index_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  size_t index = (size_t)mp_obj_get_int(index_in);

  int dim = rt_output_dimension(self->context, index);
  if (dim < 0 || dim > DNNRT_MAX_DIM) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid output index"));
  }

  mp_obj_t items[DNNRT_MAX_DIM];
  for (int i = 0; i < dim; i++) {
    items[i] = mp_obj_new_int(rt_output_shape(self->context, index, (size_t)i));
  }
  return mp_obj_new_tuple((size_t)dim, items);
}
static MP_DEFINE_CONST_FUN_OBJ_2(dnnrt_model_output_shape_obj, dnnrt_model_output_shape);

/**
 * @brief 入力テンソルのデータ型・固定小数点位置を取得する (dnnrt.Model.input_dtype)
 * @return (dtype, fp_pos) のタプル。dtype は dnnrt.DTYPE_* のいずれか。
 */
static mp_obj_t dnnrt_model_input_dtype(mp_obj_t self_in, mp_obj_t index_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  nn_variable_t *var = rt_input_variable(self->context, (size_t)mp_obj_get_int(index_in));
  if (var == NULL) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid input index"));
  }
  mp_obj_t items[2] = {mp_obj_new_int(var->type), mp_obj_new_int(var->fp_pos)};
  return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_2(dnnrt_model_input_dtype_obj, dnnrt_model_input_dtype);

/**
 * @brief 出力テンソルのデータ型・固定小数点位置を取得する (dnnrt.Model.output_dtype)
 * @return (dtype, fp_pos) のタプル。dtype は dnnrt.DTYPE_* のいずれか。
 */
static mp_obj_t dnnrt_model_output_dtype(mp_obj_t self_in, mp_obj_t index_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  nn_variable_t *var = rt_output_variable(self->context, (size_t)mp_obj_get_int(index_in));
  if (var == NULL) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid output index"));
  }
  mp_obj_t items[2] = {mp_obj_new_int(var->type), mp_obj_new_int(var->fp_pos)};
  return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_2(dnnrt_model_output_dtype_obj, dnnrt_model_output_dtype);

/**
 * @brief 入力テンソルへデータを設定する (dnnrt.Model.set_input)
 *
 * data は以下のいずれかを指定できる。
 *   - bytes/bytearray/array 等 (bufferプロトコル対応): NNBの生バイナリ形式
 *     としてそのまま input_size(index) バイト分コピーする。
 *   - list/tuple of float: dtype/fp_pos に応じて float32 または
 *     固定小数点(int16/int8)へ変換して書き込む。
 *
 * @param self_in dnnrt.Model インスタンス
 * @param index_in 入力インデックス
 * @param data_in 設定するデータ
 */
static mp_obj_t dnnrt_model_set_input(mp_obj_t self_in, mp_obj_t index_in, mp_obj_t data_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  size_t index = (size_t)mp_obj_get_int(index_in);

  int elem_count = rt_input_size(self->context, index);
  void *dst = rt_input_buffer(self->context, index);
  nn_variable_t *var = rt_input_variable(self->context, index);
  if (elem_count < 0 || dst == NULL || var == NULL) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid input index"));
  }

  mp_buffer_info_t bufinfo;
  if (mp_get_buffer(data_in, &bufinfo, MP_BUFFER_READ)) {
    size_t byte_size = dnnrt_var_byte_size(var, elem_count);
    if (bufinfo.len != byte_size) {
      mp_raise_ValueError(MP_ERROR_TEXT("input buffer size mismatch"));
    }
    memcpy(dst, bufinfo.buf, bufinfo.len);
    return mp_const_none;
  }

  size_t len;
  mp_obj_t *items;
  mp_obj_get_array(data_in, &len, &items);

  dnnrt_pack_values(var, dst, elem_count, items, len);
  return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_3(dnnrt_model_set_input_obj, dnnrt_model_set_input);

/**
 * @brief 出力テンソルをfloatのリストとして取得する (dnnrt.Model.get_output)
 * @param self_in dnnrt.Model インスタンス
 * @param index_in 出力インデックス
 * @return float を要素とする list オブジェクト
 */
static mp_obj_t dnnrt_model_get_output(mp_obj_t self_in, mp_obj_t index_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  size_t index = (size_t)mp_obj_get_int(index_in);

  int elem_count = rt_output_size(self->context, index);
  void *src = rt_output_buffer(self->context, index);
  nn_variable_t *var = rt_output_variable(self->context, index);
  if (elem_count < 0 || src == NULL || var == NULL) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid output index"));
  }

  return dnnrt_unpack_values(var, src, elem_count);
}
static MP_DEFINE_CONST_FUN_OBJ_2(dnnrt_model_get_output_obj, dnnrt_model_get_output);

/**
 * @brief 出力テンソルを生バイト列として取得する (dnnrt.Model.get_output_bytes)
 *
 * dtype に依存せず、NNBが内部で保持しているバイナリ形式をそのまま返す。
 *
 * @param self_in dnnrt.Model インスタンス
 * @param index_in 出力インデックス
 * @return bytes オブジェクト
 */
static mp_obj_t dnnrt_model_get_output_bytes(mp_obj_t self_in, mp_obj_t index_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  size_t index = (size_t)mp_obj_get_int(index_in);

  int elem_count = rt_output_size(self->context, index);
  void *src = rt_output_buffer(self->context, index);
  nn_variable_t *var = rt_output_variable(self->context, index);
  if (elem_count < 0 || src == NULL || var == NULL) {
    mp_raise_ValueError(MP_ERROR_TEXT("invalid output index"));
  }

  return mp_obj_new_bytes((const byte *)src, dnnrt_var_byte_size(var, elem_count));
}
static MP_DEFINE_CONST_FUN_OBJ_2(dnnrt_model_get_output_bytes_obj, dnnrt_model_get_output_bytes);

/**
 * @brief 順伝播 (推論) を実行する (dnnrt.Model.forward)
 *
 * 事前に set_input() で全ての入力テンソルへデータを設定しておくこと。
 * 結果は get_output()/get_output_bytes() で取得できる。
 */
static mp_obj_t dnnrt_model_forward(mp_obj_t self_in) {
  dnnrt_model_obj_t *self = dnnrt_model_get(self_in);
  rt_return_value_t ret = rt_forward(self->context);
  if (ret != RT_RET_NOERROR) {
    mp_raise_msg_varg(&mp_type_RuntimeError, MP_ERROR_TEXT("rt_forward failed (%d)"), (int)ret);
  }
  return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(dnnrt_model_forward_obj, dnnrt_model_forward);

/**
 * @brief コンテキストを解放する (dnnrt.Model.close)
 *
 * 解放後にメソッドを呼び出すと RuntimeError となる。
 * 複数回呼び出しても安全 (2回目以降は何もしない)。
 *
 * close() を呼ばずに Model オブジェクトが破棄された場合も、内部の
 * コンテキスト・中間バッファは GCヒープ (gc_alloc) 経由で確保されているため
 * 次のGCサイクルで回収されるが、解放タイミングを確定させたい場合は
 * 明示的に close() を呼ぶこと。
 */
static mp_obj_t dnnrt_model_close(mp_obj_t self_in) {
  dnnrt_model_obj_t *self = MP_OBJ_TO_PTR(self_in);
  if (self->context != NULL) {
    rt_free_context(&self->context);
    self->context = NULL;
  }
  self->nnb_buf = mp_const_none;
  return mp_const_none;
}
static MP_DEFINE_CONST_FUN_OBJ_1(dnnrt_model_close_obj, dnnrt_model_close);

/// @brief dnnrt.Model のメソッド一覧
static const mp_rom_map_elem_t dnnrt_model_locals_dict_table[] = {
    {MP_ROM_QSTR(MP_QSTR_num_inputs), MP_ROM_PTR(&dnnrt_model_num_inputs_obj)},
    {MP_ROM_QSTR(MP_QSTR_num_outputs), MP_ROM_PTR(&dnnrt_model_num_outputs_obj)},
    {MP_ROM_QSTR(MP_QSTR_input_size), MP_ROM_PTR(&dnnrt_model_input_size_obj)},
    {MP_ROM_QSTR(MP_QSTR_output_size), MP_ROM_PTR(&dnnrt_model_output_size_obj)},
    {MP_ROM_QSTR(MP_QSTR_input_shape), MP_ROM_PTR(&dnnrt_model_input_shape_obj)},
    {MP_ROM_QSTR(MP_QSTR_output_shape), MP_ROM_PTR(&dnnrt_model_output_shape_obj)},
    {MP_ROM_QSTR(MP_QSTR_input_dtype), MP_ROM_PTR(&dnnrt_model_input_dtype_obj)},
    {MP_ROM_QSTR(MP_QSTR_output_dtype), MP_ROM_PTR(&dnnrt_model_output_dtype_obj)},
    {MP_ROM_QSTR(MP_QSTR_set_input), MP_ROM_PTR(&dnnrt_model_set_input_obj)},
    {MP_ROM_QSTR(MP_QSTR_get_output), MP_ROM_PTR(&dnnrt_model_get_output_obj)},
    {MP_ROM_QSTR(MP_QSTR_get_output_bytes), MP_ROM_PTR(&dnnrt_model_get_output_bytes_obj)},
    {MP_ROM_QSTR(MP_QSTR_forward), MP_ROM_PTR(&dnnrt_model_forward_obj)},
    {MP_ROM_QSTR(MP_QSTR_close), MP_ROM_PTR(&dnnrt_model_close_obj)},
};
static MP_DEFINE_CONST_DICT(dnnrt_model_locals_dict, dnnrt_model_locals_dict_table);

MP_DEFINE_CONST_OBJ_TYPE(dnnrt_model_type, MP_QSTR_Model, MP_TYPE_FLAG_NONE,
                         make_new, dnnrt_model_make_new,
                         locals_dict, &dnnrt_model_locals_dict);

////////////////////////////////////////////////////////////////////////////
// モジュール関数・定数
////////////////////////////////////////////////////////////////////////////

/**
 * @brief NNablaのバージョン文字列を返す (dnnrt.nnabla_version)
 */
static mp_obj_t dnnrt_nnabla_version(void) {
  const char *s = rt_nnabla_version();
  return mp_obj_new_str(s, strlen(s));
}
static MP_DEFINE_CONST_FUN_OBJ_0(dnnrt_nnabla_version_obj, dnnrt_nnabla_version);

/**
 * @brief C-runtime (nnabla-c-runtime) のバージョン文字列を返す (dnnrt.runtime_version)
 */
static mp_obj_t dnnrt_runtime_version(void) {
  const char *s = rt_c_runtime_version();
  return mp_obj_new_str(s, strlen(s));
}
static MP_DEFINE_CONST_FUN_OBJ_0(dnnrt_runtime_version_obj, dnnrt_runtime_version);

/**
 * @brief NNBフォーマットのバージョン番号を返す (dnnrt.nnb_version)
 */
static mp_obj_t dnnrt_nnb_version(void) {
  return mp_obj_new_int(rt_nnb_version());
}
static MP_DEFINE_CONST_FUN_OBJ_0(dnnrt_nnb_version_obj, dnnrt_nnb_version);

/// @brief dnnrt モジュールのグローバル定義 (関数・クラス・定数)
static const mp_rom_map_elem_t dnnrt_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_dnnrt)},
    {MP_ROM_QSTR(MP_QSTR_Model), MP_ROM_PTR(&dnnrt_model_type)},
    {MP_ROM_QSTR(MP_QSTR_nnabla_version), MP_ROM_PTR(&dnnrt_nnabla_version_obj)},
    {MP_ROM_QSTR(MP_QSTR_runtime_version), MP_ROM_PTR(&dnnrt_runtime_version_obj)},
    {MP_ROM_QSTR(MP_QSTR_nnb_version), MP_ROM_PTR(&dnnrt_nnb_version_obj)},
    // nn_data_type_t (network.h) と対応するデータ型定数
    {MP_ROM_QSTR(MP_QSTR_DTYPE_FLOAT), MP_ROM_INT(NN_DATA_TYPE_FLOAT)},
    {MP_ROM_QSTR(MP_QSTR_DTYPE_INT16), MP_ROM_INT(NN_DATA_TYPE_INT16)},
    {MP_ROM_QSTR(MP_QSTR_DTYPE_INT8), MP_ROM_INT(NN_DATA_TYPE_INT8)},
    {MP_ROM_QSTR(MP_QSTR_DTYPE_SIGN), MP_ROM_INT(NN_DATA_TYPE_SIGN)},
};
static MP_DEFINE_CONST_DICT(dnnrt_module_globals, dnnrt_module_globals_table);

const mp_obj_module_t dnnrt_user_cmodule = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&dnnrt_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_dnnrt, dnnrt_user_cmodule);
