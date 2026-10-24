# -*- coding: utf-8 -*-
"""
أصوات Grok لشخصيات اللعبة (NoxBridge 2).

اللعبة تعطي كل شخصية ملف صوت مرجعي (voiceId مثل kolkata-voices/Connor/dorothy_mayfield.wav)
وجنس (gender) بملفات caller-identities. نختار صوت Grok من نفس الجنس، وثابت لنفس الملف
(نفس الشخصية = نفس الصوت كل مرة). الملف المجهول ← صوت ثابت من الكل.
"""

import os
import json
import zlib
import threading

MALE = ("rex", "leo", "sal")
FEMALE = ("ara", "eve")

_lock = threading.Lock()
_cache = {"dir": None, "stamp": None, "genders": {}}


def _norm(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lower()


def _genders(game_dir: str) -> dict:
    """{voiceId: "male"/"female"} من كل ملفات الشخصيات (تتحدث لو تغيّرت الملفات)."""
    folder = os.path.join(game_dir, "Scam With Your Friends_Data", "StreamingAssets", "kolkata-json", "caller-identities")
    try:
        stamp = max((e.stat().st_mtime for e in os.scandir(folder) if e.name.endswith(".json")), default=0)
    except OSError:
        return {}
    with _lock:
        if _cache["dir"] == folder and _cache["stamp"] == stamp:
            return _cache["genders"]
        genders = {}
        for entry in os.scandir(folder):
            if not entry.name.endswith(".json"):
                continue
            try:
                with open(entry.path, encoding="utf-8-sig") as f:
                    data = json.load(f)
            except (OSError, ValueError):
                continue
            for item in data if isinstance(data, list) else [data]:
                if isinstance(item, dict) and item.get("voiceId") and item.get("gender"):
                    g = str(item["gender"]).lower()
                    genders[_norm(item["voiceId"])] = "female" if g.startswith("f") else "male"
        _cache.update(dir=folder, stamp=stamp, genders=genders)
        return genders


# أصوات اللعبة اللي ما لها جنس بملفات الشخصيات: من اسم الملف. الباقي من kolkata-voices رجال.
FEMALE_HINTS = ("dorothy", "sloane", "shanice", "troyana", "valleygurl", "valley", "granny", "grandma",
                "brittany", "lexi", "eleanor", "woman", "girl", "female", "lady", "um_", "haila", "nouf")


def _guess(key: str):
    name = key.rsplit("/", 1)[-1]
    if any(h in name for h in FEMALE_HINTS):
        return "female"
    return "male" if key.startswith("kolkata-voices/") else None


def pick(voice_path: str, game_dir: str) -> str:
    """صوت Grok للملف المرجعي."""
    key = _norm(voice_path)
    gender = _genders(game_dir).get(key) or _guess(key)
    pool = FEMALE if gender == "female" else MALE if gender == "male" else MALE + FEMALE
    return pool[zlib.crc32(key.encode("utf-8")) % len(pool)]


# ═══════════════════════════════════════════════════ لكنة النطق على حسب الشخصية
# طلب الصوت من اللعبة فيه النص وملف الصوت بس (ملفات الأصوات مشتركة بين شخصيات). فالجسر
# يتذكر نص كل رد شخصية مع لهجتها، ويعرف جمل الافتتاح من ملف شخصياتنا، ويطابق النص.
# Grok ما عنده نطق كويتي/سوداني/يمني — الأقرب. «hi» = صوت هندي يقرا العربي (لكنة العمالة).
TTS_FOR = {
    "kuwaiti": "ar-AE", "emirati": "ar-AE", "saudi": "ar-SA", "yemeni": "ar-SA",
    "egyptian": "ar-EG", "sudanese": "ar-EG", "pidgin": "hi",
}
_spoken = []                  # [(نص مطبّع, لهجة, لكنة)] الأحدث آخر
_SPOKEN_MAX = 300
_firsts = {"path": None, "stamp": None, "map": {}}


def _text_key(text: str) -> str:
    """حروف وأرقام بس — النقط والتشكيل والمسافات ما تفرق."""
    return "".join(ch for ch in str(text or "") if ch.isalnum())


def _strings(value) -> list:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def tts_lang(dialect: str, accent: str = "") -> str:
    """لكنة النطق: وسم الشخصية لو موجود، وإلا الأقرب للهجتها، وإلا "" (الإعداد العام)."""
    return accent or TTS_FOR.get(dialect) or ""


def remember_reply(result: dict, dialect: str, accent: str = ""):
    """رد الموديل لشخصية: كل نص فيه (الرد JSON حسب سكيمة اللعبة) ينحفظ مع لهجتها ولكنتها."""
    if not dialect:
        return
    lang = tts_lang(dialect, accent)
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return
    try:
        texts = _strings(json.loads(content))
    except (ValueError, TypeError):
        texts = [content]
    with _lock:
        for t in texts:
            key = _text_key(t)
            if len(key) >= 4:
                _spoken.append((key, dialect, lang))
        del _spoken[:-_SPOKEN_MAX]


def _first_lines(game_dir: str) -> dict:
    """{جملة افتتاح مطبّعة: (لهجة, لكنة)} من ملف شخصياتنا باللعبة."""
    import nox_prompts
    path = os.path.join(game_dir, "Scam With Your Friends_Data", "StreamingAssets", "kolkata-json",
                        "caller-identities", "nox-callers.json") if game_dir else ""
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return {}
    with _lock:
        if _firsts["path"] == path and _firsts["stamp"] == stamp:
            return _firsts["map"]
    out = {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        for c in data if isinstance(data, list) else []:
            sys_msg = [{"role": "system", "content": str(c.get("personalityPrompt") or "")}]
            d = nox_prompts.dialect_for(sys_msg)
            for line in c.get("firstMessages") or []:
                out[_text_key(line)] = (d, tts_lang(d, nox_prompts.accent_for(sys_msg)))
    except (OSError, ValueError, AttributeError):
        out = {}
    with _lock:
        _firsts.update(path=path, stamp=stamp, map=out)
    return out


def speaker_of(text: str, game_dir: str) -> tuple:
    """(لهجة, لكنة) الشخصية اللي تقول هالنص، أو ("", "") لو ما عرفناها (شخصيات اللعبة ← الإعداد العام).
    اللعبة ممكن تقسّم الرد لجمل — نقبل لو النص جزء من رد محفوظ."""
    key = _text_key(text)
    if len(key) < 4:
        return "", ""
    firsts = _first_lines(game_dir)
    if key in firsts:
        return firsts[key]
    with _lock:
        for saved, dialect, lang in reversed(_spoken):
            if key in saved or (len(saved) >= 12 and saved in key):
                return dialect, lang
    for line, found in firsts.items():
        if key in line:
            return found
    return "", ""
