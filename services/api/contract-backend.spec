# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_all


conda_bin = Path(sys.prefix) / "Library" / "bin"
runtime_binaries = [
    (conda_bin / "libssl-3-x64.dll", "."),
    (conda_bin / "libcrypto-3-x64.dll", "."),
    (conda_bin / "zlib.dll", "."),
]
runtime_binaries = [(str(path), target) for path, target in runtime_binaries if path.is_file()]

pymupdf_datas, pymupdf_binaries, pymupdf_hidden = collect_all("pymupdf")
fitz_datas, fitz_binaries, fitz_hidden = collect_all("fitz")
pil_datas, pil_binaries, pil_hidden = collect_all("PIL")
docx_datas, docx_binaries, docx_hidden = collect_all("docx")


a = Analysis(
    ['app/__main__.py'],
    pathex=[str(Path.cwd())],
    binaries=runtime_binaries + pymupdf_binaries + fitz_binaries + pil_binaries + docx_binaries,
    datas=[('app', 'app')] + pymupdf_datas + fitz_datas + pil_datas + docx_datas,
    hiddenimports=[
        'app.main',
        'uvicorn',
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'fitz',
        'pymupdf',
        *pymupdf_hidden,
        *fitz_hidden,
        *pil_hidden,
        *docx_hidden,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='contract-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
