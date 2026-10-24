# -*- coding: utf-8 -*-
"""
ترجمة الشاشات الإنجليزية داخل اللعبة (NoxBridge 2).

NoxGame.Text داخل اللعبة يرسل النصوص الإنجليزية اللي ما لها ترجمة (قوالب: الأرقام ووسوم
التنسيق صارت ⟦0⟧ ⟦1⟧…). نترجمها بـGrok دفعة وحدة، نتأكد إن العلامات سليمة، ونحفظها بـ
NoxText.json بمجلد اللعبة (المكتبة تقراه مع بداية اللعبة، والجديد يوصلها بالرد).
"""

import os
import re
import json
import threading

MODEL = "grok-4.20-beta-latest-non-reasoning"   # سريع وبلا تفكير — الترجمة ما تحتاجه
SLOT = re.compile(r"⟦\d+⟧")
BATCH = 40

SYSTEM = (
    "You translate user-interface text from a comedy video game about scam phone calls "
    "(an in-game computer: apps, notes, emails, forms, buttons, notifications) into natural, concise Arabic "
    "for players in the Gulf. Rules: keep every marker like ⟦0⟧ exactly once and unchanged (they stand for numbers "
    "or formatting); keep it short like the original UI text; keep brand names, app names, usernames, codes, "
    "emails and URLs as they are; transliterate personal names into Arabic letters; never add explanations. "
    'Reply with JSON only: {"t": [translations in the same order]}.'
)

_lock = threading.Lock()
_table = {"path": None, "data": {}}


def _path(game_dir: str) -> str:
    # بلا مجلد لعبة (ما انلقت) ⇒ لا نكتب بمجلد التشغيل
    return os.path.join(game_dir, "NoxText.json") if game_dir else os.devnull


def _load(game_dir: str) -> dict:
    path = _path(game_dir)
    if _table["path"] != path:
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
            _table.update(path=path, data=data if isinstance(data, dict) else {})
        except (OSError, ValueError):
            _table.update(path=path, data={})
    return _table["data"]


def _save(game_dir: str, data: dict):
    if not game_dir:
        return
    path = _path(game_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
    os.replace(tmp, path)


def count(game_dir: str) -> int:
    with _lock:
        return len(_load(game_dir))


def clear(game_dir: str):
    with _lock:
        _table.update(path=_path(game_dir), data={})
        if not game_dir:
            return
        try:
            os.remove(_path(game_dir))
        except OSError:
            pass


def _valid(source: str, target) -> bool:
    return isinstance(target, str) and target.strip() != "" and sorted(SLOT.findall(source)) == sorted(SLOT.findall(target))


async def translate(bridge, texts: list, game_dir: str, log) -> dict:
    """يرجّع {نص: ترجمة} لكل اللي انترجم (من المحفوظ أو جديد)."""
    texts = [t for t in dict.fromkeys(str(x) for x in texts) if t.strip()][:200]
    with _lock:
        known = _load(game_dir)
        out = {t: known[t] for t in texts if t in known}
    todo = [t for t in texts if t not in out]
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        payload = {
            "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": json.dumps({"t": batch}, ensure_ascii=False)}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        result = await bridge._chat_once(payload)
        content = result["choices"][0]["message"]["content"]
        try:
            translated = json.loads(content).get("t") or []
        except (ValueError, AttributeError):
            translated = []
        good = {s: t.strip() for s, t in zip(batch, translated) if _valid(s, t)}
        with _lock:
            known = _load(game_dir)
            known.update(good)
            _save(game_dir, known)
        out.update(good)
        log(f"🌐 ترجمة الشاشات: {len(good)} من {len(batch)} نص (المجموع {len(known)})")
    return out
