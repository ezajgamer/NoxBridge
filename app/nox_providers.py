# -*- coding: utf-8 -*-
"""
مزوّدين المحادثة غير Grok — الجسر يوجّه حسب بادئة الموديل المختار بالبرنامج:

- «chatgpt:<id>» ← اشتراك ChatGPT عبر واجهة Codex (chatgpt.com/backend-api/codex)، بدخول
  device code (nox_auth.OpenAI) وتوكنات بـSave\\openai-auth.json.
  الواجهة Responses بالبث فقط، و`store: false` إجباري.
- «local:<id>» ← سيرفر LM Studio المحلي بصيغة OpenAI: LOCAL_LLM_BASE_URL لو محدد، وإلا أول واحد
  يرد من 127.0.0.1:1234 (افتراضي LM Studio) و1235.
- بدون بادئة ← Grok (xAI) — بالجسر نفسه.

الصوت والتفريغ يظلون على Grok.
"""

import os
import json
import time

import httpx

from nox_auth import AuthError, NotLoggedIn, OpenAI

GPT_PREFIX = "chatgpt:"
LOCAL_PREFIX = "local:"

GPT_API = os.environ.get("OPENAI_CODEX_BASE_URL", "https://chatgpt.com/backend-api/codex")
# موديلات Codex باشتراك ChatGPT (learn.chatgpt.com/docs/models ٠٧/٠٩/٢٠٢٦):
# 5.5 لكل الخطط، عائلة 5.6 لـPro وفوق.
GPT_MODELS = ["gpt-5.5", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"]

LOCAL_APIS = ([os.environ["LOCAL_LLM_BASE_URL"].rstrip("/")] if os.environ.get("LOCAL_LLM_BASE_URL")
              else ["http://127.0.0.1:1234/v1", "http://127.0.0.1:1235/v1"])


class ProviderError(Exception):
    """خطأ من مزوّد — الجسر يحوّله لرد خطأ للعبة (ويجرّب الاحتياط)."""

    def __init__(self, status: int, body: str):
        super().__init__(f"{status}: {body[:300]}")
        self.status = status
        self.body = body


def provider_of(model: str) -> str:
    if model.startswith(GPT_PREFIX):
        return "chatgpt"
    if model.startswith(LOCAL_PREFIX):
        return "local"
    return "grok"


def _split_messages(messages: list):
    """رسائل chat ← (instructions، input) لواجهة Responses."""
    system = [str(m.get("content") or "") for m in messages if m.get("role") in ("system", "developer")]
    rest = [{"role": m.get("role") if m.get("role") in ("user", "assistant") else "user",
             "content": str(m.get("content") or "")}
            for m in messages if m.get("role") not in ("system", "developer")]
    return "\n\n".join(s for s in system if s) or "You are a helpful assistant.", rest


def _completion(model: str, text: str, usage: dict, incomplete: bool) -> dict:
    """رد بصيغة chat.completion — اللي تفهمه اللعبة."""
    details = usage.get("output_tokens_details") or {}
    return {
        "id": f"nox-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                     "finish_reason": "length" if incomplete else "stop"}],
        "usage": {"prompt_tokens": usage.get("input_tokens", 0),
                  "completion_tokens": usage.get("output_tokens", 0),
                  "total_tokens": usage.get("total_tokens", 0),
                  "completion_tokens_details": {"reasoning_tokens": details.get("reasoning_tokens", 0)}},
    }


# ═══════════════════════════════════════════════════════════════ ChatGPT

class ChatGPT:
    name = "ChatGPT"

    def __init__(self, auth_path: str):
        self.store = OpenAI.Store(auth_path)
        self._dropped = set()   # حقول رفضها السيرفر — ما نرسلها مرة ثانية

    def models(self) -> list:
        return [{"id": GPT_PREFIX + m, "name": m} for m in GPT_MODELS] if self.store.logged_in else []

    async def login(self, log, on_code):
        flow = await OpenAI.start()
        url = flow["verification_uri_complete"] or flow["verification_uri"]
        on_code(self.name, url, flow["user_code"])
        tokens = await OpenAI.poll(flow)
        self.store.store_tokens(tokens, flow["token_endpoint"])
        who = self.store.identity.get("email") or self.store.identity.get("name") or "?"
        log(f"✅ {self.name}: تم تسجيل الدخول ({who})")

    def _headers(self, access: str) -> dict:
        return {
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "NoxBridge",
            "originator": OpenAI.ORIGINATOR,
            "OpenAI-Beta": "responses=experimental",
            "chatgpt-account-id": self.store.account_id,
        }

    def _payload(self, payload: dict, effort: str) -> dict:
        instructions, items = _split_messages(payload.get("messages") or [])
        req = {
            "model": payload["model"][len(GPT_PREFIX):],
            "instructions": instructions,
            "input": items,
            "store": False,
            "stream": True,
        }
        if effort and "reasoning" not in self._dropped:
            req["reasoning"] = {"effort": effort}
        fmt = payload.get("response_format") or {}
        if "text" not in self._dropped:
            if fmt.get("type") == "json_schema":
                js = fmt.get("json_schema") or {}
                req["text"] = {"format": {"type": "json_schema", "name": js.get("name", "reply"),
                                          "schema": js.get("schema", {}), "strict": js.get("strict", False)}}
            elif fmt.get("type") == "json_object":
                req["text"] = {"format": {"type": "json_object"}}
        return req

    async def chat(self, client: httpx.AsyncClient, payload: dict, effort: str) -> dict:
        if not self.store.logged_in:
            raise ProviderError(401, "ChatGPT مو مربوط — اربطه من صفحة الحسابات")
        req = self._payload(payload, effort)
        for attempt in range(3):
            try:
                access = await self.store.ensure_access()
            except NotLoggedIn:
                raise ProviderError(401, "ChatGPT مو مربوط — اربطه من صفحة الحسابات")
            except AuthError as e:
                raise ProviderError(401, f"ChatGPT: {e}")
            status, body, result = await self._stream(client, access, req)
            if status == 200:
                return result
            if status == 401 and attempt == 0:
                await self.store.refresh()
                continue
            low = body.lower()
            # حقل ما يقبله الموديل؟ نشيله ونعيد (ونتذكر)
            if status == 400 and "reasoning" in req and "reasoning" in low:
                self._dropped.add("reasoning")
                req.pop("reasoning")
                continue
            if status == 400 and "text" in req and ("format" in low or "schema" in low):
                self._dropped.add("text")
                req.pop("text")
                continue
            raise ProviderError(status, body)
        raise ProviderError(status, body)

    async def _stream(self, client, access, req):
        """بث SSE: نجمّع النص لين response.completed. يرجّع (status, body, result)."""
        texts, deltas = [], []
        async with client.stream("POST", f"{GPT_API}/responses", headers=self._headers(access), json=req) as r:
            if r.status_code != 200:
                return r.status_code, (await r.aread()).decode("utf-8", "replace"), None
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    ev = json.loads(data)
                except ValueError:
                    continue
                kind = ev.get("type")
                if kind == "response.output_item.done":
                    item = ev.get("item") or {}
                    if item.get("type") == "message":
                        texts.extend(c.get("text", "") for c in item.get("content") or []
                                     if c.get("type") in ("output_text", "text"))
                elif kind == "response.output_text.delta" and isinstance(ev.get("delta"), str):
                    deltas.append(ev["delta"])
                elif kind in ("response.completed", "response.incomplete"):
                    resp = ev.get("response") or {}
                    text = "".join(texts) or "".join(deltas)
                    return 200, "", _completion(req["model"], text, resp.get("usage") or {},
                                                kind == "response.incomplete")
                elif kind == "response.failed":
                    err = (ev.get("response") or {}).get("error") or {}
                    return 502, err.get("message") or "الرد فشل", None
                elif kind == "error":
                    err = ev.get("error") if isinstance(ev.get("error"), dict) else ev
                    return 502, err.get("message") or "خطأ بالبث", None
        return 502, "انقطع البث قبل اكتمال الرد", None


# ═══════════════════════════════════════════════════════════════ المحلي

class Local:
    name = "المحلي (LM Studio)"

    def __init__(self):
        self.api = LOCAL_APIS[0]
        self.reachable = False
        self.model_ids = []
        self.loaded_keys = {}   # المحمّل على الكرت الحين (يتحدث مع probe)

    async def probe(self, client: httpx.AsyncClient) -> bool:
        """السيرفر شغّال؟ + الموديلات المتاحة (بدون موديلات التضمين) + المحمّل منها."""
        self.reachable, self.model_ids = False, []
        for api in [self.api] + [a for a in LOCAL_APIS if a != self.api]:
            try:
                r = await client.get(f"{api}/models", timeout=2.0)
                if r.status_code != 200:
                    continue
                ids = [m.get("id") for m in (r.json().get("data") or []) if m.get("id")]
                self.api, self.reachable = api, True
                self.model_ids = [i for i in ids if "embed" not in i.lower()]
                break
            except (httpx.HTTPError, ValueError):
                continue
        self.loaded_keys = await self.loaded(client) if self.reachable else {}
        return self.reachable

    def models(self) -> list:
        return [{"id": LOCAL_PREFIX + m, "name": m} for m in self.model_ids]

    # ---------------------------------------------------------------- التحميل
    # واجهة LM Studio الأصلية (/api/v1 — مو /v1 المتوافقة مع OpenAI)
    @property
    def _native(self) -> str:
        return self.api[:-3] if self.api.endswith("/v1") else self.api

    async def loaded(self, client: httpx.AsyncClient) -> dict:
        """{مفتاح الموديل: [instance_id…]} للموديلات المحمّلة على الكرت الحين."""
        try:
            r = await client.get(f"{self._native}/api/v1/models", timeout=3.0)
            out = {}
            for m in (r.json().get("models") or []) if r.status_code == 200 else []:
                ids = [i.get("id") or i.get("instance_id") for i in m.get("loaded_instances") or [] if isinstance(i, dict)]
                if m.get("loaded_instances"):
                    out[m.get("key")] = [i for i in ids if i] or [m.get("key")]
            return out
        except (httpx.HTTPError, ValueError):
            return {}

    async def load(self, client: httpx.AsyncClient, key: str) -> dict:
        """يحمّل موديل على الكرت (يطوّل — ١٠ لـ٦٠ ثانية حسب الحجم)."""
        try:
            r = await client.post(f"{self._native}/api/v1/models/load", json={"model": key}, timeout=300.0)
        except httpx.HTTPError as e:
            return {"ok": False, "error": f"LM Studio ما رد: {type(e).__name__}"}
        if r.status_code == 404:
            return {"ok": False, "error": f"LM Studio ما لقى الموديل {key}"}
        if r.status_code != 200:
            return {"ok": False, "error": f"LM Studio {r.status_code}: {r.text[:200]}"}
        js = r.json() if r.content else {}
        return {"ok": True, "seconds": js.get("load_time_seconds")}

    async def unload_all(self, client: httpx.AsyncClient) -> dict:
        """يفرّغ كل الموديلات المحمّلة (أي برنامج يستخدم LM Studio يتأثر)."""
        done, errors = [], []
        for key, instances in (await self.loaded(client)).items():
            for inst in instances:
                try:
                    r = await client.post(f"{self._native}/api/v1/models/unload", json={"instance_id": inst}, timeout=60.0)
                    (done if r.status_code == 200 else errors).append(key)
                except httpx.HTTPError:
                    errors.append(key)
        return {"ok": not errors, "unloaded": done, "error": ("ما قدرت أفرّغ: " + "، ".join(errors)) if errors else None}

    async def chat(self, client: httpx.AsyncClient, payload: dict, effort: str) -> dict:
        req = dict(payload)
        req["model"] = payload["model"][len(LOCAL_PREFIX):]
        req.pop("reasoning_effort", None)
        if not effort:
            req["reasoning_effort"] = "none"   # «بدون تفكير» — مجرّب على LM Studio (0 توكن تفكير)
        try:
            r = await client.post(f"{self.api}/chat/completions", json=req)
        except httpx.ConnectError:
            raise ProviderError(503, "السيرفر المحلي طافي — افتح LM Studio وشغّل Local Server")
        # المخطط مرفوض؟ json_object، وإلا بدون — اللعبة تكتب المخطط بالتعليمات أصلاً
        if r.status_code == 400 and (req.get("response_format") or {}).get("type") == "json_schema":
            req["response_format"] = {"type": "json_object"}
            r = await client.post(f"{self.api}/chat/completions", json=req)
        if r.status_code == 400 and "response_format" in req:
            req.pop("response_format")
            r = await client.post(f"{self.api}/chat/completions", json=req)
        if r.status_code != 200:
            raise ProviderError(r.status_code, r.text)
        js = r.json()
        js["model"] = req["model"]
        return js
