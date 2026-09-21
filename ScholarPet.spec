# Keep libraries external: faster launch, transparent redistribution and LGPL replacement.
import os
import sys
from pathlib import Path

from PyInstaller.building.datastruct import TOC
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


def _normalized(entry):
    """Return (destination name, normalized source path) for a TOC entry."""
    name, source = entry[0], entry[1]
    return str(name), os.path.normcase(str(source)).replace("\\", "/")


def _is_codex_native(entry):
    """True for binaries pulled from the desktop runtime's bundled native tree.

    This build runs on a Python baseline that lives inside
    ``.cache/codex-runtimes/codex-primary-runtime/dependencies``. That runtime
    exposes several vendored native packages (poppler, git, libheif ...) on the
    DLL search path, so PyInstaller happily resolves Qt's or OpenSSL's DLL
    imports against those copies. Shipping them is wrong on two counts:

    * Poppler's ``icuuc.dll`` / ``icudt78.dll`` shadow the ICU build Qt needs
      and make ``import PySide6.QtCore`` fail with "找不到指定的程序".
    * Poppler's ``libssl-3-x64.dll`` / ``libcrypto-3-x64.dll`` replace CPython's
      own OpenSSL, which can silently break HTTPS.

    Only the ``native`` subtree is rejected. The interpreter's own DLLs live in
    ``dependencies/python/DLLs`` and must be kept.
    """
    _name, source = _normalized(entry)
    return "codex-runtimes/" in source and "/native/" in source


# DLLs CPython needs at runtime. If Analysis resolved them against the
# runtime's native tree they are dropped with it, so they are re-added from the
# interpreter's own DLL directory afterwards.
_PYTHON_DLL_DIR = Path(sys.base_prefix) / "DLLs"
_REQUIRED_FROM_PYTHON = ("libssl-3-x64.dll", "libcrypto-3-x64.dll", "libffi-8.dll")

a = Analysis(['run.py'], pathex=[],
             binaries=collect_dynamic_libs('onnxruntime'),
             datas=collect_data_files('rapidocr_onnxruntime') + [
                 ('assets/haibara_head.png', 'assets'),
                 ('assets/haibara_head.rig.json', 'assets'),
                 ('THIRD_PARTY_NOTICES.md', '.'),
                 ('models/translate-en_zh-1_9', 'models/translate-en_zh-1_9'),
             ],
             hiddenimports=['onnxruntime.capi.onnxruntime_pybind11_state', 'scholarpet.offline', 'scholarpet.selftest', 'ctranslate2', 'sentencepiece'],
             hookspath=[], hooksconfig={}, runtime_hooks=[],
             excludes=['tkinter', 'matplotlib', 'scipy', 'pandas', 'PySide6.QtWebEngineCore'],
             noarchive=False)

# Filter after Analysis so this also covers binaries discovered by hooks rather
# than only the explicit ``collect_dynamic_libs`` list above.
kept = [entry for entry in a.binaries if not _is_codex_native(entry)]
dropped = [entry for entry in a.binaries if _is_codex_native(entry)]
for name, source in sorted(_normalized(entry) for entry in dropped):
    print(f"[spec] dropped native runtime binary: {name} <- {source}")

present = {os.path.normcase(os.path.basename(_normalized(entry)[1])) for entry in kept}
for dll in _REQUIRED_FROM_PYTHON:
    candidate = _PYTHON_DLL_DIR / dll
    if dll in present or not candidate.is_file():
        continue
    kept.append((dll, str(candidate), "BINARY"))
    print(f"[spec] restored from interpreter: {dll} <- {candidate}")

a.binaries = TOC(kept)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ScholarPet',
          debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
          console=False, disable_windowed_traceback=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ScholarPet')
