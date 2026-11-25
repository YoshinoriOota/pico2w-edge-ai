# code/dnnrt_port/resource/ の model.nnb / test.bmp を使った推論サンプル。
#
# ベアメタル版にはファイルシステムがないため、bin2c.cmake で
# model.nnb / test.bmp をビルド時にCの配列 (model_nnb.h / test_bmp.h) へ
# 変換し、infer_example.c に埋め込む。

set(DNNRT_EXAMPLE_RESOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../resource)
set(DNNRT_BIN2C ${CMAKE_CURRENT_SOURCE_DIR}/bin2c.cmake)

set(MODEL_NNB_H ${CMAKE_CURRENT_BINARY_DIR}/model_nnb.h)
add_custom_command(
    OUTPUT ${MODEL_NNB_H}
    COMMAND ${CMAKE_COMMAND}
            -DINPUT_FILE=${DNNRT_EXAMPLE_RESOURCE_DIR}/model.nnb
            -DOUTPUT_FILE=${MODEL_NNB_H}
            -DARRAY_NAME=model_nnb
            -P ${DNNRT_BIN2C}
    DEPENDS ${DNNRT_EXAMPLE_RESOURCE_DIR}/model.nnb ${DNNRT_BIN2C}
    COMMENT "Generating model_nnb.h from resource/model.nnb"
)

set(TEST_BMP_H ${CMAKE_CURRENT_BINARY_DIR}/test_bmp.h)
add_custom_command(
    OUTPUT ${TEST_BMP_H}
    COMMAND ${CMAKE_COMMAND}
            -DINPUT_FILE=${DNNRT_EXAMPLE_RESOURCE_DIR}/test.bmp
            -DOUTPUT_FILE=${TEST_BMP_H}
            -DARRAY_NAME=test_bmp
            -P ${DNNRT_BIN2C}
    DEPENDS ${DNNRT_EXAMPLE_RESOURCE_DIR}/test.bmp ${DNNRT_BIN2C}
    COMMENT "Generating test_bmp.h from resource/test.bmp"
)

add_executable(dnnrt_infer_example
    infer_example.c
    ${MODEL_NNB_H}
    ${TEST_BMP_H}
)

target_include_directories(dnnrt_infer_example PRIVATE ${CMAKE_CURRENT_BINARY_DIR})

target_link_libraries(dnnrt_infer_example PRIVATE dnnrt_runtime)

# printfの出力先をUSB/UARTシリアルへ
pico_enable_stdio_usb(dnnrt_infer_example 1)
pico_enable_stdio_uart(dnnrt_infer_example 1)

pico_add_extra_outputs(dnnrt_infer_example)
