# -*- coding: utf-8 -*-
"""
تسجيل الدخول باشتراك المستخدم (OAuth 2.0 Device Authorization Grant — RFC 8628).

المستخدم يفتح رابط بمتصفحه ويوافق، والبرنامج يستلم توكن ويحفظه بـSave\\ على جهازه بس.
ما فيه أي secret بالكود: الـCLIENT_ID أدناه معرّفات «عميل عام» (public client) نفس اللي
تستخدمها أدوات المزوّدين الرسمية — ما تكشف شي عن المستخدم.

- xAI (Grok): الاكتشاف من auth.x.ai/.well-known/openid-configuration ثم device code قياسي.
- OpenAI (ChatGPT): device code حق Codex — الموافقة ترجّع authorization_code + PKCE نبادله بتوكن.

شكل ملف التوكن (Save\\<provider>-auth.json):
    {access, refresh, expires_ms, token_endpoint, identity{email,name,sub}, obtained_at}
"""

import os
import json
import time
import base64
import asyncio
from urllib.parse import urlparse

import httpx

TIMEOUT = 30.0
REFRESH_BEFORE_S = 120          # نجدّد قبل الانتهاء بدقيقتين
USER_AGENT = "NoxBridge"


class AuthError(Exception):
    """فشل الدخول أو التجديد — الرسالة جاهزة للعرض."""


class NotLoggedIn(AuthError):
    pass


# ═══════════════════════════════════════════════════════════════ أدوات

def jwt_claims(token) -> dict:
    """حمولة JWT للعرض بس (بدون تحقق توقيع)."""
    try:
        part = str(token).split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return data if isinstance(data, dict) else {}
    except (IndexError, ValueError):
        return {}


def _json(r) -> dict:
    try:
        data = r.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _error_of(r) -> str:
    data = _json(r)
    err = data.get("error")
    if isinstance(err, dict):
        err = err.get("code") or err.get("type") or err.get("message")
    return str(err or data.get("error_description") or r.text[:200] or f"HTTP {r.status_code}")


def _tokens(data: dict, need_refresh: bool) -> dict:
    access = data.get("access_token")
    if not isinstance(access, str) or not access:
        raise AuthError("رد التوكن بدون access_token")
    if need_refresh and not data.get("refresh_token"):
        raise AuthError("رد التوكن بدون refresh_token — سجّل من جديد")
    out = {"access": access, "refresh": data.get("refresh_token"), "id_token": data.get("id_token")}
    life = data.get("expires_in")
    out["expires_ms"] = int((time.time() + life) * 1000) if isinstance(life, (int, float)) and life > 0 else None
    return out


# ═══════════════════════════════════════════════════════════════ المخزن

class TokenStore:
    """توكنات مزوّد واحد بملف: تحميل، حفظ، خروج، وتجديد تلقائي قبل الانتهاء."""

    provider = ""
    expired_errors = ("invalid_grant", "invalid_refresh_token", "refresh_token_expired",
                      "refresh_token_invalidated", "refresh_token_reused")

    def __init__(self, path: str):
        self.path = path
        self._lock = asyncio.Lock()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._data = data if isinstance(data, dict) else None
        except (OSError, ValueError):
            self._data = None

    @property
    def logged_in(self) -> bool:
        return bool(self._data and self._data.get("refresh"))

    @property
    def identity(self) -> dict:
        return (self._data or {}).get("identity") or {}

    def _write(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def identity_of(self, tokens: dict) -> dict:
        claims = jwt_claims(tokens.get("id_token") or tokens["access"])
        return {k: claims[k] for k in ("email", "name", "sub") if k in claims}

    def store_tokens(self, tokens: dict, token_endpoint: str):
        self._data = {
            "access": tokens["access"],
            "refresh": tokens.get("refresh"),
            "expires_ms": tokens.get("expires_ms"),
            "token_endpoint": token_endpoint,
            "identity": self.identity_of(tokens),
            "obtained_at": int(time.time()),
        }
        self._write()

    def logout(self):
        self._data = None
        try:
            os.remove(self.path)
        except OSError:
            pass

    # ── التجديد (يحدده المزوّد) ──
    def refresh_request(self, refresh: str) -> tuple:
        """(headers, form)"""
        raise NotImplementedError

    async def token_endpoint(self) -> str:
        endpoint = (self._data or {}).get("token_endpoint")
        if not endpoint:
            raise AuthError(f"ملف دخول {self.provider} ناقص — سجّل من جديد")
        return endpoint

    async def refresh(self):
        """يجدّد التوكن الحين (ينادى لحاله قبل الانتهاء، أو بعد 401)."""
        token = (self._data or {}).get("refresh")
        if not token:
            raise NotLoggedIn(f"ما فيه دخول {self.provider}")
        endpoint = await self.token_endpoint()
        headers, form = self.refresh_request(token)
        last = "فشل التجديد"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for attempt in range(3):
                r = await client.post(endpoint, headers=headers, data=form)
                if r.status_code == 200:
                    tokens = _tokens(_json(r), need_refresh=False)
                    if self._data is None:      # خرج المستخدم وهو ينتظر الرد — لا نرجّع الجلسة
                        raise NotLoggedIn("سجّلت خروج")
                    self._data["access"] = tokens["access"]
                    self._data["expires_ms"] = tokens["expires_ms"]
                    if tokens.get("refresh"):
                        self._data["refresh"] = tokens["refresh"]
                    self._write()
                    return
                err = _error_of(r)
                if err in self.expired_errors:
                    self.logout()
                    raise NotLoggedIn(f"انتهى الدخول عند {self.provider} — سجّل من جديد")
                last = f"التجديد فشل ({r.status_code}): {err}"
                await asyncio.sleep(0.3 * (attempt + 1))
        raise AuthError(last)

    async def ensure_access(self) -> str:
        """access صالح — يجدّد لو قرب ينتهي."""
        async with self._lock:
            if not self._data:
                raise NotLoggedIn(f"ما فيه دخول {self.provider}")
            expires = self._data.get("expires_ms")
            if expires is None or expires / 1000 - time.time() < REFRESH_BEFORE_S:
                await self.refresh()
            if not self._data:
                raise NotLoggedIn(f"ما فيه دخول {self.provider}")
            return self._data["access"]


# ═══════════════════════════════════════════════════════════════ xAI (Grok)

class Xai:
    CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"     # عميل xAI العام (device code)
    SCOPE = "openid profile email offline_access grok-cli:access api:access"
    DISCOVERY = "https://auth.x.ai/.well-known/openid-configuration"
    DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

    @staticmethod
    def headers() -> dict:
        return {"Accept": "application/json", "User-Agent": USER_AGENT}

    @staticmethod
    def trusted(url: str) -> str:
        host = urlparse(url).hostname or ""
        if not url.startswith("https://") or not (host == "x.ai" or host.endswith(".x.ai")):
            raise AuthError(f"عنوان مو تابع لـxAI: {url}")
        return url

    @classmethod
    async def endpoints(cls) -> tuple:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(cls.DISCOVERY, headers=cls.headers())
        if r.status_code != 200:
            raise AuthError(f"xAI ما رد على الاكتشاف ({r.status_code})")
        doc = _json(r)
        device, token = doc.get("device_authorization_endpoint"), doc.get("token_endpoint")
        if not isinstance(device, str) or not isinstance(token, str):
            raise AuthError("وثيقة xAI ناقصة")
        return cls.trusted(device), cls.trusted(token)

    @classmethod
    async def start(cls) -> dict:
        """يرجّع {user_code, verification_uri, verification_uri_complete, ...} للعرض والاستطلاع."""
        device, token = await cls.endpoints()
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(device, headers=cls.headers(), data={"client_id": cls.CLIENT_ID, "scope": cls.SCOPE})
        if r.status_code != 200:
            raise AuthError(f"طلب الكود فشل ({r.status_code}): {_error_of(r)}")
        data = _json(r)
        if not all(data.get(k) for k in ("device_code", "user_code", "verification_uri")):
            raise AuthError("رد الكود ناقص")
        complete = data.get("verification_uri_complete")
        return {
            "device_code": data["device_code"], "user_code": data["user_code"],
            "verification_uri": cls.trusted(data["verification_uri"]),
            "verification_uri_complete": cls.trusted(complete) if complete else None,
            "expires_in": int(data.get("expires_in") or 300), "interval": int(data.get("interval") or 5),
            "token_endpoint": token,
        }

    @classmethod
    async def poll(cls, flow: dict) -> dict:
        """يستطلع لين يوافق المستخدم. يرجّع التوكنات."""
        deadline, interval = time.time() + flow["expires_in"], max(1, flow["interval"])
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            while time.time() < deadline:
                r = await client.post(flow["token_endpoint"], headers=cls.headers(), data={
                    "grant_type": cls.DEVICE_GRANT, "client_id": cls.CLIENT_ID, "device_code": flow["device_code"]})
                if r.status_code == 200:
                    return _tokens(_json(r), need_refresh=True)
                err = _error_of(r)
                if err == "authorization_pending":
                    await asyncio.sleep(interval)
                elif err == "slow_down":
                    interval += 5
                    await asyncio.sleep(interval)
                elif err in ("access_denied", "authorization_denied"):
                    raise AuthError("رفضت الدخول من المتصفح")
                elif err == "expired_token":
                    raise AuthError("الكود انتهى — سجّل من جديد")
                else:
                    raise AuthError(f"الدخول فشل ({r.status_code}): {err}")
        raise AuthError("انتهت مهلة الدخول — سجّل من جديد")

    class Store(TokenStore):
        provider = "xAI"

        def refresh_request(self, refresh: str) -> tuple:
            return Xai.headers(), {"grant_type": "refresh_token", "client_id": Xai.CLIENT_ID, "refresh_token": refresh}

        async def token_endpoint(self) -> str:
            endpoint = (self._data or {}).get("token_endpoint")
            if not endpoint:
                _, endpoint = await Xai.endpoints()
            return Xai.trusted(endpoint)


# ═══════════════════════════════════════════════════════════════ OpenAI (ChatGPT)

class OpenAI:
    CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"              # عميل Codex العام (device code)
    BASE = "https://auth.openai.com"
    USERCODE = BASE + "/api/accounts/deviceauth/usercode"
    DEVICE_TOKEN = BASE + "/api/accounts/deviceauth/token"
    TOKEN = BASE + "/oauth/token"
    VERIFY = BASE + "/codex/device"
    CALLBACK = BASE + "/deviceauth/callback"
    ORIGINATOR = "NoxBridge"
    AUTH_CLAIM = "https://api.openai.com/auth"
    PROFILE_CLAIM = "https://api.openai.com/profile"

    @classmethod
    def headers(cls, content_type="application/json") -> dict:
        return {"Content-Type": content_type, "Accept": "application/json",
                "originator": cls.ORIGINATOR, "User-Agent": USER_AGENT}

    @classmethod
    def account_id(cls, access) -> str:
        claim = jwt_claims(access).get(cls.AUTH_CLAIM)
        value = claim.get("chatgpt_account_id") if isinstance(claim, dict) else None
        return value if isinstance(value, str) else ""

    @classmethod
    async def start(cls) -> dict:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(cls.USERCODE, headers=cls.headers(), json={"client_id": cls.CLIENT_ID})
        if r.status_code != 200:
            raise AuthError(f"طلب الكود فشل ({r.status_code}): {_error_of(r)}")
        data = _json(r)
        device_id, code = data.get("device_auth_id"), data.get("user_code") or data.get("usercode")
        if not device_id or not code:
            raise AuthError("رد الكود ناقص")
        interval = data.get("interval")
        return {
            "device_auth_id": str(device_id), "user_code": str(code),
            "verification_uri": cls.VERIFY, "verification_uri_complete": None,
            "expires_in": 15 * 60, "interval": int(interval) if isinstance(interval, (int, float)) and interval > 0 else 5,
            "token_endpoint": cls.TOKEN,
        }

    @classmethod
    async def poll(cls, flow: dict) -> dict:
        deadline, interval = time.time() + flow["expires_in"], max(1, int(flow["interval"]))
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            while time.time() < deadline:
                try:
                    r = await client.post(cls.DEVICE_TOKEN, headers=cls.headers(),
                                          json={"device_auth_id": flow["device_auth_id"], "user_code": flow["user_code"]})
                except httpx.HTTPError:
                    await asyncio.sleep(interval)
                    continue
                if r.status_code in (403, 404):          # لسا ما وافق
                    await asyncio.sleep(interval)
                    continue
                if r.status_code != 200:
                    raise AuthError(f"الدخول فشل ({r.status_code}): {_error_of(r)}")
                data = _json(r)
                code, verifier = data.get("authorization_code"), data.get("code_verifier")
                if not code or not verifier:
                    raise AuthError("رد الموافقة ناقص")
                r = await client.post(cls.TOKEN, headers=cls.headers("application/x-www-form-urlencoded"), data={
                    "grant_type": "authorization_code", "code": code, "redirect_uri": cls.CALLBACK,
                    "client_id": cls.CLIENT_ID, "code_verifier": verifier})
                if r.status_code != 200:
                    raise AuthError(f"تبادل التوكن فشل ({r.status_code}): {_error_of(r)}")
                tokens = _tokens(_json(r), need_refresh=True)
                if not cls.account_id(tokens["access"]):
                    raise AuthError("الحساب ما عليه اشتراك ChatGPT يخدم Codex")
                return tokens
        raise AuthError("انتهت مهلة الدخول — سجّل من جديد")

    class Store(TokenStore):
        provider = "OpenAI"

        def refresh_request(self, refresh: str) -> tuple:
            return (OpenAI.headers("application/x-www-form-urlencoded"),
                    {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": OpenAI.CLIENT_ID})

        async def token_endpoint(self) -> str:
            return OpenAI.TOKEN

        def identity_of(self, tokens: dict) -> dict:
            ident = super().identity_of(tokens)
            if not ident.get("email"):
                profile = jwt_claims(tokens["access"]).get(OpenAI.PROFILE_CLAIM)
                if isinstance(profile, dict) and isinstance(profile.get("email"), str):
                    ident["email"] = profile["email"]
            return ident

        @property
        def account_id(self) -> str:
            return OpenAI.account_id((self._data or {}).get("access") or "")
