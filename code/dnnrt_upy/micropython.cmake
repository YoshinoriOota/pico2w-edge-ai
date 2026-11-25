# DNNRT (Sony nnabla-c-runtime) を MicroPython の user C module として
# 組み込むための CMake 定義。
#
# nnabla-c-runtime 本体のソースは pico2w-edge-ai リポジトリの
# analyze/dnnrt_sdk/externals/nnablart/nnabla-c-runtime をそのまま参照する
# (コピーはしない)。 code/dnnrt_port/CMakeLists.txt と同じ参照方法。
#
# 使い方:
#   MicroPython のソースを別途取得し、rp2ポートを以下のように
#   USER_C_MODULES でこのファイルを指定してビルドする。
#
#     cd micropython/ports/rp2
#     make BOARD=RPI_PICO2_W \
#          USER_C_MODULES=<このリポジトリ>/code/dnnrt_upy/micropython.cmake \
#          submodules
#     make BOARD=RPI_PICO2_W \
#          USER_C_MODULES=<このリポジトリ>/code/dnnrt_upy/micropython.cmake
#
# 詳細は code/dnnrt_upy/README.md を参照。

add_library(usermod_dnnrt INTERFACE)

set(DNNRT_UPY_DIR ${CMAKE_CURRENT_LIST_DIR})

# このファイルから見て ../../ が pico2w-edge-ai リポジトリのルート
get_filename_component(DNNRT_UPY_REPO_ROOT "${DNNRT_UPY_DIR}/../.." ABSOLUTE)

set(NNABLART_DIR ${DNNRT_UPY_REPO_ROOT}/analyze/dnnrt_sdk/externals/nnablart/nnabla-c-runtime)

# ランタイム本体 (src/runtime/)
file(GLOB DNNRT_RUNTIME_SOURCES
    ${NNABLART_DIR}/src/runtime/*.c
)

# 各レイヤ実装・ユーティリティ (src/functions/)
file(GLOB_RECURSE DNNRT_FUNCTIONS_SOURCES
    ${NNABLART_DIR}/src/functions/*.c
)

target_sources(usermod_dnnrt INTERFACE
    ${DNNRT_UPY_DIR}/src/moddnnrt.c
    ${DNNRT_RUNTIME_SOURCES}
    ${DNNRT_FUNCTIONS_SOURCES}
)

# nnabla-c-runtime本体にMicroPythonビルドの -Werror=format に抵触する
# printf書式 (uint32_t を %d で出力) が含まれるため、ベンダーソースを
# 変更せずにこれらのファイルのみ警告を非致命化する。
set_source_files_properties(
    ${DNNRT_RUNTIME_SOURCES}
    ${DNNRT_FUNCTIONS_SOURCES}
    PROPERTIES COMPILE_OPTIONS "-Wno-error=format"
)

target_include_directories(usermod_dnnrt INTERFACE
    ${DNNRT_UPY_DIR}/src
    ${NNABLART_DIR}/include
    ${NNABLART_DIR}/src/runtime
)

target_link_libraries(usermod INTERFACE usermod_dnnrt)
