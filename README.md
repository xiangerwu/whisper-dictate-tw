# whisper-dictate-tw

本地、離線的**繁體中文語音聽寫**工具（Windows）。按熱鍵說話，文字直接打在你游標所在的輸入框——編輯器、瀏覽器、聊天、終端機都行。全程在本機跑，不連雲端。

```
[麥克風 16kHz] → [faster-whisper ASR] → [OpenCC 繁化] → [打到游標位置]
```

專為「用講的代替打字」而做：本地 Whisper 免費轉錄，只把結果文字送出去，省掉雲端語音模式的音訊 token。

## 功能

- **游標聽寫**：全域熱鍵切換錄音，轉錄後以 Unicode 直接打在當前輸入框。
- **決定性繁化**：Whisper 對中文可能吐簡體或簡繁混，用 OpenCC `s2twp` 釘死成繁體台灣用語。
- **筆記歷史**：每次聽寫/匯入結果自動存進本機 SQLite，可搜尋、複製、刪除。
- **音檔匯入**：選 mp3/m4a/wav… 轉成文字（逐段即時顯示），存進筆記。
- **系統匣常駐**：關閉視窗縮回托盤，背景待命；圖示顏色反映狀態。
- **按鍵擷取設定熱鍵**：直接按下組合鍵設定，不用手打字串。

預設模型 `large-v3-turbo`（多語、接近 large-v3 準度但快數倍）。

## 快速開始（從原始碼）

需要 Windows 10/11 + Python 3.13（相依皆有 cp313 wheel）。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt

pythonw gui.py     # 背景執行（無主控台視窗）
# 或 python gui.py 前景執行，可看到訊息
```

首次啟動會下載 `large-v3-turbo` 模型（約 1.6GB）到 Hugging Face 快取，之後完全離線。托盤圖示載入中為灰色，就緒轉綠。

## 使用

- **Ctrl+Alt+D**：開始/停止錄音 → 文字打進游標位置（也可左鍵點托盤圖示）。
- **Ctrl+Alt+Q**：離開。
- 分頁：**聽寫**（狀態、最近結果）／**筆記歷史**（搜尋、複製、刪除）／**音檔匯入**／**設定**。
- 關閉主視窗＝縮回系統匣，不會結束程式；從托盤選單可再開或離開。
- 開機自動啟動：把 `pythonw gui.py`（或安裝後的 exe）捷徑丟進 `shell:startup`。

## 設定（設定分頁）

| 項目 | 預設 | 說明 |
|---|---|---|
| 熱鍵 | `<ctrl>+<alt>+d` | 點欄位後直接按下組合鍵設定 |
| ASR 模型 | `large-v3-turbo` | `large-v3` / `medium` / `small` |
| 裝置 | `cpu` | `cuda`（失敗自動退回 cpu） |
| 語言 | `zh` | `en` / `auto` |
| 繁化 | 開 | OpenCC `s2twp` 強制繁體台灣用語 |

設定存於 `%APPDATA%\voice2text-dictate\settings.json`，筆記存於同目錄 `notes.db`。

## 打包成 exe

```powershell
pip install -r requirements-build.txt
pyinstaller gui.spec
# 產出 dist\whisper-dictate-tw\（含 whisper-dictate-tw.exe，模型不打包）
```

要做安裝檔：安裝 [Inno Setup](https://jrsoftware.org/isdl.php) 後 `iscc installer.iss`，產出 `whisper-dictate-tw-setup.exe`（可勾開機自動啟動）。

## 疑難排解

- **啟動後看不到東西**：托盤圖示可能收在時鐘左邊的「隱藏圖示」`^` 裡（灰色圓點＝正在載入模型），拖出來固定。錯誤紀錄在 `%APPDATA%\voice2text-dictate\gui.log`。
- **打字打不進某個程式**：以系統管理員身分執行的視窗，非管理員的本程式無法送入（Windows UIPI）；要對它聽寫，請以管理員身分執行本程式。
- **麥克風找不到**：`python -c "import sounddevice; print(sounddevice.query_devices())"` 檢查裝置。
- **首次啟動很久沒反應**：正在下載 `large-v3-turbo`（~1.6GB），耐心等托盤轉綠；`gui.log` 有進度。

## 致謝

本專案的設定選擇受 [WhisperPress](https://github.com/b84330808/whisperpress) 啟發——採用了它的 **large-v3-turbo 模型選擇**、**OpenCC 決定性繁化**，以及**按鍵→游標的全域聽寫**概念。借鑑的是設計取向，非其程式碼（WhisperPress 用 whisper.cpp + Electron；本專案用 faster-whisper + PySide6）。兩者皆採 MIT 授權。

## 授權

[MIT](LICENSE)
