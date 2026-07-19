"""語音轉文字：以 faster-whisper（CTranslate2 後端）把音訊轉成含標點的文字。

預設跑 CPU（int8），品質與 GPU fp16 幾乎無差。transcribe() 接受 16kHz mono 的
float32 ndarray 或音檔路徑（mp3/m4a/wav… 由 faster-whisper 內建的 av 解碼）。
transcribe_segments() 逐段 yield，供音檔匯入做即時輸出。
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Iterator

import numpy as np


def _app_base() -> Path:
    """app 所在目錄：打包版＝exe 資料夾；源碼版＝專案資料夾。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


# 模型下載到 app 同目錄的 models\ 下，方便隨 app 一起管理/搬移。
# 必須在 import faster-whisper（會拉 huggingface_hub）之前設定；使用者自訂 HF_HOME 則尊重之。
os.environ.setdefault("HF_HOME", str(_app_base() / "models"))

from faster_whisper import WhisperModel  # noqa: E402 - 需在設定 HF_HOME 之後才 import

import config  # noqa: E402


def _normalize_language(value) -> str | None:
    """把設定字串轉成 faster-whisper 認得的語言碼；auto/空字串 → None（自動偵測）。"""
    if value is None:
        return None
    v = str(value).strip().lower()
    return None if v in ("", "auto", "none") else v


class SpeechToText:
    def __init__(self, model=None, device=None, compute_type=None, language=None):
        self.model_name = model or config.ASR_MODEL
        self.device = device or config.ASR_DEVICE
        self.compute_type = compute_type or config.ASR_COMPUTE_TYPE
        self.language = _normalize_language(
            language if language is not None else config.ASR_LANGUAGE
        )
        self.model = self._load()

    def _load(self) -> WhisperModel:
        """載入模型；若指定 cuda 但失敗（無 GPU / 缺 CUDA DLL / 顯存不足），自動退回 CPU int8。

        打包版預設 cpu、自帶可跑；cuda 需目標機器裝有 CUDA 執行庫，缺了就走這條退回，
        原因會寫進 log（缺哪個 DLL 也看得到），不讓程式崩潰。
        """
        try:
            return WhisperModel(
                self.model_name, device=self.device, compute_type=self.compute_type
            )
        except Exception as exc:  # noqa: BLE001 - 退回策略需攔截所有載入錯誤
            if self.device != "cpu":
                logging.warning(
                    "%s 載入失敗（%s），改用 CPU int8。", self.device, exc
                )
                self.device, self.compute_type = "cpu", "int8"
                return WhisperModel(self.model_name, device="cpu", compute_type="int8")
            raise

    def transcribe_segments(self, audio) -> Iterator[str]:
        """逐段 yield 文字。接受 np.ndarray(float32/16kHz/mono) 或音檔路徑。"""
        if isinstance(audio, np.ndarray):
            audio = audio.astype(np.float32)

        segments, _info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            vad_filter=True,  # faster-whisper 內建 Silero VAD，過濾靜音段
        )
        for segment in segments:
            yield segment.text

    def transcribe(self, audio) -> str:
        """接受 np.ndarray(float32/16kHz/mono) 或音檔路徑，回傳含標點的整段文字。"""
        return "".join(self.transcribe_segments(audio)).strip()
