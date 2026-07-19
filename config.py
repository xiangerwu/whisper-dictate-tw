"""ASR 集中設定（faster-whisper）。每個值都可用同名環境變數覆寫。

GUI 的使用者設定另存於 %APPDATA%\\voice2text-dictate\\settings.json，並以明確參數
傳入 SpeechToText；這裡是不帶參數時的 fallback 預設。
"""
from __future__ import annotations

import os


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


ASR_MODEL = _env("ASR_MODEL", "large-v3-turbo")     # large-v3-turbo / large-v3 / medium / small
ASR_DEVICE = _env("ASR_DEVICE", "cpu")              # cpu / cuda
ASR_COMPUTE_TYPE = _env("ASR_COMPUTE_TYPE", "int8")  # cpu 建議 int8；cuda 建議 float16
ASR_LANGUAGE = _env("ASR_LANGUAGE", "zh")           # zh / en / auto（auto 交模型自動偵測）
