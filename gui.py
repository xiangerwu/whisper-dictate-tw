"""本地聽寫 app（PySide6）：分頁主視窗 + 系統匣常駐。

分頁：聽寫 / 筆記歷史 / 音檔匯入 / 設定。背景常駐，按熱鍵或點托盤即可語音轉文字
並直接打到游標位置；每次結果存進本機筆記；也可匯入音檔轉錄。專注繁體中文
（預設 large-v3-turbo + OpenCC s2twp 決定性繁化）。

用法：
    pythonw gui.py     # 背景執行（無主控台）
    python  gui.py     # 前景執行（可看例外訊息）

核心 dictation_engine.DictationEngine；全域熱鍵 pynput；筆記 notes.NotesStore；
熱鍵設定用 hotkey_capture.HotkeyEdit（按鍵擷取）。設定/筆記存於 %APPDATA%。
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QGuiApplication,
    QIcon,
    QPainter,
    QPalette,
    QPixmap,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMainWindow,
)
from pynput import keyboard

from dictation_engine import DictationEngine
from hotkey_capture import HotkeyEdit
from notes import NotesStore

APP_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "voice2text-dictate"
SETTINGS_PATH = APP_DIR / "settings.json"
QUIT_HOTKEY = "<ctrl>+<alt>+q"

DEFAULTS = {
    "model": "large-v3-turbo",
    "device": "cpu",
    "language": "zh",
    "traditional": True,
    "hotkey": "<ctrl>+<alt>+d",
}
MODELS = ["large-v3-turbo", "large-v3", "medium", "small"]
DEVICES = ["cpu", "cuda"]
LANGUAGES = ["zh", "en", "auto"]
AUDIO_FILTER = "音檔 (*.mp3 *.m4a *.wav *.ogg *.flac *.aac *.wma);;所有檔案 (*.*)"

STATE = {  # 狀態 → (色, 文字)
    "loading": ("#8a8f98", "載入模型中…"),
    "idle": ("#3bb273", "待命"),
    "recording": ("#e5484d", "錄音中"),
    "processing": ("#e08a00", "辨識中…"),
    "error": ("#b02a2a", "錯誤"),
}

# 明確指定前景+背景色，強制淺色一致主題（不看 OS 深/淺主題臉色，避免白底白字）
STYLE = """
QWidget { font-family: "Segoe UI","Microsoft JhengHei UI",sans-serif; font-size: 10pt;
  color: #1c2430; }
QMainWindow, QTabWidget, QTabWidget::pane > QWidget { background: #f4f5f7; }
QTabWidget::pane { border: 1px solid #d0d4da; border-radius: 8px; top: -1px; background: #f4f5f7; }
QTabBar::tab { padding: 8px 18px; margin-right: 2px; background: #e7eaee; color: #4a5060;
  border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { background: #3bb273; color: #ffffff; }
QLabel { color: #1c2430; background: transparent; }
QPushButton { padding: 7px 14px; border-radius: 6px; border: 1px solid #c2c8d0;
  background: #ffffff; color: #1c2430; }
QPushButton:hover { border-color: #3bb273; }
QPushButton:pressed { background: #eef0f3; }
QPushButton:disabled { color: #a6abb4; background: #f0f1f3; }
QLineEdit, QComboBox, QTextEdit, QListWidget {
  border: 1px solid #c2c8d0; border-radius: 6px; padding: 5px;
  background: #ffffff; color: #1c2430; selection-background-color: #3bb273;
  selection-color: #ffffff; }
QComboBox QAbstractItemView { background: #ffffff; color: #1c2430;
  selection-background-color: #3bb273; selection-color: #ffffff; }
QListWidget::item { padding: 4px 2px; }
QListWidget::item:selected { background: #3bb273; color: #ffffff; }
"""


def _apply_light_theme(app: QApplication) -> None:
    """Fusion + 明確淺色 palette，保證每個內建元件都是深字淺底、不受 OS 主題影響。"""
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#f4f5f7"))
    pal.setColor(QPalette.WindowText, QColor("#1c2430"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#eef0f3"))
    pal.setColor(QPalette.Text, QColor("#1c2430"))
    pal.setColor(QPalette.Button, QColor("#f0f2f5"))
    pal.setColor(QPalette.ButtonText, QColor("#1c2430"))
    pal.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipText, QColor("#1c2430"))
    pal.setColor(QPalette.PlaceholderText, QColor("#8a8f98"))
    pal.setColor(QPalette.Highlight, QColor("#3bb273"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#a6abb4"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#a6abb4"))
    app.setPalette(pal)


# ---------- 設定持久化 ----------
def load_settings() -> dict:
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(SETTINGS_PATH.read_text("utf-8")))
    except (OSError, ValueError):
        pass
    return data


def save_settings(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def make_icon(color: str) -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(10, 10, 44, 44)
    painter.end()
    return QIcon(pm)


class Bridge(QObject):
    """引擎/工作執行緒的 callback → Qt signal，確保 UI 更新落在主執行緒。"""

    state = Signal(str)
    result = Signal(str)
    error = Signal(str)
    file_segment = Signal(str)
    file_done = Signal(str)
    file_error = Signal(str)


class AppWindow(QMainWindow):
    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self.app = app
        self.settings = load_settings()
        self.notes = NotesStore()
        self.engine: DictationEngine | None = None
        self._listener: keyboard.GlobalHotKeys | None = None

        self.bridge = Bridge()
        self.bridge.state.connect(self._on_state)
        self.bridge.result.connect(self._on_result)
        self.bridge.error.connect(self._on_error)
        self.bridge.file_segment.connect(self._on_file_segment)
        self.bridge.file_done.connect(self._on_file_done)
        self.bridge.file_error.connect(self._on_file_error)

        self.setWindowTitle("聽寫 · whisper-dictate-tw")
        self.resize(600, 520)
        self._build_tray()  # 先建托盤，_set_dot 會用到
        self._build_tabs()
        self._build_engine_and_load()

    # ---------- 分頁 ----------
    def _build_tabs(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._dictation_tab(), "聽寫")
        tabs.addTab(self._notes_tab(), "筆記歷史")
        tabs.addTab(self._import_tab(), "音檔匯入")
        tabs.addTab(self._settings_tab(), "設定")
        tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs = tabs
        self.setCentralWidget(tabs)

    def _dictation_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self.dot = QLabel()
        self.dot.setFixedSize(18, 18)
        self.status_label = QLabel("載入模型中…")
        self.status_label.setStyleSheet("font-size: 13pt; font-weight: 600;")
        row.addWidget(self.dot)
        row.addWidget(self.status_label)
        row.addStretch()
        lay.addLayout(row)

        self.hotkey_label = QLabel()
        lay.addWidget(self.hotkey_label)

        self.toggle_btn = QPushButton("開始 / 停止 錄音")
        self.toggle_btn.clicked.connect(self._toggle)
        lay.addWidget(self.toggle_btn)

        lay.addWidget(QLabel("最近一次結果："))
        self.last_result = QTextEdit()
        self.last_result.setReadOnly(True)
        lay.addWidget(self.last_result, 1)

        tip = QLabel("提示：文字會直接打在游標所在的輸入框；每次結果自動存入「筆記歷史」。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#777;")
        lay.addWidget(tip)
        self._set_dot("loading", "載入模型中…")
        return w

    def _notes_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜尋筆記…")
        self.search_box.textChanged.connect(lambda _t: self._reload_notes())
        lay.addWidget(self.search_box)

        self.notes_list = QListWidget()
        lay.addWidget(self.notes_list, 1)

        btns = QHBoxLayout()
        copy_btn = QPushButton("複製")
        copy_btn.clicked.connect(self._copy_note)
        del_btn = QPushButton("刪除")
        del_btn.clicked.connect(self._delete_note)
        refresh_btn = QPushButton("重新整理")
        refresh_btn.clicked.connect(self._reload_notes)
        btns.addWidget(copy_btn)
        btns.addWidget(del_btn)
        btns.addStretch()
        btns.addWidget(refresh_btn)
        lay.addLayout(btns)
        self._reload_notes()
        return w

    def _import_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        self.import_btn = QPushButton("選擇音檔…")
        self.import_btn.clicked.connect(self._choose_file)
        self.import_status = QLabel("")
        self.import_status.setStyleSheet("color:#777;")
        top.addWidget(self.import_btn)
        top.addWidget(self.import_status, 1)
        lay.addLayout(top)

        self.import_output = QTextEdit()
        self.import_output.setReadOnly(True)
        lay.addWidget(self.import_output, 1)

        self.import_copy_btn = QPushButton("複製全部")
        self.import_copy_btn.clicked.connect(
            lambda: QGuiApplication.clipboard().setText(self.import_output.toPlainText())
        )
        lay.addWidget(self.import_copy_btn)
        return w

    def _settings_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.hotkey_edit = HotkeyEdit(self.settings["hotkey"])
        self.model_combo = QComboBox()
        self.model_combo.addItems(MODELS)
        self.model_combo.setCurrentText(self.settings["model"])
        self.device_combo = QComboBox()
        self.device_combo.addItems(DEVICES)
        self.device_combo.setCurrentText(self.settings["device"])
        self.language_combo = QComboBox()
        self.language_combo.addItems(LANGUAGES)
        self.language_combo.setCurrentText(self.settings["language"])
        self.traditional_check = QCheckBox("輸出強制繁體（OpenCC s2twp，台灣用語）")
        self.traditional_check.setChecked(self.settings["traditional"])

        form.addRow("熱鍵", self.hotkey_edit)
        form.addRow("ASR 模型", self.model_combo)
        form.addRow("裝置", self.device_combo)
        form.addRow("語言", self.language_combo)
        form.addRow("", self.traditional_check)
        save_btn = QPushButton("儲存")
        save_btn.clicked.connect(self._save_settings)
        form.addRow(save_btn)
        note = QLabel("切換模型會重新載入（首次選 large-v3-turbo 會下載約 1.6GB）。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#777;")
        form.addRow(note)
        return w

    # ---------- 系統匣 ----------
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(make_icon(STATE["loading"][0]), self.app)
        self.tray.setToolTip("聽寫 — 載入中")
        self.tray_menu = QMenu()
        act_show = QAction("顯示視窗", self.tray_menu)
        act_show.triggered.connect(self._show_window)
        self.act_tray_toggle = QAction("開始 / 停止錄音", self.tray_menu)
        self.act_tray_toggle.triggered.connect(self._toggle)
        act_quit = QAction("離開", self.tray_menu)
        act_quit.triggered.connect(self._quit)
        self.tray_menu.addAction(act_show)
        self.tray_menu.addAction(self.act_tray_toggle)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(act_quit)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    # ---------- 引擎 / 熱鍵 ----------
    def _build_engine_and_load(self) -> None:
        s = self.settings
        self.engine = DictationEngine(
            model=s["model"],
            device=s["device"],
            language=s["language"],
            traditional=s["traditional"],
            on_state=self.bridge.state.emit,
            on_result=self.bridge.result.emit,
            on_error=self.bridge.error.emit,
        )
        self._set_dot("loading", "載入模型中…")

        def load() -> None:
            try:
                logging.info("載入模型 %s / %s", s["model"], s["device"])
                self.engine.load_model()
                logging.info("模型載入完成")
                self.bridge.state.emit("idle")
            except Exception as exc:  # noqa: BLE001
                logging.exception("模型載入失敗")
                self.bridge.error.emit(f"模型載入失敗：{exc}")

        threading.Thread(target=load, daemon=True).start()

    def _start_hotkey(self) -> None:
        self._stop_hotkey()
        try:
            self._listener = keyboard.GlobalHotKeys(
                {self.settings["hotkey"]: self._toggle, QUIT_HOTKEY: self._quit}
            )
            self._listener.start()
        except Exception as exc:  # noqa: BLE001
            self.bridge.error.emit(f"熱鍵無效：{self.settings['hotkey']}（{exc}）")

    def _stop_hotkey(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _toggle(self) -> None:
        if self.engine and self.engine.ready:
            self.engine.toggle()

    # ---------- 狀態顯示 ----------
    def _set_dot(self, state_key: str, text: str = "") -> None:
        color, label = STATE.get(state_key, STATE["idle"])
        self.dot.setStyleSheet(f"background:{color}; border-radius:9px;")
        self.status_label.setText(text or label)
        self.hotkey_label.setText(
            f"熱鍵：{self.settings['hotkey']}　（離開：{QUIT_HOTKEY}）　"
            f"繁化：{'開' if self.settings['traditional'] else '關'}"
        )
        if hasattr(self, "tray"):
            self.tray.setIcon(make_icon(color))
            self.tray.setToolTip(f"聽寫 — {label}")

    # ---------- slots（主執行緒）----------
    def _on_state(self, state: str) -> None:
        self._set_dot(state)
        if state == "idle" and self._listener is None:
            self._start_hotkey()
            self.tray.showMessage(
                "聽寫就緒",
                f"{self.settings['hotkey']} 開始/停止；視窗可關閉縮回系統匣。",
                QSystemTrayIcon.Information,
                4000,
            )

    def _on_result(self, text: str) -> None:
        self._set_dot("idle")
        if text:
            self.last_result.setPlainText(text)
            self.notes.add(text, "dictation")
            self._reload_notes()
        else:
            self.tray.showMessage("聽寫", "沒有辨識到文字。", QSystemTrayIcon.Warning, 2000)

    def _on_error(self, msg: str) -> None:
        self._set_dot("error")
        self.tray.showMessage("聽寫錯誤", msg, QSystemTrayIcon.Critical, 6000)

    # ---------- 筆記 ----------
    def _reload_notes(self) -> None:
        query = self.search_box.text().strip() if hasattr(self, "search_box") else ""
        self.notes_list.clear()
        for note in self.notes.search(query):
            preview = note.text.replace("\n", " ")
            if len(preview) > 60:
                preview = preview[:60] + "…"
            tag = "🎤" if note.source == "dictation" else "📁"
            item = QListWidgetItem(f"{tag} {note.created_at}  ·  {preview}")
            item.setData(Qt.UserRole, note.id)
            item.setData(Qt.UserRole + 1, note.text)
            self.notes_list.addItem(item)

    def _copy_note(self) -> None:
        item = self.notes_list.currentItem()
        if item:
            QGuiApplication.clipboard().setText(item.data(Qt.UserRole + 1))

    def _delete_note(self) -> None:
        item = self.notes_list.currentItem()
        if item:
            self.notes.delete(int(item.data(Qt.UserRole)))
            self._reload_notes()

    # ---------- 音檔匯入 ----------
    def _choose_file(self) -> None:
        if not (self.engine and self.engine.ready):
            self.import_status.setText("模型尚未載入，請稍候。")
            return
        path, _ = QFileDialog.getOpenFileName(self, "選擇音檔", "", AUDIO_FILTER)
        if not path:
            return
        self.import_btn.setEnabled(False)
        self.import_output.clear()
        self.import_status.setText(f"辨識中：{Path(path).name}")

        def work() -> None:
            try:
                text = self.engine.transcribe_file(
                    path, on_segment=self.bridge.file_segment.emit
                )
                self.bridge.file_done.emit(text)
            except Exception as exc:  # noqa: BLE001
                self.bridge.file_error.emit(str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _on_file_segment(self, segment: str) -> None:
        self.import_output.moveCursor(QTextCursor.MoveOperation.End)
        self.import_output.insertPlainText(segment)

    def _on_file_done(self, text: str) -> None:
        self.import_btn.setEnabled(True)
        if text:
            self.notes.add(text, "file")
            self._reload_notes()
            self.import_status.setText("完成，已存入筆記歷史。")
        else:
            self.import_status.setText("完成，但沒有辨識到文字。")

    def _on_file_error(self, msg: str) -> None:
        self.import_btn.setEnabled(True)
        self.import_status.setText(f"錯誤：{msg}")

    # ---------- 設定 ----------
    def _save_settings(self) -> None:
        new = {
            "hotkey": self.hotkey_edit.hotkey() or DEFAULTS["hotkey"],
            "model": self.model_combo.currentText(),
            "device": self.device_combo.currentText(),
            "language": self.language_combo.currentText(),
            "traditional": self.traditional_check.isChecked(),
        }
        engine_changed = any(
            new[k] != self.settings[k]
            for k in ("model", "device", "language", "traditional")
        )
        hotkey_changed = new["hotkey"] != self.settings["hotkey"]
        self.settings = new
        save_settings(new)
        self._set_dot(self.engine.state if self.engine else "idle")
        if engine_changed:
            self._stop_hotkey()  # 載入完成後 _on_state('idle') 會用新設定重啟
            self._build_engine_and_load()
        elif hotkey_changed:
            self._start_hotkey()
        self.tray.showMessage("設定已儲存", "", QSystemTrayIcon.Information, 1500)

    # ---------- 視窗 / 托盤 / 離開 ----------
    def _on_tab_changed(self, index: int) -> None:
        if self.tabs.tabText(index) == "筆記歷史":
            self._reload_notes()

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # 關閉視窗＝縮回系統匣，不結束程式
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "仍在背景執行", "從系統匣圖示可再開啟或離開。", QSystemTrayIcon.Information, 2500
        )

    def _quit(self) -> None:
        self._stop_hotkey()
        try:
            self.notes.close()
        except Exception:  # noqa: BLE001
            pass
        self.tray.hide()
        self.app.quit()


def _setup_logging() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(APP_DIR / "gui.log"),
        filemode="a",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def main() -> int:
    _setup_logging()
    logging.info("gui 啟動")
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)  # 關視窗不等於離開
        _apply_light_theme(app)
        app.setStyleSheet(STYLE)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(None, "聽寫", "此系統沒有可用的系統匣，無法執行。")
            return 1
        window = AppWindow(app)  # 保住參照到事件迴圈結束
        window.show()
        logging.info("進入事件迴圈")
        return app.exec()
    except Exception:
        logging.exception("未攔截的例外，程式結束")
        raise


if __name__ == "__main__":
    sys.exit(main())
