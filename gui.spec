# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir 打包（Windows, windowed）。

    pyinstaller gui.spec

產出 dist\\whisper-dictate-tw\\（含 whisper-dictate-tw.exe）。
模型不打包——首次執行才下載到 Hugging Face 快取。
原生庫/資料收集是主要脆弱點；build 後跑 exe，缺什麼再補 hiddenimports/collect_*。
"""
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

datas = []
binaries = []
hiddenimports = []

# OpenCC 字典（.ocd2）必須打包，否則繁化壞掉
datas += collect_data_files("opencc")
# faster-whisper 的資產（含內建 Silero VAD 等）
datas += collect_data_files("faster_whisper")

# 原生動態庫
binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("av")
binaries += collect_dynamic_libs("onnxruntime")

hiddenimports += collect_submodules("ctranslate2")
hiddenimports += ["av", "onnxruntime"]

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["openai", "tkinter", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="whisper-dictate-tw",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed（無主控台）
    disable_windowed_traceback=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="whisper-dictate-tw",
)
