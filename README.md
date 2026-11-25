# README.md

## プロジェクト概要
Raspberry Pi Pico2 W + OV7670 によるエッジAIカメラシステム

## ハードウェア
- MCU: RP2350 (Raspberry Pi Pico2 W)
- カメラ: OV7670 (DVP 8bit パラレル、FIFOなし)
- 通信: CYW43439 WiFi (lwIP)

## インターフェース設計
- OV7670 DVP → PIO 2ステートマシン構成で受信
  - SM0: VSYNC/HREF同期
  - SM1: PCLK立ち上がりでD0-D7取得
- DMA: PIO RX FIFOからフレームバッファへ直接転送
- WiFi配信: UDP unicast、RAWフレームデータ

## AIパイプライン（検討中）
- モデル設計: Sony Neural Network Console (NNC)
- 推論ランタイム候補A: Sony DNNRT移植（NNBそのまま使用、世界初）
- 推論ランタイム候補B: TFLite Micro（TFLite変換が必要）
- 移植可能性調査: analyze/dnnrt_sdk/ 以下を参照

## ビルド環境
- SDK: Pico C SDK 2.x
- ビルド: cmake + ninja
- ターゲット: pico2_w (RP2350)

## ディレクトリ構成
analyze/dnnrt_sdk/   # SpresenseSDK（DNNRTソース解析用）
analyze/report/      # 移植可能性レポート
code/ov7670_pio/     # PIOドライバ・SCCBレジスタ設定
code/dnnrt_port/     # DNNRT移植コード（Pico C SDKベアメタル版）
code/dnnrt_upy/      # DNNRT MicroPythonラッパー（usermod、pico-sdkとは分離）
code/collect/        # データ収集ツール（Pico撮影サーバ+PC受信・NNC CSV整形）
code/wifi_udp/       # UDP送信
code/integrated/     # 統合アプリ（カメラ+推論の結合テスト、V3電流測定）
book/chapters/       # 各章Markdown
book/figures/        # 図版（Mermaid・SVG・NNCスクリーンショット）
book/code_snippets/  # 書籍掲載用コード抜粋

## 制約・注意事項
- OV7670はFIFOなし版を想定
- PIO命令は32命令制限に注意
- RP2350のSRAM容量(520KB)を常に意識
- コメントは日本語可
- 関数単位でDoxygen形式
EOF
