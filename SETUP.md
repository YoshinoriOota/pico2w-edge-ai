# 開発環境構築手順（PC移行用）

開発用PCを移行する際に、現在の開発環境を再現するための手順を記録する。

## 進め方（Claude Code向け）

新PCで「SETUP.mdを読んで環境移行を手伝って」と指示された場合は、以下の手順で進める。

1. 1章から順に処理する。各節には **担当** / **状態確認** / **完了条件** を記載している。
2. まず **状態確認** のコマンドを実行し、既に完了しているか確認する
   （バージョン違いなどで完全一致しない場合は、実態に合わせて以降のパス記載を
   読み替える）。
3. **担当が👤** の節は、具体的に何をすればよいかをユーザーに指示し、
   完了報告を待ってから次に進む（GUI操作・管理者権限・再起動・物理操作を含むため、
   Claude Codeは代行しない）。
4. **担当が🤖** の節は、実行するコマンドをユーザーに提示し、承認を得てから実行する。
5. 各節の **完了条件** を満たしたら次の節へ進む。
6. 全章完了後、4章のチェックリストを通しで実行し、最終確認する。

このSETUP.md自体が新PCでの引き継ぎ情報の本体である
（会話履歴・メモリは引き継がれない。付録A参照）。

---

## 0. 全体像

本リポジトリのビルド・実機検証には、目的の異なる環境が3つ必要。

| 環境 | 用途 | 対象 |
|---|---|---|
| ① Windows ネイティブ（Pico SDK 2.x） | ベアメタル（Pico C SDK）アプリのビルド | `code/dnnrt_port`、将来的に `code/ov7670_pio`, `code/wifi_udp`, `code/integrated` |
| ② WSL Ubuntu | MicroPython usermod (`dnnrt`) のビルド | `code/dnnrt_upy` |
| ③ Windows上のPython | 実機（Pico2 W）への書き込み・動作確認 (`mpremote`) | 全般 |

リポジトリ本体（`analyze/`, `code/`, `book/`, `CLAUDE.md`, `SETUP.md`）はフォルダ単位で
新PCにコピーする想定（2026-06-14時点でgit remote未設定・コミット未実施）。
`analyze/dnnrt_sdk/` はSony SpresenseSDKを解析用に取り込んだベンダツリーで
約488MB あるため、コピー時間に注意。

---

## 1. Windows ネイティブ環境（Pico SDK 2.x）

### 1.1 VS Code + 拡張機能

- **担当**: 👤（VS Code本体のインストール）/ 🤖（拡張機能のインストールは
  `code --install-extension` で代行可、承認後）
- **状態確認**:
  ```powershell
  code --version
  code --list-extensions
  ```
- **実施内容**:
  1. VS Code をインストール（未インストールの場合）
  2. 拡張機能をインストール
     - `raspberry-pi.raspberry-pi-pico` （Pico SDK本体・必須）
     - `ms-vscode.cmake-tools`
     - `marus25.cortex-debug`（デバッグ用、任意）
     - `paulober.pico-w-go`（MicroPython/Pico-W用、`dnnrt_upy`開発時に利用、任意）
- **完了条件**: `code --list-extensions` に上記4つが表示される

### 1.2 Pico SDK / ツールチェインのセットアップ

- **担当**: 👤（VS Code拡張機能のGUI操作が必要なため）
- **状態確認**:
  ```powershell
  Get-ChildItem "$env:USERPROFILE\.pico-sdk"
  ```
- **実施内容**: VS Codeでコマンドパレット（`Ctrl+Shift+P`）から
  「Raspberry Pi Pico: Configure SDK」を実行し、SDKバージョンを選択する
  （初回ビルド時に自動で促される場合もある）。
- **完了条件**: `%USERPROFILE%\.pico-sdk\` 以下に `sdk`, `toolchain`, `cmake`,
  `ninja`, `picotool`, `openocd` が展開される。

  確認時点（旧PC）でのバージョン。新PCでは拡張機能の更新により異なる
  バージョンが入る可能性があるため、**新PCでの実際のフォルダ名を1.3節の
  コマンドに反映すること**。

  | コンポーネント | バージョン | パス |
  |---|---|---|
  | Pico SDK | 2.2.0 | `%USERPROFILE%\.pico-sdk\sdk\2.2.0` |
  | arm-none-eabi-gcc | 14.2.1 (14_2_Rel1) | `%USERPROFILE%\.pico-sdk\toolchain\14_2_Rel1\bin` |
  | CMake | 3.31.5 | `%USERPROFILE%\.pico-sdk\cmake\v3.31.5\bin` |
  | Ninja | 1.12.1 | `%USERPROFILE%\.pico-sdk\ninja\v1.12.1` |
  | picotool | 2.2.0-a4 | `%USERPROFILE%\.pico-sdk\picotool\2.2.0-a4\picotool` |
  | OpenOCD | 0.12.0+dev | `%USERPROFILE%\.pico-sdk\openocd` |

### 1.3 ビルド確認（dnnrt_port）

- **担当**: 🤖（承認後に実行）
- **状態確認**: 下記コマンドを実行し、エラーなく完了するか確認
- **実施内容**（PowerShell。パスは1.2節で確認した実際のバージョンに置き換える）:
  ```powershell
  $env:PICO_SDK_PATH = "$env:USERPROFILE\.pico-sdk\sdk\2.2.0"
  $env:PATH = "$env:USERPROFILE\.pico-sdk\toolchain\14_2_Rel1\bin;" +
              "$env:USERPROFILE\.pico-sdk\cmake\v3.31.5\bin;" +
              "$env:USERPROFILE\.pico-sdk\ninja\v1.12.1;" + $env:PATH

  cmake -G Ninja -S code\dnnrt_port -B code\dnnrt_port\build `
        -Dpicotool_DIR="$env:USERPROFILE\.pico-sdk\picotool\2.2.0-a4\picotool"

  cmake --build code\dnnrt_port\build --target dnnrt_infer_example
  ```
  `-Dpicotool_DIR` を指定しないと、picotoolをソースからビルドしようとして失敗する。
- **完了条件**: `code\dnnrt_port\build\example\dnnrt_infer_example.uf2` が生成される。

  実機書き込み・出力確認は3章を参照。詳細は `code/dnnrt_port/resource/README.md` にも記載。

---

## 2. WSL Ubuntu環境（dnnrt_upy / MicroPython usermod）

### 2.1 WSL + Ubuntuのインストール

- **担当**: 👤（管理者権限・再起動を伴う可能性があるため）
- **状態確認**:
  ```powershell
  wsl -l -v
  ```
- **実施内容**: `Ubuntu` (Version 2) が無ければインストールする。
  ```powershell
  wsl --install -d Ubuntu --no-launch
  ```
  初回起動時の対話的なUNIXユーザー作成を省略するため、rootで起動する
  （UNIXユーザー未作成時のデフォルトユーザーがroot）。
  ```powershell
  wsl -d Ubuntu -u root
  ```
- **完了条件**: `wsl -l -v` で `Ubuntu` が `Running`/`Stopped` かつ
  `VERSION 2` と表示される。

### 2.2 必要パッケージ

- **担当**: 🤖（承認後に実行）
- **状態確認**:
  ```powershell
  wsl -d Ubuntu -u root bash -c "dpkg -l | grep -E 'build-essential|cmake|ninja-build|gcc-arm-none-eabi'"
  ```
- **実施内容**:
  ```sh
  apt update
  apt install -y build-essential cmake ninja-build \
      gcc-arm-none-eabi libnewlib-arm-none-eabi \
      git python3 python3-pip python3-venv libffi-dev pkg-config
  ```
- **完了条件**: 上記パッケージがすべてインストール済みと表示される。

### 2.3 MicroPythonの取得とビルド

- **担当**: 🤖（承認後に実行。ビルドは数分かかるためバックグラウンド実行推奨）
- **状態確認**:
  ```powershell
  wsl -d Ubuntu -u root bash -c "test -d ~/micropython/ports/rp2/build-RPI_PICO2_W && echo exists"
  ```
- **実施内容**（`<path-to-repo>` は新PCでの本リポジトリの配置場所
  `/mnt/<drive>/...` に置き換える）:
  ```sh
  cd ~
  git clone --depth 1 https://github.com/micropython/micropython.git
  cd micropython
  make -C mpy-cross

  cd ports/rp2
  make BOARD=RPI_PICO2_W \
       USER_C_MODULES=/mnt/<drive>/<path-to-repo>/code/dnnrt_upy/micropython.cmake \
       submodules

  make BOARD=RPI_PICO2_W \
       USER_C_MODULES=/mnt/<drive>/<path-to-repo>/code/dnnrt_upy/micropython.cmake \
       -j4
  ```
- **完了条件**: `build-RPI_PICO2_W/firmware.uf2`（約1.86MB, Flash使用率59%,
  静的RAM使用率約10%）が生成される。

  確認時点のバージョン: micropython/master のshallow clone
  （2026-06-11時点のコミット `6552836c2c6a9833992f9d9e7229b5235386fa20`）。
  新しいコミットでビルドする場合、2.4節の修正が依然有効か確認すること
  （ビルドエラーが出た場合は2.4節を疑う）。

### 2.4 適用済みの修正（参考情報・再作業不要）

- **担当**: なし（確認のみ。本リポジトリのファイルに反映済み）

`code/dnnrt_upy/` は、MicroPythonの `-Werror` ビルドに対応するため
以下2点を修正済み:

1. `code/dnnrt_upy/src/moddnnrt.c`: `dnnrt_model_type` の前方宣言から
   `static` を削除（`MP_DEFINE_CONST_OBJ_TYPE` による非static定義との
   リンク競合を回避。`machine_timer_type` 等と同じパターン）。
2. `code/dnnrt_upy/micropython.cmake`: ベンダSDK
   (`analyze/dnnrt_sdk/externals/nnablart/nnabla-c-runtime/src/runtime/runtime.c`)
   の `printf("%d", uint32_t)` 形式警告を、当該ソースのみ
   `-Wno-error=format` で抑制。

2.3節でビルドエラーが出た場合、まずこの2点が新しいMicroPythonコミットでも
有効かを確認する。

---

## 3. 実機（Pico2 W）への書き込みと動作確認

### 3.1 BOOTSELモードでの書き込み

- **担当**: 👤（USB接続・BOOTSELボタン操作は物理操作） / 🤖（コピーコマンド実行）
- **実施内容**:
  1. （👤）Pico2 W の BOOTSELボタンを押しながらUSB接続
     → リムーバブルディスク `RP2350` として認識される。
  2. （🤖、ドライブレターをユーザーに確認した上で）`.uf2` をコピーする。

     - dnnrt_port（ベアメタル）:
       `code\dnnrt_port\build\example\dnnrt_infer_example.uf2`
     - dnnrt_upy（MicroPython、WSL側でビルドした場合）:
       `\\wsl$\Ubuntu\root\micropython\ports\rp2\build-RPI_PICO2_W\firmware.uf2`
       （PowerShellからUNCパスで直接アクセス可能）
     - dnnrt_upy（ビルド済みを使う場合）:
       `code\dnnrt_upy\firmware\firmware.uf2`

     ```powershell
     Copy-Item <uf2ファイル> F:\ -Force
     ```

     BOOTSELドライブは再接続時に一時的に消えたり再表示されたりすることがある。
- **完了条件**: コピー後、ボードが自動的に再起動してプログラムが実行される。

### 3.2 mpremote（動作確認用）

- **担当**: 🤖（承認後にインストール・実行） / 👤（COMポート番号の確認）
- **状態確認**:
  ```powershell
  python -m mpremote --help
  ```
- **実施内容**:
  ```powershell
  pip install mpremote
  ```
  書き込み後、ボードはUSBシリアル（VID_2E8A PID_0005, "USBシリアルデバイス"）
  として列挙される（👤がデバイスマネージャー等でCOM番号を確認）。
  ```powershell
  python -m mpremote connect COMxx exec "import dnnrt; print(dnnrt.nnabla_version())"
  ```
- **完了条件**: `import dnnrt` がエラーなく実行され、バージョン文字列が返る。

### 3.3 リモートBOOTSELトリック（MicroPythonファーム書き込み済みの場合）

- **担当**: 🤖（承認後に実行）

物理的なBOOTSELボタン操作なしで再書き込みするには:

```powershell
python -m mpremote connect COMxx exec "import machine; machine.bootloader()"
```

実行後に `SerialException` が出るのは正常（COMポートが一時的に消えるため）。
再起動後、`RP2350` ドライブとして再列挙される。

### 3.4 ベアメタルアプリのUSB CDCシリアル出力キャプチャ（PowerShell）

- **担当**: 🤖（承認後に実行） / 👤（COMポート番号の確認）

`pico_enable_stdio_usb` を使うアプリは、`tud_cdc_connected()` が
**DTR信号**を見て出力先の有無を判定する。.NETの `SerialPort.Open()` は
DTRをデフォルトでアサートしないため、開いた直後に明示的に設定する必要がある。

```powershell
$port = New-Object System.IO.Ports.SerialPort COMxx,115200,None,8,One
$port.Open()
$port.DtrEnable = $true
$port.RtsEnable = $true
# ファームウェアの stdio_init_all() 後、約3秒の遅延中に読み取りを開始する
```

すでに実行中のベアメタルアプリをBOOTSELモードへ再投入する場合:

```powershell
picotool reboot -f -u
```

（`picotool reboot -a -f` は専用リセットインターフェースを持たないアプリには
効果がない）

---

## 4. 動作確認チェックリスト

新PCで以下が成功すれば環境構築完了:

- [ ] `code/dnnrt_port`: `dnnrt_infer_example.uf2` がビルドできる（1.3節）
- [ ] `code/dnnrt_upy`: `firmware.uf2` がビルドできる（2.3節）
      ※ `code/dnnrt_upy/firmware/firmware.uf2` にビルド済みファームウェアが
      同梱されているため、ソースを変更しない限り再ビルド不要
- [ ] Pico2 Wに書き込み、`import dnnrt` が成功する（3.2節）
- [ ] `dnnrt_infer_example` 実行で
      `predicted class: 3 (score=0.998012)` がシリアル出力される（3.4節）

---

## 付録A: 会話履歴・メモリの引き継ぎについて

Claude Codeの会話履歴・自動メモリ（本プロジェクトでは
`C:\Users\<user>\.claude\projects\<このプロジェクト用のフォルダ>\`）は、
**新PCに自動的には引き継がれない**。これらはローカルマシン上のユーザー
フォルダに保存されており、ユーザー名やプロジェクトパスが変わると別の
フォルダとして扱われるため。

引き継ぎたい場合は、上記フォルダを新PCの同じ相対パスへ手動コピーする
必要がある。ただし基本方針として、**再現に必要な情報はすべてこの
SETUP.md（および各サブディレクトリのREADME）に記録し、リポジトリと共に
移動する**ことで、メモリの有無に依存せず環境構築できるようにしている。

---

# 追記: Linux PC 環境（2026-07-08 構築）

上記の Windows/WSL 環境とは別に、Linux PC で PC 側ツールを構築した際の記録。

## PC側 Python ツール（担当🤖）

- システム python3.14 には pip/venv が無いため **uv** で venv を作成する:
  ```sh
  cd <リポジトリルート>
  uv venv .venv
  VIRTUAL_ENV=.venv uv pip install mpremote pyserial pillow
  ```
- **状態確認**: `.venv/bin/mpremote version` → mpremote 1.28.0 以降
- .venv/ は .gitignore 済み（コミットしない）

## シリアルポート権限（担当👤）

- `/dev/ttyACM0` は dialout グループ所有。`sudo usermod -aG dialout $USER` 後、
  再ログインで恒久化
- 再ログイン前のセッションでは `sg dialout -c "<コマンド>"` で回避可能
- **完了条件**: `.venv/bin/mpremote exec "print('ok')"` が sudo なしで通ること

## 実機上のファイル（参考）

- Pico 2 W には firmware.uf2（dnnrt 組み込み）を書き込み済み
- フラッシュ上: ov7670.py / v3_states.py / model.nnb / dnnrt_loader.py /
  wifi_config.py（Wi-Fi 認証情報。**リポジトリには含めない**）
