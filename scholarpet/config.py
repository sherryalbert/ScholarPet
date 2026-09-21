"""User settings stay outside the repository; API keys use Windows DPAPI."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path

DEFAULTS = dict(engine="offline", api_base="https://api.deepseek.com/v1",
                api_model="deepseek-chat", api_key="", color="#6475ed",
                pet_size=100, opacity=96, animate=True, view="overlay",
                font_size=15, glossary={}, first_run=True,
                selection_enabled=True, popup_side="auto", popup_width=430,
                pet_avatar=True, topmost=True)


def data_dir():
    path = Path(os.environ.get("SCHOLARPET_DATA_DIR") or
                Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ScholarPet")
    path.mkdir(parents=True, exist_ok=True)
    return path


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(value: bytes, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("API 密钥持久保存需要 Windows DPAPI。")
    buffer = ctypes.create_string_buffer(value)
    source = _Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = _Blob()
    crypt = ctypes.windll.crypt32
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    # CRYPTPROTECT_UI_FORBIDDEN: never display a credential dialog.
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise RuntimeError("Windows 无法读取或保存加密密钥，请重新填写。")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def load_settings():
    settings = DEFAULTS.copy()
    settings["glossary"] = {}
    try:
        raw = json.loads((data_dir() / "settings.json").read_text("utf-8"))
        settings.update({k: v for k, v in raw.items() if k in DEFAULTS and k != "api_key"})
        if raw.get("encrypted_key"):
            settings["api_key"] = _crypt(base64.b64decode(raw["encrypted_key"]), True).decode()
    except (OSError, ValueError, TypeError, RuntimeError):
        pass
    settings["pet_size"] = max(76, min(160, int(settings.get("pet_size", 100))))
    settings["opacity"] = max(45, min(100, int(settings.get("opacity", 96))))
    return settings


def save_settings(settings):
    safe = {k: v for k, v in settings.items() if k in DEFAULTS and k != "api_key"}
    if settings.get("api_key"):
        safe["encrypted_key"] = base64.b64encode(_crypt(settings["api_key"].encode())).decode()
    path = data_dir() / "settings.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(safe, ensure_ascii=False, indent=2), "utf-8")
    temporary.replace(path)
