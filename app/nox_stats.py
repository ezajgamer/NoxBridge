# -*- coding: utf-8 -*-
"""
إحصائيات الموديلات — كل رد يمر بالجسر ينسجّل هني (Save\\stats.json) عشان تعرف
بالأرقام أي موديل أسرع وأضمن تحت مهلة اللعبة.

لكل موديل: عدد الردود، مجموع الوقت، أبطأ رد، كم مرة تأخر وراح الطلب للاحتياط،
كم مرة فشل، وكم مرة ألغته اللعبة (عدّى المهلة).
"""

import os
import json
import threading

import nox_paths

STATS_PATH = os.path.join(nox_paths.SAVE, "stats.json")

_lock = threading.Lock()
_data = None
FIELDS = ("replies", "seconds", "slowest", "hedged", "failed", "cancelled")


def _load() -> dict:
    global _data
    if _data is None:
        try:
            with open(STATS_PATH, encoding="utf-8") as f:
                _data = json.load(f)
        except (OSError, ValueError):
            _data = {}
    return _data


def _save():
    try:
        os.makedirs(os.path.dirname(STATS_PATH), exist_ok=True)
        tmp = STATS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, STATS_PATH)
    except OSError:
        pass


def _entry(model: str) -> dict:
    d = _load()
    e = d.setdefault(model, {})
    for k in FIELDS:
        e.setdefault(k, 0)
    return e


def reply(model: str, seconds: float):
    """رد ناجح من الموديل (الوقت الكلي من وصول الطلب)."""
    with _lock:
        e = _entry(model)
        e["replies"] += 1
        e["seconds"] = round(e["seconds"] + seconds, 2)
        e["slowest"] = round(max(e["slowest"], seconds), 2)
        _save()


def event(model: str, kind: str):
    """hedged = تأخر/فشل وراح للاحتياط · failed = خطأ · cancelled = اللعبة ألغت الطلب."""
    if kind not in ("hedged", "failed", "cancelled"):
        return
    with _lock:
        _entry(model)[kind] += 1
        _save()


def summary() -> list:
    """[{model, replies, avg, slowest, hedged, failed, cancelled}] مرتبة بعدد الاستخدام."""
    with _lock:
        rows = []
        for model, e in _load().items():
            total = e.get("replies", 0) + e.get("failed", 0) + e.get("cancelled", 0)
            rows.append({
                "model": model,
                "replies": e.get("replies", 0),
                "avg": (e["seconds"] / e["replies"]) if e.get("replies") else None,
                "slowest": e.get("slowest") or None,
                "hedged": e.get("hedged", 0),
                "failed": e.get("failed", 0),
                "cancelled": e.get("cancelled", 0),
                "total": total,
            })
        return sorted(rows, key=lambda r: -(r["total"] + r["hedged"]))


def reset():
    global _data
    with _lock:
        _data = {}
        _save()


def backfill_from_log(log_path: str) -> int:
    """أول مرة (ما فيه stats.json): نبني الإحصائيات من سجل الجسر القديم. يرجّع عدد الأسطر."""
    import re
    if os.path.isfile(STATS_PATH):
        return 0
    ok = re.compile(r"^\[[^\]]+\] ✓ (\S+)(?: ⚡احتياط)? ([\d.]+)s · .*توكن")
    hedge = re.compile(r"^\[[^\]]+\] ⚡ (\S+) .*أرسلت نفس الطلب")
    gone = re.compile(r"^\[[^\]]+\] ↩ (\S+) اللعبة ألغت")
    fail = re.compile(r"^\[[^\]]+\] ✗ (?!صوت|تفريغ)(\S+) ")
    n = 0
    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                if m := ok.match(line):
                    reply(m.group(1), float(m.group(2)))
                elif m := hedge.match(line):
                    event(m.group(1), "hedged")
                elif m := gone.match(line):
                    event(m.group(1), "cancelled")
                elif m := fail.match(line):
                    event(m.group(1), "failed")
                else:
                    continue
                n += 1
    except OSError:
        pass
    if not n:
        with _lock:
            _load()
            _save()   # ملف فاضي = ما نعيد المحاولة كل مرة
    return n
