# -*- coding: utf-8 -*-
"""
جسر NoxBridge المحلي — اللعبة تكلّمه بدل خدمات الذكاء الاصطناعي، وهو يرد من اشتراك المستخدم.

المرقّع (patcher/) يحوّل روابط اللعبة لهني، وNoxGame.dll داخل اللعبة يطلب الصوت والترجمة:
- /nox/v1/chat/completions  ردود الشخصيات (خيار «OpenRouter بمفتاحك» باللعبة) ← Grok / ChatGPT / موديل محلي،
                            مع لهجة الشخصية وصعوبتها (nox_prompts) واحتياط لو تأخر الموديل.
- /nox/v1/tts               صوت الشخصية العربي (xAI TTS) بلكنتها (nox_voices).
- /nox/v1/translate         ترجمة نصوص الواجهة الإنجليزية (nox_translate).
- /nox/deepgram/listen      تفريغ المايك (xAI STT) — لإصدارات اللعبة اللي فيها Deepgram.

يسمع على 127.0.0.1 بس. البرنامج (nox_app.pyw) يشغّله؛ أو لحاله: py nox_bridge.py [--login | --logout | --no-login]
"""

import os
import sys
import json
import time
import socket
import select
import asyncio
import threading
import concurrent.futures
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# بايثون يثق بقائمة certifi مو بمخزن ويندوز، فبرنامج الحماية اللي يفحص الاتصالات المشفرة
# بشهادته يطيّح الطلبات (CERTIFICATE_VERIFY_FAILED). نستخدم مخزن ويندوز — التحقق يظل كامل.
import truststore  # noqa: E402
truststore.inject_into_ssl()

import httpx  # noqa: E402

import nox_auth  # noqa: E402
import nox_settings  # noqa: E402
import nox_providers  # noqa: E402
import nox_stats  # noqa: E402
import nox_prompts  # noqa: E402
import nox_voices  # noqa: E402
import nox_translate  # noqa: E402
import base64  # noqa: E402
import struct  # noqa: E402
from nox_providers import ProviderError  # noqa: E402
from nox_auth import AuthError, NotLoggedIn, Xai  # noqa: E402

import nox_paths  # noqa: E402
HERE = os.path.dirname(os.path.abspath(__file__))
SAVE_DIR = nox_paths.SAVE
AUTH_PATH = os.path.join(SAVE_DIR, "xai-auth.json")
GPT_AUTH_PATH = os.path.join(SAVE_DIR, "openai-auth.json")
LOG_PATH = os.path.join(SAVE_DIR, "bridge.log")

HOST = "127.0.0.1"
PORT = int(os.environ.get("NOXBRIDGE_PORT", "8797"))
API_BASE = os.environ.get("XAI_BASE_URL", "https://api.x.ai/v1")
# بدون تفكير: اللعبة تلغي رد الشخصية بعد 15 ثانية (CallerAiPipeline.TurnBudgetSeconds)،
# والموديلات اللي تفكّر تعدّيها لما تطول المكالمة (قياس 20/10: ~1.4s مقابل 9–11s)
DEFAULT_MODEL = "grok-4.20-beta-latest-non-reasoning"
UPSTREAM_TIMEOUT = 120.0

# احتياط لو جلب قائمة الموديلات من xAI فشل
FALLBACK_MODELS = [
    ("grok-4.20-beta-latest-non-reasoning", "Grok 4.20 Non-Reasoning"),
    ("grok-4.5", "Grok 4.5"),
    ("grok-4.3", "Grok 4.3"),
    ("grok-4.20-beta-latest-reasoning", "Grok 4.20 Reasoning"),
]
# الحقول اللي تعبر للمزوّد من طلب اللعبة
CHAT_FIELDS = ("model", "messages", "max_tokens", "temperature", "top_p", "response_format")
# مستوى التفكير وموديل الاحتياط ووقت التحويل له: من إعدادات البرنامج (nox_settings).
# الموديلات اللي تفكّر (4.5 / 4.7) تطوّل لما تكبر المكالمة وتعدّي مهلة اللعبة؛
# «low» يقص التفكير للنص تقريباً (قياس 20/10 على 9k توكن: 4.7 من 12–24s لـ6–11s،
# و4.5 لـ5–7s). موديل يرفض الحقل ينحفظ وينرسل بدونه.
# الاحتياط: لو المختار ما رد خلال hedge_after ثانية يروح الطلب له بالتوازي.
# 8s + ~2s للاحتياط يخلّي الرد تحت مهلة اللعبة (15s).

# الصوت: xAI TTS. اللغة = لكنة الشخصية أو إعداد البرنامج (ar-SA/ar-AE/ar-EG)، و«لكنات» لأصوات
# تقرا العربي بلكنة (هندي، بنغالي، إنجليزي) لشخصيات عربي العمالة.
TTS_PREFIX = "grok-tts"
TTS_DEFAULT_LANG = "ar-SA"
TTS_LANGS = ("ar-SA", "ar-AE", "ar-EG")
TTS_ACCENTS = ("hi", "bn", "en")
GROK_VOICES = ("rex", "leo", "sal", "ara", "eve")
DEFAULT_VOICE = "eve"

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8")
    except Exception:
        pass


# البرنامج (nox_app) يسجّل هني عشان يعرض السجل بنافذته — يُنادى من أي خيط
LOG_LISTENERS = []
# وكود تسجيل الدخول (المزوّد، الرابط، الكود) — البرنامج يعرضه بنافذة
LOGIN_LISTENERS = []


def announce_login(provider: str, url: str, code: str):
    log(f"🔑 {provider}: سجّل دخول من المتصفح — الكود: {code} — الرابط: {url}")
    for listener in list(LOGIN_LISTENERS):
        try:
            listener(provider, url, code)
        except Exception:
            pass
    webbrowser.open(url)


def log(line: str):
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {line}", flush=True)
    try:
        os.makedirs(SAVE_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {line}\n")
    except OSError:
        pass
    for listener in list(LOG_LISTENERS):
        try:
            listener(stamp, line)
        except Exception:
            pass


def fix_wav_sizes(wav: bytes) -> bytes:
    """xAI يرجّع WAV بترويسة بث: حجم RIFF والـdata = 0x7FFFFFFF («غير معروف»). نكتب الأحجام
    الحقيقية عشان أي مفكّك WAV يقرا الملف صح."""
    if len(wav) < 12 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        return wav
    out = bytearray(wav)
    i = 12
    while i + 8 <= len(out):
        cid = bytes(out[i:i + 4])
        size = int.from_bytes(out[i + 4:i + 8], "little")
        if cid == b"data":
            out[i + 4:i + 8] = (len(out) - (i + 8)).to_bytes(4, "little")
            out[4:8] = (len(out) - 8).to_bytes(4, "little")
            return bytes(out)
        i += 8 + size + (size & 1)
    return wav


class ClientGone(Exception):
    """اللعبة سكّرت الاتصال قبل الرد."""


class UpstreamError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"{status}: {body[:300]}")
        self.status = status
        self.body = body


# ═══════════════════════════════════════════════════════════════ الحالة

class Bridge:
    """كل شي async يعيش على حلقة وحدة بخيط خلفي — خيوط HTTP ترسل لها."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.store = self.run(self._make_store())
        self.gpt = self.run(self._make_gpt())
        self.local = nox_providers.Local()
        self.client = self.run(self._make_client())
        self._login_task = None
        self._gpt_login_task = None
        self.auto_login = True
        # true = الجسر يفتح المتصفح لحاله لما يحتاج دخول (نافذة الأوامر). البرنامج يطفّيها:
        # الدخول بس لما يضغط المستخدم «ربط»، وغيره تنبيه بالسجل.
        self.prompt_login = True
        self._last_login_hint = 0.0
        self._chat_path = "/chat/completions"   # ينقلب لـ/responses لو انقفل
        self._no_effort = set()                 # موديلات رفضت reasoning_effort

    def run(self, coro, timeout=None):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _make_store(self):
        return Xai.Store(AUTH_PATH)

    async def _make_gpt(self):
        return nox_providers.ChatGPT(GPT_AUTH_PATH)

    async def _make_client(self):
        return httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT)

    # ---------------------------------------------------------------- الدخول
    def need_login(self):
        """طلب وصل وGrok مو مربوط: يفتح الدخول (نافذة الأوامر) أو ينبّه بس (البرنامج)."""
        if self.prompt_login:
            self.start_login()
        elif time.time() - self._last_login_hint > 60:
            self._last_login_hint = time.time()
            log("⚠️ Grok مو مربوط — اربطه من «الحسابات»")

    def start_login(self):
        """يبدأ تسجيل الدخول بالخلفية لو مو شغّال — آمن من أي خيط."""
        if not self.auto_login:
            log("بلا تسجيل دخول (--no-login)")
            return

        def _start():
            if self._login_task is None or self._login_task.done():
                self._login_task = self.loop.create_task(self._login())
        self.loop.call_soon_threadsafe(_start)

    async def _login(self):
        try:
            flow = await Xai.start()
            announce_login("Grok", flow["verification_uri_complete"] or flow["verification_uri"], flow["user_code"])
            tokens = await Xai.poll(flow)
            self.store.store_tokens(tokens, flow["token_endpoint"])
            who = self.store.identity.get("email") or self.store.identity.get("name") or "?"
            log(f"✅ تم تسجيل الدخول ({who})")
        except AuthError as e:
            log(f"❌ تسجيل الدخول فشل: {e} — أعد تشغيل الجسر أو شغّله بـ--login")
        except Exception as e:
            log(f"❌ تسجيل الدخول فشل: {type(e).__name__}: {e}")

    def logout(self):
        self.store.logout()
        log("تم تسجيل الخروج — الدخول الجاي يطلب المتصفح من جديد")

    # ---------------------------------------------------------------- ChatGPT / المحلي
    def start_gpt_login(self):
        async def _run():
            try:
                await self.gpt.login(log, announce_login)
            except AuthError as e:
                log(f"❌ ChatGPT: تسجيل الدخول فشل: {e}")
            except Exception as e:
                log(f"❌ ChatGPT: تسجيل الدخول فشل: {type(e).__name__}: {e}")

        def _start():
            if self._gpt_login_task is None or self._gpt_login_task.done():
                self._gpt_login_task = self.loop.create_task(_run())
        self.loop.call_soon_threadsafe(_start)

    def gpt_logout(self):
        self.gpt.store.logout()
        log("ChatGPT: تم تسجيل الخروج")

    async def all_models(self) -> list:
        """موديلات كل الحسابات المربوطة: Grok بدون بادئة، والباقي بـchatgpt: / local:."""
        grok = await self.models() if self.store.logged_in else []
        local = []
        if nox_settings.bridge_settings().get("local_enabled"):   # المحلي بس لو ربطه المستخدم
            await self.local.probe(self.client)
            local = self.local.models()
        return grok + self.gpt.models() + local

    # ---------------------------------------------------------------- xAI
    def _headers(self, access: str) -> dict:
        # Content-Type يحطه httpx حسب الجسم (json أو multipart)
        return {
            "Authorization": f"Bearer {access}",
            "User-Agent": nox_auth.USER_AGENT,
        }

    async def _send(self, method: str, path: str, payload=None, **body) -> httpx.Response:
        """طلب لـxAI بتوكن صالح — 401 مرة = تجديد وإعادة.
        payload = JSON؛ أو data/files بـbody لطلبات multipart."""
        if payload is not None:
            body["json"] = payload
        for attempt in range(2):
            access = await self.store.ensure_access()
            r = await self.client.request(method, f"{API_BASE}{path}",
                                          headers=self._headers(access), **body)
            if r.status_code != 401 or attempt:
                return r
            await self.store.refresh()
        return r

    async def models(self) -> list:
        try:
            r = await self._send("GET", "/models")
            if r.status_code == 200:
                ids = [m.get("id") for m in r.json().get("data") or [] if m.get("id")]
                ids = [i for i in ids if not any(x in i for x in ("image", "imagine", "video"))]
                if ids:
                    return [{"id": i, "name": i} for i in sorted(ids, reverse=True)]
        except (AuthError, httpx.HTTPError):
            pass
        return [{"id": i, "name": n} for i, n in FALLBACK_MODELS]

    async def chat(self, body: dict):
        """يرجّع (الرد, الموديل اللي رد). لو الموديل المختار ما رد خلال HEDGE_AFTER
        ثانية، نفس الطلب يروح لـFALLBACK_MODEL بالتوازي وأول رد ناجح يفوز —
        مهلة اللعبة (25s) ما تنتظر xAI لو علّق (4.7 وصل 41–62s بلا تفكير يذكر)."""
        cfg = nox_settings.bridge_settings()
        fallback, hedge_after = cfg["fallback_model"], float(cfg["hedge_after"])
        payload = {k: body[k] for k in CHAT_FIELDS if body.get(k) is not None}
        payload["model"] = payload.get("model") or DEFAULT_MODEL
        payload["stream"] = False
        model = payload["model"]
        primary = asyncio.ensure_future(self._chat_once(dict(payload)))
        tasks = {primary: model}
        try:
            done, _ = await asyncio.wait({primary}, timeout=hedge_after)
            if done and not primary.exception():
                return primary.result(), model
            if not fallback or fallback == model:
                return await primary, model
            why = f"فشل ({primary.exception()})" if done else f"ما رد خلال {hedge_after:g}s"
            log(f"⚡ {model} {why} — أرسلت نفس الطلب لـ{fallback}")
            backup = asyncio.ensure_future(self._chat_once(dict(payload, model=fallback)))
            tasks[backup] = fallback
            if done:
                return await backup, fallback
            pending = {primary, backup}
            last_error = None
            while pending:
                finished, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for t in finished:
                    if t.exception() is None:
                        return t.result(), tasks[t]
                    last_error = t.exception()
            raise last_error
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()

    async def _chat_once(self, payload: dict) -> dict:
        model = payload["model"]
        effort = nox_settings.bridge_settings()["reasoning_effort"]
        provider = nox_providers.provider_of(model)
        if provider != "grok":
            try:
                if provider == "chatgpt":
                    return await self.gpt.chat(self.client, payload, effort)
                return await self.local.chat(self.client, payload, effort)
            except ProviderError as e:
                raise UpstreamError(e.status, e.body)
        if effort and "non-reasoning" not in model and model not in self._no_effort:
            payload["reasoning_effort"] = effort
        if self._chat_path == "/chat/completions":
            r = await self._send("POST", "/chat/completions", payload)
            if r.status_code == 400 and "reasoning_effort" in payload and "reason" in r.text.lower():
                log(f"{model} ما يقبل reasoning_effort — أرسله بدونه من الحين")
                self._no_effort.add(model)
                payload.pop("reasoning_effort")
                r = await self._send("POST", "/chat/completions", payload)
            fmt = payload.get("response_format") or {}
            if r.status_code == 400 and fmt.get("type") == "json_schema":
                # المخطط الصارم مرفوض؟ اللعبة تكتب المخطط بالتعليمات أصلاً — json_object يكفي
                log("json_schema انرفض — أعيد بـjson_object")
                payload["response_format"] = {"type": "json_object"}
                r = await self._send("POST", "/chat/completions", payload)
            # 404 «الموديل مو موجود» مو معناها إن النقطة مقفلة — لا تقلب الجسر كله
            if r.status_code in (404, 405) and "model" not in r.text.lower():
                log("chat/completions غير متاح — أتحول لـresponses")
                self._chat_path = "/responses"
            elif r.status_code != 200:
                raise UpstreamError(r.status_code, r.text)
            else:
                return r.json()
        return await self._chat_via_responses(payload)

    async def speech(self, body: dict):
        """صوت xAI. body = {model: grok-tts-<لغة>, input, voice}. يرجّع (status, content_type, wav)."""
        model = str(body.get("model") or "")
        lang = model[len(TTS_PREFIX):].lstrip("-") or TTS_DEFAULT_LANG
        if lang not in TTS_LANGS + TTS_ACCENTS:
            lang = TTS_DEFAULT_LANG
        voice = str(body.get("voice") or "").strip().lower()
        req = {
            "text": body.get("input") or "",
            "voice_id": voice if voice in GROK_VOICES else DEFAULT_VOICE,
            "language": lang,
            # معدّل أصوات اللعبة 24k — نطلبه من البداية
            "output_format": {"codec": "wav", "sample_rate": 24000},
        }
        r = await self._send("POST", "/tts", req)
        if r.status_code != 200:
            raise UpstreamError(r.status_code, r.text)
        return 200, "audio/wav", fix_wav_sizes(r.content)

    async def stt_pcm16(self, pcm: bytes, rate: int, lang: str) -> str:
        """تفريغ صوت PCM16 أحادي خام بـxAI STT. يرجّع النص."""
        header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack(
            "<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm))
        r = await self._send("POST", "/stt", data={"language": lang} if lang else {},
                             files={"file": ("speech.wav", header + pcm, "audio/wav")})
        if r.status_code != 200:
            raise UpstreamError(r.status_code, r.text)
        return (r.json().get("text") or "").strip()

    async def _chat_via_responses(self, payload: dict) -> dict:
        req = {
            "model": payload["model"],
            "input": [{"role": m.get("role", "user"), "content": m.get("content") or ""}
                      for m in payload["messages"]],
            "store": False,
        }
        for src, dst in (("max_tokens", "max_output_tokens"), ("temperature", "temperature"),
                         ("top_p", "top_p")):
            if src in payload:
                req[dst] = payload[src]
        if "reasoning_effort" in payload:
            req["reasoning"] = {"effort": payload["reasoning_effort"]}
        fmt = payload.get("response_format") or {}
        if fmt.get("type") == "json_schema":
            js = fmt.get("json_schema") or {}
            req["text"] = {"format": {"type": "json_schema", "name": js.get("name", "reply"),
                                      "schema": js.get("schema", {}), "strict": js.get("strict", False)}}
        elif fmt.get("type") == "json_object":
            req["text"] = {"format": {"type": "json_object"}}
        r = await self._send("POST", "/responses", req)
        if r.status_code != 200:
            raise UpstreamError(r.status_code, r.text)
        js = r.json()
        text = "".join(c.get("text", "") for item in js.get("output") or [] if item.get("type") == "message"
                       for c in item.get("content") or [] if c.get("type") in ("output_text", "text"))
        usage = js.get("usage") or {}
        return {
            "id": js.get("id", "resp"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": js.get("model", payload["model"]),
            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                         "finish_reason": "length" if js.get("status") == "incomplete" else "stop"}],
            "usage": {"prompt_tokens": usage.get("input_tokens", 0),
                      "completion_tokens": usage.get("output_tokens", 0),
                      "total_tokens": usage.get("total_tokens", 0)},
        }


BRIDGE: Bridge = None  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════════ HTTP

class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # اللعبة تقطع الاتصال بعد ما تستلم الرد — مو خطأ، بلا traceback
        if isinstance(sys.exc_info()[1], (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def _error(message: str, code: str = "bridge_error") -> dict:
    return {"error": {"message": message, "type": code, "code": code}}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "NoxBridge/2"

    def log_message(self, fmt, *args):   # نسجّل بأنفسنا — بلا ضجيج لكل طلب
        pass

    def _reply(self, status: int, data: dict):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/health"):
            store = BRIDGE.store
            self._reply(200, {"ok": True, "logged_in": store.logged_in,
                              "user": store.identity.get("email") or store.identity.get("name")})
        elif path == "/v1/models":
            self._reply(200, {"object": "list", "data": BRIDGE.run(BRIDGE.models(), 30)})
        else:
            self._reply(404, _error("not found", "not_found"))

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            return body if isinstance(body, dict) else None
        except (ValueError, OSError):
            return None

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/nox/v1/tts":
            self._game_tts()
            return
        if path == "/nox/deepgram/listen":
            self._game_stt()
            return
        if path == "/nox/v1/translate":
            body = self._read_json() or {}
            try:
                out = BRIDGE.run(nox_translate.translate(BRIDGE, body.get("texts") or [], nox_settings.game_dir(), log), 120)
            except Exception as e:
                log(f"✗ ترجمة الشاشات: {type(e).__name__}: {e}")
                self._reply(502, _error(f"{type(e).__name__}: {e}", "upstream"))
                return
            self._reply(200, {"translations": out})
            return
        if path != "/nox/v1/chat/completions":
            self._reply(404, _error("not found", "not_found"))
            return
        body = self._read_json()
        if body is None:
            self._reply(400, _error("طلب غير صالح", "invalid_request"))
            return
        self._game_chat(body)

    def _game_tts(self):
        """صوت شخصية عربية (NoxGame.Voice داخل اللعبة). الرد WAV (PCM16 24kHz) بـbase64."""
        started = time.time()
        body = self._read_json()
        if not body or not str(body.get("text") or "").strip():
            self._reply(400, _error("طلب صوت بلا نص", "invalid_request"))
            return
        gd = nox_settings.game_dir()
        voice = nox_voices.pick(body.get("voice") or "", gd)
        # لكنة الشخصية (مصري، هندي…) لو عرفناها من النص، وإلا إعداد النطق العام
        dialect, accent = nox_voices.speaker_of(body["text"], gd)
        lang = accent or nox_settings.bridge_settings().get("voice_lang") or TTS_DEFAULT_LANG
        try:
            status, _, wav = BRIDGE.run(BRIDGE.speech(
                {"model": f"{TTS_PREFIX}-{lang}", "input": body["text"], "voice": voice}), 60)
        except NotLoggedIn:
            BRIDGE.need_login()
            self._reply(401, _error("Grok مو مربوط", "not_logged_in"))
            return
        except Exception as e:
            log(f"✗ صوت {voice} {type(e).__name__}: {e}")
            self._reply(502, _error(f"{type(e).__name__}: {e}", "upstream"))
            return
        log(f"✓ صوت {voice} ({lang}{' · ' + dialect if dialect else ''}) {time.time() - started:.1f}s · {len(wav) // 1024}KB")
        raw = base64.b64encode(wav)
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=ascii")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _game_stt(self):
        """تفريغ المايك: اللعبة تحسب إنها تكلّم Deepgram — صوت PCM16 16kHz خام، والرد بشكل
        Deepgram (results.channels[0].alternatives[0].transcript)."""
        started = time.time()
        try:
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        except (ValueError, OSError):
            self._reply(400, _error("طلب غير صالح", "invalid_request"))
            return
        query = dict(p.split("=", 1) for p in (self.path.split("?", 1)[1] if "?" in self.path else "").split("&") if "=" in p)
        lang = (query.get("language") or "ar").split("-")[0]
        try:
            text = BRIDGE.run(BRIDGE.stt_pcm16(raw, 16000, lang), 60)
        except NotLoggedIn:
            BRIDGE.need_login()
            self._reply(401, _error("Grok مو مربوط", "not_logged_in"))
            return
        except Exception as e:
            log(f"✗ تفريغ {type(e).__name__}: {e}")
            self._reply(502, _error(f"{type(e).__name__}: {e}", "upstream"))
            return
        log(f"✓ تفريغ Grok {time.time() - started:.1f}s · {len(raw) // 1024}KB → {len(text)} حرف")
        self._reply(200, {"results": {"channels": [{"alternatives": [{"transcript": text, "confidence": 0.95}]}]}})

    def _game_chat(self, body: dict):
        """طلب اللعبة نفسها (خيار «OpenRouter بمفتاحك» محوّل لهني). الموديل اللي
        ترسله وهمي — نحط الموديل المختار، ونضيف اللهجة والصعوبة لردود الشخصيات."""
        body["model"] = nox_settings.chat_model() or DEFAULT_MODEL
        b = nox_settings.bridge_settings()
        try:
            note = nox_prompts.apply(body, b.get("difficulty") or "normal")
        except Exception as e:   # التعليمات إضافة — لا تطيّح الطلب
            note = ""
            log(f"⚠️ ما قدرت أضيف التعليمات: {type(e).__name__}: {e}")
        if note:
            log(f"🎭 رد شخصية ({note})")
        dialect = accent = ""
        if nox_prompts.is_caller_turn(body):
            try:
                dialect, accent = nox_prompts.dialect_for(body["messages"]), nox_prompts.accent_for(body["messages"])
            except Exception:
                dialect = accent = ""
        # نطق الرد لاحقاً بلكنة الشخصية (طلب الصوت يجي بالنص بس)
        self._chat(body, on_result=(lambda result: nox_voices.remember_reply(result, dialect, accent)) if dialect else None)

    def _chat(self, body: dict, on_result=None):
        if not isinstance(body.get("messages"), list):
            self._reply(400, _error("الطلب بلا messages", "invalid_request"))
            return
        started = time.time()
        model = body.get("model") or DEFAULT_MODEL
        try:
            result, answered = self._await_unless_gone(BRIDGE.chat(body), UPSTREAM_TIMEOUT + 15)
        except ClientGone:
            log(f"↩ {model} اللعبة ألغت الطلب بعد {time.time() - started:.1f}s — وقّفت انتظار المزوّد")
            nox_stats.event(model, "cancelled")
            self.close_connection = True
            return
        except NotLoggedIn:
            BRIDGE.need_login()
            log("طلب وصل بلا تسجيل دخول")
            nox_stats.event(model, "failed")
            self._reply(401, _error("Grok مو مربوط — اربطه من «الحسابات» بالبرنامج", "not_logged_in"))
            return
        except UpstreamError as e:
            log(f"✗ {model} {e.status} ({time.time() - started:.1f}s): {e.body[:200]}")
            nox_stats.event(model, "failed")
            self._reply(e.status if 400 <= e.status < 600 else 502, _error(f"{model} {e.status}: {e.body[:300]}", "upstream"))
            return
        except Exception as e:
            log(f"✗ {model} {type(e).__name__}: {e}")
            nox_stats.event(model, "failed")
            self._reply(502, _error(f"NoxBridge: {type(e).__name__}: {e}", "bridge_error"))
            return
        elapsed = time.time() - started
        nox_stats.reply(answered, elapsed)
        if answered != model:
            nox_stats.event(model, "hedged")
        usage = result.get("usage") or {}
        thought = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        log(f"✓ {answered}{' ⚡احتياط' if answered != model else ''} {elapsed:.1f}s · "
            f"{usage.get('prompt_tokens', 0)}→{usage.get('completion_tokens', 0)} توكن"
            + (f" (تفكير {thought})" if thought else ""))
        if on_result:
            try:
                on_result(result)
            except Exception as e:
                log(f"⚠️ {type(e).__name__}: {e}")
        self._reply(200, result)

    def _await_unless_gone(self, coro, timeout: float):
        """ينتظر الرد، ولو اللعبة سكّرت الاتصال (ألغت الدور) يلغي الطلب عند xAI —
        بدونها الطلب الملغي يظل شاغل والطلب الجاي يتأخر وراه."""
        future = asyncio.run_coroutine_threadsafe(coro, BRIDGE.loop)
        deadline = time.time() + timeout
        while True:
            try:
                return future.result(0.5)
            except concurrent.futures.TimeoutError:
                pass
            if self._client_gone():
                future.cancel()
                raise ClientGone()
            if time.time() > deadline:
                future.cancel()
                raise TimeoutError(f"ما وصل رد خلال {timeout:g}s")

    def _client_gone(self) -> bool:
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            # اللعبة ما ترسل طلب ثاني على نفس الاتصال قبل الرد — قابل للقراءة = انسكّر
            return bool(readable) and self.connection.recv(1, socket.MSG_PEEK) == b""
        except OSError:
            return True


def main():
    global BRIDGE
    args = set(sys.argv[1:])
    BRIDGE = Bridge()
    BRIDGE.auto_login = "--no-login" not in args
    if "--logout" in args:
        BRIDGE.logout()
        return
    try:
        server = start_server(force_login="--login" in args)
    except OSError:
        sys.exit(1)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def start_server(force_login: bool = False, login_on_start: bool = True) -> "Server":
    """يفتح المنفذ ويرجّع السيرفر (المنادي يشغّل serve_forever). BRIDGE لازم يكون جاهز.
    login_on_start=False (البرنامج): ما يفتح المتصفح لحاله لو مو مربوط.
    OSError = المنفذ مشغول (جسر ثاني شغّال)."""
    try:
        server = Server((HOST, PORT), Handler)
    except OSError as e:
        log(f"❌ ما قدرت أفتح المنفذ {PORT}: {e} — يمكن الجسر شغّال بنافذة ثانية")
        raise
    log(f"الجسر شغّال على http://{HOST}:{PORT}/v1 — خلّه شغّال وأنت تلعب")
    if force_login or (login_on_start and not BRIDGE.store.logged_in):
        BRIDGE.start_login()
    elif not BRIDGE.store.logged_in:
        log("Grok مو مربوط — اربطه من «الحسابات» لما تبي")
    else:
        who = BRIDGE.store.identity.get("email") or BRIDGE.store.identity.get("name") or "?"
        log(f"مسجّل دخول ({who})")
    return server


def init_bridge(auto_login: bool = True, prompt_login: bool = True) -> Bridge:
    global BRIDGE
    BRIDGE = Bridge()
    BRIDGE.auto_login = auto_login
    BRIDGE.prompt_login = prompt_login
    return BRIDGE


if __name__ == "__main__":
    main()
