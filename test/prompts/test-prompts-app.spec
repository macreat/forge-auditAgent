# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

llama_datas, llama_binaries, llama_hidden = collect_all("llama_cpp")

a = Analysis(
    ["app/launcher.py"],
    pathex=["."],
    binaries=llama_binaries,
    datas=llama_datas,
    hiddenimports=[
        "llama_cpp",
        "llama_cpp.server",
        "llama_cpp.server.app",
        "llama_cpp.server.settings",
        "numpy",
        "flet",
        "flet_desktop",
        "flet_core",
        "flet_runtime",
        "uvicorn",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "fastapi",
        "sse_starlette",
        "starlette_context",
        "diskcache",
        "jinja2",
        "pydantic_settings",
    ] + llama_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "pandas",
        "PIL",
        "scipy",
        "IPython",
        "jedi",
        "notebook",
        "torch",
        "tensorflow",
        "sympy",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="test-prompts-app",
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
