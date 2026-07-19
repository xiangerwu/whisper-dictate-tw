"""聽寫核心：錄音 → faster-whisper 轉錄 → OpenCC 繁化（可選）→ 在游標位置打字。

不綁定任何 UI 或熱鍵框架：狀態與結果透過 callback 回報，CLI（dictate.py）與
GUI（gui.py）各自包裝。專注繁體中文——預設 large-v3-turbo 模型，輸出用 OpenCC
的 s2twp 決定性轉成繁體台灣用語（Whisper 對 zh 可能吐簡體或簡繁混，這步把它釘死）。

turbo 是新世代、裁剪解碼層，接近 large-v3 準度但快數倍。CTranslate2 沒有 whisper.cpp
的 q5_0 格式，等價的輕量量化是 CPU→int8、CUDA→float16。
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
from pynput import keyboard as _kb

from asr import SpeechToText

try:
    import opencc
except ImportError:  # 未安裝 opencc 時，繁化功能停用
    opencc = None

SAMPLE_RATE = 16000  # Whisper 需要 16kHz
CHANNELS = 1

Callback = Callable[[str], None]


def compute_type_for(device: str) -> str:
    """CT2 的輕量量化：CPU 用 int8、CUDA 用 float16（對應 whisper.cpp 的 q5_0 定位）。"""
    return "int8" if device == "cpu" else "float16"


class DictationEngine:
    """狀態機 idle → recording → processing → idle。toggle() 只切換 idle↔recording。"""

    def __init__(
        self,
        *,
        model: str = "large-v3-turbo",
        device: str = "cpu",
        language: str = "zh",
        traditional: bool = True,
        compute_type: Optional[str] = None,
        on_state: Optional[Callback] = None,
        on_result: Optional[Callback] = None,
        on_error: Optional[Callback] = None,
    ) -> None:
        self.model = model
        self.device = device
        self.language = language
        self.traditional = traditional
        self.compute_type = compute_type or compute_type_for(device)
        self._on_state = on_state or (lambda s: None)
        self._on_result = on_result or (lambda t: None)
        self._on_error = on_error or (lambda e: None)

        self._stt: Optional[SpeechToText] = None
        self._cc = None
        self._keyboard = _kb.Controller()
        self._frames: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None
        self._state = "idle"
        self._lock = threading.Lock()  # 狀態機（toggle/錄音）
        self._infer_lock = threading.Lock()  # 序列化模型推論：麥克風與音檔匯入不同時呼叫（CTranslate2 非執行緒安全）

    @property
    def state(self) -> str:
        return self._state

    @property
    def ready(self) -> bool:
        return self._stt is not None

    def _set_state(self, s: str) -> None:
        self._state = s
        self._on_state(s)

    def load_model(self) -> None:
        """載入 ASR 模型（耗時，建議在背景執行緒呼叫）。首次會下載模型。"""
        self._stt = SpeechToText(
            model=self.model,
            device=self.device,
            compute_type=self.compute_type,
            language=self.language,
        )
        # SpeechToText 在 cuda 失敗時會自動退回 cpu int8，同步回來
        self.device = self._stt.device
        self.compute_type = self._stt.compute_type
        self._cc = (
            opencc.OpenCC("s2twp") if self.traditional and opencc is not None else None
        )

    def _to_traditional(self, text: str) -> str:
        """輸出繁化（若啟用）。麥克風與音檔匯入共用。"""
        return self._cc.convert(text) if (text and self._cc is not None) else text

    def transcribe_file(self, path, on_segment=None) -> str:
        """轉錄音檔（mp3/m4a/wav…），逐段回報（on_segment 收已繁化的片段），回傳整段。

        與麥克風不同，這裡不注入游標——匯入結果交給 UI 顯示/存筆記。
        """
        if not self.ready:
            raise RuntimeError("模型尚未載入")
        parts: list[str] = []
        with self._infer_lock:  # 不與麥克風轉錄同時用模型
            for segment in self._stt.transcribe_segments(str(path)):  # type: ignore[union-attr]
                segment = self._to_traditional(segment)
                parts.append(segment)
                if on_segment is not None:
                    on_segment(segment)
        return "".join(parts).strip()

    def toggle(self) -> None:
        """熱鍵/點擊回呼：idle 開始錄音，recording 停止並轉錄，processing 忽略。"""
        with self._lock:
            if not self.ready:
                return
            if self._state == "idle":
                self._start()
            elif self._state == "recording":
                self._stop_and_process()

    def _callback(self, indata, frames, time_info, status):  # noqa: ANN001
        self._frames.append(indata.copy())

    def _start(self) -> None:
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        self._set_state("recording")

    def _stop_and_process(self) -> None:
        self._set_state("processing")
        assert self._stream is not None
        self._stream.stop()
        self._stream.close()
        self._stream = None
        frames, self._frames = self._frames, []
        threading.Thread(target=self._process, args=(frames,), daemon=True).start()

    def _process(self, frames: list[np.ndarray]) -> None:
        try:
            text = ""
            if frames:
                audio = np.concatenate(frames, axis=0).reshape(-1).astype(np.float32)
                with self._infer_lock:  # 不與音檔匯入同時用模型
                    text = self._stt.transcribe(audio)  # type: ignore[union-attr]
            text = self._to_traditional(text)  # 決定性繁化（台灣用語）
            if text:
                self._keyboard.type(text)  # 以 Unicode 直接打在游標位置
            self._on_result(text)
        except Exception as exc:  # noqa: BLE001 - 回報給 UI，不讓執行緒默默死掉
            self._on_error(str(exc))
        finally:
            with self._lock:
                self._set_state("idle")
