# DNNRT (Sony nnabla-c-runtime) を RP2350 (Pico2 W) に統合するための
# Pico C SDK 2.x プロジェクト。
#
# nnabla-c-runtime 本体のソースは analyze/dnnrt_sdk/externals/nnablart/ 以下を
# そのまま参照する(コピーはしない)。詳細は analyze/report/dnnrt_feasibility.md
# を参照。

cmake_minimum_required(VERSION 3.13)

set(PICO_BOARD pico2_w CACHE STRING "Board type")

include(pico_sdk_import.cmake)

project(dnnrt_port C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

# --- nnabla-c-runtime (DNNRT) のソース ---
set(NNABLART_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../analyze/dnnrt_sdk/externals/nnablart/nnabla-c-runtime)

# ランタイム本体 (src/runtime/)
file(GLOB DNNRT_RUNTIME_SOURCES
    ${NNABLART_DIR}/src/runtime/*.c
)

# 各レイヤ実装・ユーティリティ (src/functions/)
file(GLOB_RECURSE DNNRT_FUNCTIONS_SOURCES
    ${NNABLART_DIR}/src/functions/*.c
)

add_library(dnnrt_runtime STATIC
    ${DNNRT_RUNTIME_SOURCES}
    ${DNNRT_FUNCTIONS_SOURCES}
)

# include/ 以下 (nnablart/network.h, runtime.h, functions.h, config.h) と
# src/runtime/ (context.h: コールバック登録に必要) を公開
target_include_directories(dnnrt_runtime PUBLIC
    ${NNABLART_DIR}/include
    ${NNABLART_DIR}/src/runtime
)

target_link_libraries(dnnrt_runtime PUBLIC
    pico_stdlib
    pico_float
)

# --- 推論動作確認用テストプログラム ---
add_executable(dnnrt_test
    src/dnnrt_test.c
)

target_link_libraries(dnnrt_test PRIVATE
    dnnrt_runtime
)

# printfの出力先をUSB/UARTシリアルへ
pico_enable_stdio_usb(dnnrt_test 1)
pico_enable_stdio_uart(dnnrt_test 1)

pico_add_extra_outputs(dnnrt_test)

# --- model.nnb + test.bmp を使った推論サンプル ---
add_subdirectory(example)
