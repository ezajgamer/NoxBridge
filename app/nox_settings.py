# -*- coding: utf-8 -*-
"""
إعدادات NoxBridge، ومجلد اللعبة، والتركيب.

- إعدادات البرنامج (الموديل، التفكير، الاحتياط، الصوت، الترجمة، الصعوبة…) ← Save\\settings.json،
  الجسر يطبّقها على الطلب الجاي.
- الصوت والترجمة داخل اللعبة (NoxGame) يقرونها من NoxBridge.json بمجلد اللعبة مع بدايتها.
- مهلة رد الشخصية مزروعة بملفات اللعبة ← تتغير بإعادة التركيب (المرقّع) واللعبة مسكّرة.
"""

import os
import re
import json
import subprocess
import threading

import nox_paths

SETTINGS_PATH = os.path.join(nox_paths.SAVE, "settings.json")

GAME_EXE = "Scam With Your Friends.exe"
GAME_APPID = "4954910"
GAME_FOLDER = "Scam With Your Friends"   # اسمه تحت steamapps\common لو ملف ستيم ما ذكره
BRIDGE_DEFAULTS = {
    "reasoning_effort": "low",
    "fallback_model": "grok-4.20-0309-non-reasoning",
    "hedge_after": 8.0,     # ثواني قبل ما يروح نفس الطلب للاحتياط
    "timeout": 15,          # مهلة رد الشخصية باللعبة (١٥ = الأصل حق اللعبة)
    "local_enabled": False,  # المحلي (LM Studio) ما ينحسب مربوط إلا لما يضغط «ربط»
    "game_dir": "",         # مجلد اللعبة لو اختاره المستخدم بنفسه (غير كذا ينلقى من ستيم)
    "auto_unload": False,   # البرنامج يفرّغ موديلات LM Studio من الكرت لما تتسكّر اللعبة
    "llm_model": "",        # موديل رد الشخصيات (الجسر يختاره — اللعبة ترسل موديل وهمي)
    "difficulty": "normal",
    "voice": "grok",        # صوت الشخصيات العربي: grok / game
    "voice_lang": "ar-SA",  # نطق شخصيات اللعبة الأصلية (شخصياتنا على حسب لهجتها)
    "stt": "grok",          # تفريغ المايك: grok (لو اللعبة فيها Deepgram) / game
    "translate": True,      # ترجمة الشاشات الإنجليزية داخل اللعبة بـGrok
}
EFFORTS = ("", "low", "medium", "high")

TTS_LANGS = {"ar-SA": "سعودي", "ar-AE": "إماراتي", "ar-EG": "مصري"}

DIFFICULTIES = ("easy", "normal", "realistic")
_lock = threading.Lock()
_settings = None
_install_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════ الجسر

def bridge_settings() -> dict:
    """إعدادات الجسر الحالية (تنقرا مرة وتنحفظ بالذاكرة)."""
    global _settings
    with _lock:
        if _settings is None:
            _settings = dict(BRIDGE_DEFAULTS)
            try:
                with open(SETTINGS_PATH, encoding="utf-8") as f:
                    saved = json.load(f)
                for k in BRIDGE_DEFAULTS:
                    if k in saved:
                        _settings[k] = saved[k]
            except (OSError, ValueError):
                pass
        return dict(_settings)


def set_bridge_option(key: str, value):
    """يحفظ خيار واحد من إعدادات الجسر."""
    if key not in BRIDGE_DEFAULTS:
        raise KeyError(key)
    b = bridge_settings()
    b[key] = value
    _save_bridge(b)


def _save_bridge(new: dict):
    global _settings
    with _lock:
        _settings = new
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        _write_json(SETTINGS_PATH, new)


# ═══════════════════════════════════════════════════════════════ اللعبة

def is_game_dir(d: str) -> bool:
    return bool(d) and os.path.isfile(os.path.join(d, GAME_EXE))


def _steam_libraries() -> list:
    """كل مكتبات ستيم بالجهاز: مكان ستيم من الريجستري + libraryfolders.vdf."""
    import winreg
    roots = []
    for hive, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                             (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
        try:
            with winreg.OpenKey(hive, key) as k:
                roots.append(os.path.normpath(winreg.QueryValueEx(k, value)[0]))
        except OSError:
            pass
    libs = []
    for steam in roots:
        libs.append(steam)
        try:
            with open(os.path.join(steam, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
                libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', f.read())]
        except OSError:
            pass
    seen, out = set(), []
    for lib in libs:
        key = os.path.normcase(os.path.normpath(lib))
        if key not in seen:
            seen.add(key)
            out.append(os.path.normpath(lib))
    return out


def find_steam_game() -> str:
    """مجلد اللعبة من مكتبات ستيم، أو "" لو ما لقاها."""
    try:
        libs = _steam_libraries()
    except Exception:
        return ""
    for lib in libs:
        apps = os.path.join(lib, "steamapps")
        folder = GAME_FOLDER
        try:
            with open(os.path.join(apps, f"appmanifest_{GAME_APPID}.acf"), encoding="utf-8", errors="replace") as f:
                m = re.search(r'"installdir"\s+"([^"]+)"', f.read())
            folder = m.group(1) if m else folder
        except OSError:
            pass
        d = os.path.join(apps, "common", folder)
        if is_game_dir(d):
            return d
    return ""


_found = {"dir": ""}


def game_dir() -> str:
    """مجلد اللعبة: اللي اختاره المستخدم، وإلا من ستيم. "" لو ما لقاها."""
    chosen = bridge_settings().get("game_dir") or ""
    if is_game_dir(chosen):
        return chosen
    if not is_game_dir(_found["dir"]):
        _found["dir"] = find_steam_game()
    return _found["dir"]


def set_game_dir(d: str) -> bool:
    """يحفظ مجلد اختاره المستخدم (لازم فيه exe اللعبة)."""
    if not is_game_dir(d):
        return False
    set_bridge_option("game_dir", os.path.normpath(d))
    return True


def _in_game(*parts) -> str:
    gd = game_dir()
    return os.path.join(gd, *parts) if gd else ""


def game_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {GAME_EXE}", "/NH"],
                             capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return GAME_EXE.lower() in out.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def mod_installed(gd: str) -> bool:
    """المود مركّب باللعبة؟ تحديث ستيم يرجّع ملفاتها أصلية."""
    return installed_version(gd) == 2


def chat_model() -> str:
    """موديل رد الشخصيات (الجسر يختاره — اللعبة ترسل موديل وهمي)."""
    return bridge_settings().get("llm_model") or ""


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: str, data: dict):
    # كتابة ذرّية: ما نبي أحد يقرا نص ملف
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ═══════════════════════════════════════════════════════════════ الإعدادات

def current() -> dict:
    """كل اللي تحتاجه واجهة البرنامج."""
    gd = game_dir()
    info = _read_json(_in_game("NoxBridge.json"))
    b = bridge_settings()
    return {
        "llm_model": b.get("llm_model") or "",
        "reasoning_effort": b["reasoning_effort"],
        "fallback_model": b["fallback_model"],
        "hedge_after": b["hedge_after"],
        "tts": (b.get("voice_lang") or "ar-SA") if b.get("voice") == "grok" else "game",
        "stt": b.get("stt") or "grok",
        "translate": bool(b.get("translate", True)),
        "difficulty": b.get("difficulty") or "normal",
        "timeout": info.get("TurnBudgetSeconds"),
        "installed_at": info.get("InstalledAt"),
        "mod_installed": mod_installed(gd),
        "game_running": game_running(),
        "game_dir": gd,
        "tts_langs": TTS_LANGS,
    }


def save(data: dict) -> dict:
    """يحفظ إعدادات البرنامج. يرجّع {ok, error?}."""
    b = bridge_settings()
    effort = str(data.get("reasoning_effort", b["reasoning_effort"]))
    if effort not in EFFORTS:
        return {"ok": False, "error": "مستوى تفكير غير معروف"}
    try:
        hedge = float(data.get("hedge_after", b["hedge_after"]))
    except (TypeError, ValueError):
        return {"ok": False, "error": "وقت التحويل للاحتياط لازم رقم"}
    if not 3 <= hedge <= 60:
        return {"ok": False, "error": "وقت التحويل للاحتياط بين ٣ و٦٠ ثانية"}
    b.update(reasoning_effort=effort, hedge_after=hedge,
             fallback_model=str(data.get("fallback_model", b["fallback_model"])).strip())
    if str(data.get("llm_model") or "").strip():
        b["llm_model"] = str(data["llm_model"]).strip()
    if str(data.get("difficulty") or "") in DIFFICULTIES:
        b["difficulty"] = str(data["difficulty"])
    tts = str(data.get("tts") or "")
    if tts == "game":
        b["voice"] = "game"
    elif tts in TTS_LANGS:
        b.update(voice="grok", voice_lang=tts)
    if str(data.get("stt") or "") in ("grok", "game"):
        b["stt"] = str(data["stt"])
    if "translate" in data:
        b["translate"] = bool(data["translate"])
    _set_game_flags(b)
    _save_bridge(b)
    return {"ok": True}


def _set_game_flags(b: dict):
    """NoxGame داخل اللعبة يقرا "Voice" و"Translate" من NoxBridge.json مع بداية اللعبة."""
    path = _in_game("NoxBridge.json")
    if not path:
        return
    info = _read_json(path)
    if info.get("Version") != 2:
        return
    flags = {"Voice": b.get("voice") or "grok", "Translate": bool(b.get("translate", True))}
    if any(info.get(k) != v for k, v in flags.items()):
        info.update(flags)
        _write_json(path, info)


def installed_version(gd: str = None) -> int:
    """٢ = NoxBridge مركّب، ١ = مود قديم ثاني (المرقّع يشيله بالتركيب)، ٠ = أصلية."""
    gd = gd or game_dir()
    if not gd:
        return 0
    try:
        with open(os.path.join(gd, "Scam With Your Friends_Data", "Managed", "Assembly-CSharp.dll"), "rb") as f:
            data = f.read()
    except OSError:
        return 0
    if "8797/nox/".encode("utf-16-le") in data:
        return 2
    return 1 if b"NoxBridge" in data else 0


def install(seconds=None) -> dict:
    """يركّب (أو يعيد التركيب بعد تحديث ستيم). المهلة: المحفوظة، أو الجديدة لو انعطت (وتنحفظ).
    اللعبة لازم مسكّرة."""
    try:
        seconds = float(bridge_settings().get("timeout") or 15) if seconds is None else float(seconds)
    except (TypeError, ValueError):
        return {"ok": False, "error": "المهلة لازم رقم"}
    if not 10 <= seconds <= 90:
        return {"ok": False, "error": "المهلة بين ١٠ و٩٠ ثانية"}
    set_bridge_option("timeout", seconds)
    b = bridge_settings()
    return _patcher("install", "--data", nox_paths.data_dir(),
                    "--game-dll", nox_paths.game_dll(), "--seconds", f"{seconds:g}",
                    "--voice", b.get("voice") or "grok", "--stt", b.get("stt") or "grok",
                    "--translate", "on" if b.get("translate", True) else "off")


def restore() -> dict:
    """يرجّع اللعبة أصلية. اللعبة لازم مسكّرة."""
    return _patcher("restore")


def _patcher(command: str, *args) -> dict:
    command_line = nox_paths.patcher_command()
    if not game_dir():
        return {"ok": False, "error": "ما لقيت اللعبة — اختر مجلدها من «مجلد اللعبة» بالرئيسية"}
    if game_running():
        return {"ok": False, "error": "سكّر اللعبة أول — ملفاتها مقفولة وهي شغّالة"}
    if not os.path.isfile(command_line[-1]):
        return {"ok": False, "error": f"ما لقيت {command_line[-1]} — ابنِ المرقّع أول"}
    if not _install_lock.acquire(blocking=False):
        return {"ok": False, "error": "المرقّع شغّال أصلاً"}
    try:
        r = subprocess.run([*command_line, command, "--game", game_dir(), *args],
                           capture_output=True, timeout=300,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
        ok = r.returncode == 0
        return {"ok": ok, "output": out, "error": None if ok else (out.splitlines()[-1] if out else "فشل المرقّع")}
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    finally:
        _install_lock.release()
