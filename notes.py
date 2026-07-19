"""筆記儲存：每次聽寫／匯入的結果存進本機 SQLite，可搜尋、複製、刪除。

純 stdlib（sqlite3），無外部相依。DB 位於 %APPDATA%\\voice2text-dictate\\notes.db。
"""
from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.environ.get("APPDATA") or Path.home()) / "voice2text-dictate" / "notes.db"


@dataclass
class Note:
    id: int
    created_at: str
    text: str
    source: str  # 'dictation' | 'file'


class NotesStore:
    def __init__(self, path: Path = DB_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # 允許跨執行緒使用；所有存取都在 self._lock 內
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS notes ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " created_at TEXT NOT NULL,"
            " text TEXT NOT NULL,"
            " source TEXT NOT NULL DEFAULT 'dictation',"
            " meta TEXT NOT NULL DEFAULT '')"
        )
        self._conn.commit()

    def add(self, text: str, source: str = "dictation", meta: str = "") -> int:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO notes(created_at, text, source, meta) VALUES (?,?,?,?)",
                (ts, text, source, meta),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def search(self, query: str = "", limit: int = 500) -> list[Note]:
        with self._lock:
            if query:
                rows = self._conn.execute(
                    "SELECT id, created_at, text, source FROM notes"
                    " WHERE text LIKE ? ORDER BY id DESC LIMIT ?",
                    (f"%{query}%", limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id, created_at, text, source FROM notes"
                    " ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [Note(*row) for row in rows]

    def delete(self, note_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
