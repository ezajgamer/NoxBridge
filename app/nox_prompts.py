# -*- coding: utf-8 -*-
"""
تعليمات NoxBridge 2 — الجسر يضيفها لطلبات الشخصيات قبل ما يرسلها للموديل.

اللعبة نفسها تحدد لغة المكالمة (مدخل «language» برسالة اللاعب) وشخصية المتصل
(## CALLER_PERSONALITY). احنا نضيف فوقها: اللهجة، وأسلوب الكلام المسموع، والصعوبة.
اللهجة على حسب الشخصية: الوسم «GULF DIALECT: Kuwaiti/Saudi/Emirati» أو
«ARABIC DIALECT: Egyptian/Sudanese/Yemeni/Pidgin» بوصفها ⇒ لهجتها، والباقين (شخصيات اللعبة الأصلية) عربي عام.
Pidgin = عربي العمالة الآسيوية بالخليج (Gulf Pidgin Arabic): أنا/إنت للكل، فعل بدون تصريف، «مافي» للنفي، «فيه» رابط.
"""

import re

# ردود الشخصيات بالمكالمة — غيرها (المراجعة، سجل العميل…) ما نلمسه
CALLER_SCHEMAS = ("gameplay_caller_turn", "celeris_caller_turn")

DIALECT_TAG = re.compile(r"(?:GULF|ARABIC) DIALECT:\s*(Kuwait|Saudi|Emirat|Egypt|Sudan|Yemen|Pidgin)", re.IGNORECASE)
TAG_DIALECT = {"kuwait": "kuwaiti", "saudi": "saudi", "emirat": "emirati",
               "egypt": "egyptian", "sudan": "sudanese", "yemen": "yemeni", "pidgin": "pidgin"}
# لكنة الصوت لو تختلف عن لهجة النص (مثلاً بنغالي يتكلم عربي العمالة ⇒ bn بدل hi)
ACCENT_TAG = re.compile(r"VOICE ACCENT:\s*([A-Za-z]{2}(?:-[A-Za-z]{2})?)(?![A-Za-z])")
ARABIC_CALL = re.compile(r'"code"\s*:\s*"ar"|\bArabic\b', re.IGNORECASE)

DIALECTS = {
    "kuwaiti": (
        "Speak everyday Kuwaiti Arabic for the whole call, the way people talk at home and in the diwaniya: "
        "شلونك، شنو، شفيك، وايد، الحين، أبي، ماكو، اكو، زين، جذي، ترى، عاد، يبه، خوش. "
        "Money is in Kuwaiti dinars (دينار، فلس). Never drift into Egyptian, Levantine or formal Arabic."
    ),
    "gulf": (
        "Speak natural everyday Gulf Arabic (Khaleeji) for the whole call: شلون، شنو/وش، ليش، الحين، أبي، زين، يعني، خلاص. "
        "Never drift into Egyptian, Levantine or formal Arabic."
    ),
    "emirati": (
        "Speak natural everyday Emirati Arabic for the whole call: شحالك، شو، ليش، الحين، أبا، زين، وايد، عيل، مب. "
        "Money is in UAE dirhams (درهم). Never drift into Egyptian, Levantine or formal Arabic."
    ),
    "egyptian": (
        "Speak natural everyday Egyptian Arabic (Masri) for the whole call: إزيك، إيه، ليه، فين، إمتى، دلوقتي، كده، أوي، "
        "مش، عايز/عايزة، ماشي، طب، يا باشا، يا حاج. Future with هـ (هعمل)، ongoing with بـ (بعمل)، and ده/دي/دول after the noun. "
        "Never drift into Gulf, Levantine or formal Arabic."
    ),
    "sudanese": (
        "Speak natural everyday Sudanese Arabic for the whole call: شنو، مالك، كيف، وين، متين، هسي، داير/دايرة (want)، "
        "زول، يا زول، ياخ، كدا، كدي (hold on / first)، شديد and بالحيل (very)، سمح (good)، عديل، قروش (money). "
        "Future with حـ (حمشي)، ongoing with بـ. Never drift into Egyptian, Gulf or formal Arabic."
    ),
    "yemeni": (
        "Speak natural everyday Yemeni Arabic (Sanaani) for the whole call: ايش/ماهو (what)، ليش، كيف، فين، متى، "
        "ذلحين (now)، أشتي/يشتي (want)، قد for things already done (قد قلت لك)، شا/با for the future (شاجي، بارجع)، "
        "مش، عاد، يا خبير، يا رجّال، زلط (money). Never drift into Egyptian, Levantine or formal Arabic."
    ),
    "pidgin": (
        "You are a South Asian worker in the Gulf, so speak the simple Gulf Pidgin Arabic that Indian and Pakistani workers "
        "really use: short sentences, أنا and إنت for everyone, verbs never conjugated (أنا يروح، إنت يسوي، هو يدفع)، "
        "مافي for every kind of no/not (مافي معلوم = I don't know، مافي زين)، فيه as 'is/has'، مال for 'of' (كارت مال أنا)، "
        "واجد (a lot)، شوية، كلام، نفر (person)، بابا/صديق/رفيق for men، and English words for things like card, bank, "
        "message, OTP, visa. Never conjugate like a native (not أسوي/يرحلوني/ما يشتغل — say أنا سوي، هو رحّل أنا، مافي شغل). "
        "Keep it natural and respectful, a real person, never a joke or a caricature."
    ),
    "arabic": (
        "Speak clear, simple everyday Arabic for the whole call that any Arab understands (white dialect): "
        "not stiff formal Arabic and not a heavy local dialect. Never drift into Egyptian or Levantine."
    ),
    "saudi": (
        "Speak natural everyday Saudi Arabic for the whole call (Najdi/Hejazi): وش، ليش، الحين، أبغى/أبي، زين، يا رجال، مره. "
        "Money is in Saudi riyals. Never drift into Egyptian, Levantine or formal Arabic."
    ),
}

SPOKEN = (
    "Your words are read aloud by a voice engine, so write them the way they are said: short complete sentences, "
    "numbers written as spoken words except exact codes from the game, no emojis, no stretched letters, "
    "no stage directions. Show feelings through word choice, not through punctuation or capital letters."
)

DIFFICULTY = {
    "easy": "Be an easy target: you trust quickly and one reasonable explanation is enough for you.",
    "normal": "",
    "realistic": "Be a careful target: notice contradictions and ask sensible follow-up questions, "
                 "but a clear and consistent explanation still convinces you. Never get stuck repeating the same doubt.",
}


def _system_text(messages: list) -> str:
    return "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")


def _all_text(messages: list) -> str:
    out = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, list):
            out.extend(str(p.get("text") or "") for p in c if isinstance(p, dict))
        else:
            out.append(str(c or ""))
    return "\n".join(out)


def is_caller_turn(body: dict) -> bool:
    fmt = body.get("response_format") or {}
    return (fmt.get("json_schema") or {}).get("name") in CALLER_SCHEMAS or body.get("ai_category") == "dialogue"


def dialect_for(messages: list) -> str:
    """لهجة الشخصية من وسمها بوصفها، وإلا عربي عام."""
    m = DIALECT_TAG.search(_system_text(messages))
    return TAG_DIALECT[m.group(1).lower()] if m else "arabic"


def accent_for(messages: list) -> str:
    """لكنة الصوت من وسم «VOICE ACCENT: bn» بوصف الشخصية، أو "" (على حسب اللهجة)."""
    m = ACCENT_TAG.search(_system_text(messages))
    return m.group(1) if m else ""


def apply(body: dict, difficulty: str) -> str:
    """يضيف تعليماتنا لطلب رد شخصية (يعدّل body). يرجّع وصف مختصر للسجل، أو "" لو ما تغيّر شي."""
    messages = body.get("messages")
    if not isinstance(messages, list) or not is_caller_turn(body):
        return ""
    notes, parts = [], []
    if ARABIC_CALL.search(_all_text(messages)):
        chosen = dialect_for(messages)
        if chosen in DIALECTS:
            parts.append(DIALECTS[chosen])
            notes.append(chosen)
        parts.append(SPOKEN)
    if DIFFICULTY.get(difficulty):
        parts.append(DIFFICULTY[difficulty])
        notes.append(difficulty)
    if not parts:
        return ""
    # بعد آخر رسالة نظام (قبل كلام اللاعب) عشان تكون آخر شي يقراه الموديل من التعليمات
    last_system = max((i for i, m in enumerate(messages) if m.get("role") == "system"), default=-1)
    messages.insert(last_system + 1, {"role": "system", "content": "## NOXBRIDGE STYLE\n" + "\n".join(parts)})
    return "·".join(notes) or "style"
