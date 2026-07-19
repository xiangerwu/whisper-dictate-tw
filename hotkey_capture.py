"""熱鍵擷取 widget：點一下 → 按下組合鍵 → 產生 pynput 格式字串（例 <ctrl>+<alt>+d）。

取代手打字串的輸入框。定案的組合會用 pynput 的 HotKey.parse() 驗證合法才接受。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QPushButton
from pynput import keyboard

# Qt 修飾鍵 → pynput token
_MODIFIERS = [
    (Qt.KeyboardModifier.ControlModifier, "<ctrl>"),
    (Qt.KeyboardModifier.AltModifier, "<alt>"),
    (Qt.KeyboardModifier.ShiftModifier, "<shift>"),
    (Qt.KeyboardModifier.MetaModifier, "<cmd>"),
]
_MODIFIER_KEYS = {
    int(Qt.Key.Key_Control),
    int(Qt.Key.Key_Alt),
    int(Qt.Key.Key_AltGr),
    int(Qt.Key.Key_Shift),
    int(Qt.Key.Key_Meta),
    int(Qt.Key.Key_Super_L),
    int(Qt.Key.Key_Super_R),
}
_SPECIAL = {
    int(Qt.Key.Key_Space): "<space>",
    int(Qt.Key.Key_Escape): "<esc>",
    int(Qt.Key.Key_Tab): "<tab>",
    int(Qt.Key.Key_Return): "<enter>",
    int(Qt.Key.Key_Enter): "<enter>",
    int(Qt.Key.Key_Backspace): "<backspace>",
    int(Qt.Key.Key_Insert): "<insert>",
    int(Qt.Key.Key_Delete): "<delete>",
    int(Qt.Key.Key_Home): "<home>",
    int(Qt.Key.Key_End): "<end>",
    int(Qt.Key.Key_PageUp): "<page_up>",
    int(Qt.Key.Key_PageDown): "<page_down>",
}
_A, _Z = int(Qt.Key.Key_A), int(Qt.Key.Key_Z)
_0, _9 = int(Qt.Key.Key_0), int(Qt.Key.Key_9)
_F1, _F24 = int(Qt.Key.Key_F1), int(Qt.Key.Key_F24)


def _main_key(key: int) -> str | None:
    if _A <= key <= _Z:
        return chr(key).lower()
    if _0 <= key <= _9:
        return chr(key)
    if _F1 <= key <= _F24:
        return f"<f{key - _F1 + 1}>"
    return _SPECIAL.get(key)


class HotkeyEdit(QPushButton):
    """顯示目前熱鍵；點擊進入擷取模式，按下組合鍵後定案並發出 changed 訊號。"""

    changed = Signal(str)

    def __init__(self, hotkey: str = "", parent=None) -> None:
        super().__init__(parent)
        self._hotkey = hotkey
        self._capturing = False
        self.setCheckable(True)
        self.clicked.connect(self._toggle_capture)
        self._refresh()

    def hotkey(self) -> str:
        return self._hotkey

    def setHotkey(self, hk: str) -> None:
        self._hotkey = hk
        self._refresh()

    def _refresh(self) -> None:
        self.setText(
            "請按下組合鍵…（Esc 取消）"
            if self._capturing
            else (self._hotkey or "（點此設定熱鍵）")
        )

    def _toggle_capture(self) -> None:
        self._capturing = not self._capturing
        if self._capturing:
            self.setChecked(True)
            self.grabKeyboard()
        else:
            self.releaseKeyboard()
            self.setChecked(False)
        self._refresh()

    def _stop(self) -> None:
        self._capturing = False
        self.releaseKeyboard()
        self.setChecked(False)
        self._refresh()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        if not self._capturing:
            super().keyPressEvent(event)
            return
        key = int(event.key())
        if key == int(Qt.Key.Key_Escape):
            self._stop()
            return
        if key in _MODIFIER_KEYS:
            return  # 只按了修飾鍵，繼續等主鍵
        main = _main_key(key)
        if main is None:
            return  # 不支援的鍵，忽略
        mods = event.modifiers()
        tokens = [token for flag, token in _MODIFIERS if mods & flag]
        is_function = main.startswith("<f") and main[2:-1].isdigit()
        if not tokens and not is_function:
            self.setText("請含 Ctrl/Alt/Shift，或改用功能鍵")
            return
        combo = "+".join(tokens + [main])
        try:
            keyboard.HotKey.parse(combo)
        except Exception:  # noqa: BLE001
            self.setText("無效組合，請重按")
            return
        self._hotkey = combo
        self._stop()
        self.changed.emit(combo)
