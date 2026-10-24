# NoxBridge

مود عربي للعبة **Scam With Your Friends**: الشخصيات اللي تتصل فيك ترد بالذكاء الاصطناعي من **اشتراكك**
(Grok أو ChatGPT) أو من موديل على كرتك، وتتكلم عربي بصوت Grok، بلهجاتها.

> **English:** NoxBridge is an Arabic mod for the game *Scam With Your Friends*. A local desktop app routes the
> game's AI caller conversations, Arabic voice and screen translation to the player's own Grok / ChatGPT
> subscription (OAuth device login — no API keys) or a local LM Studio model, and adds 20 Arabic-speaking
> callers with their own dialects. It uses the game's official options ("OpenRouter with your key") plus a
> small patch applied from local backups, and restores the game with one button. Not affiliated with the
> game's developers.

## المميزات

- **ردود الشخصيات** من اشتراك Grok أو ChatGPT، أو موديل محلي (LM Studio) — مع موديل احتياط لو تأخر الرد.
- **صوت عربي** من Grok، ونطق على حسب الشخصية (إماراتي، سعودي، مصري، ولكنة هندية/بنغالية لعربي العمالة).
- **٢٠ شخصية** بلهجاتها: كويتيين، وسعوديين، وإماراتيين، ومصريين، وسودانيين، ويمنيين، وهندي، وباكستاني،
  وبنغالي، وفلبينية — وطابور المكالمات يصير شخصياتنا بس.
- **ترجمة الشاشات** الإنجليزية داخل اللعبة (شاشات الكمبيوتر وغيرها) للعربي.
- **مهلة رد الشخصية** تتغير من البرنامج.
- **زر واحد يرجّع اللعبة أصلية** (ملفاتها وإعداداتها وطابور مكالماتها).

## التشغيل

1. نزّل `NoxBridge-<الإصدار>.zip` من [Releases](../../releases) وفكّه بأي مكان.
2. افتح `NoxBridge.exe` ← «الحسابات» ← اربط Grok (يفتح المتصفح وتوافق).
3. سكّر اللعبة، وبـ«الرئيسية» اضغط «إعادة التركيب».
4. اضغط «شغّل اللعبة»، وخلّ البرنامج مفتوح وأنت تلعب.

بعد أي تحديث للعبة من ستيم: سكّرها واضغط «إعادة التركيب» مرة ثانية.

## الخصوصية

- البرنامج يشتغل على جهازك بس (`127.0.0.1`).
- تسجيل الدخول بالمتصفح عند المزوّد نفسه (OAuth device code)، والتوكنات تنحفظ بمجلد `Save` جنب البرنامج —
  ما تطلع لأي مكان غير المزوّد، ولا تشاركها مع أحد.
- الكود ما فيه أي مفاتيح سرية — بس معرّفات «العميل العام» حق xAI وOpenAI (نفس أدواتهم الرسمية).

## البناء من الكود

المتطلبات: ويندوز، Python 3.13، .NET SDK 8.

```powershell
py -m pip install -r app\requirements.txt pyinstaller
py tools\make_icon.py
powershell -ExecutionPolicy Bypass -File tools\build-release.ps1
```

الناتج: `release\NoxBridge\` و`release\NoxBridge-<الإصدار>.zip`. البناء ما يحتاج ملفات اللعبة — `NoxGame.dll`
يلقى أنواع اللعبة وUnity وقت التشغيل.

| المجلد | الوصف |
|---|---|
| `app/` | البرنامج (PySide6) والجسر المحلي (`nox_bridge.py`) والدخول (`nox_auth.py`) |
| `game/` | `NoxGame.dll` — مكتبة داخل اللعبة: الصوت العربي وترجمة الشاشات |
| `patcher/` | `NoxPatcher2.exe` — يركّب ويرجّع (Mono.Cecil، من النسخ الأصلية `.orig`) |
| `data/` | `nox-callers.json` — الشخصيات (يولّدها `tools/make_callers.py`) |
| `tools/` | البناء، والأيقونة، و`refcheck` (يفحص إن كل دالة يستخدمها `NoxGame` موجودة بمكتبات اللعبة) |

## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by
[SignPath Foundation](https://signpath.org/).

- Committers and reviewers: [ezajgamer](https://github.com/ezajgamer)
- Approvers: [ezajgamer](https://github.com/ezajgamer)

Release binaries (`NoxBridge.exe`, `NoxPatcher2.exe`, `NoxGame.dll`) are built by
[GitHub Actions](.github/workflows/build.yml) from this repository only; each signing request is approved
by an approver.

## Privacy policy

This program will not transfer any information to other networked systems unless specifically requested by
the user or the person installing or operating it:

- The app talks to the game on this computer only (`127.0.0.1`).
- When the user links an account, the conversation, voice text and screen text the game sends are forwarded
  to the provider the user chose (xAI for Grok, OpenAI for ChatGPT) under the user's own account, or to the
  user's local LM Studio server. Nothing is sent to the authors of NoxBridge.
- Login tokens are stored in the `Save` folder next to the app and are only sent to the provider that issued them.

**Install / uninstall:** «إعادة التركيب» (Reinstall) patches the game from local backups and changes the
game's AI / speech options and call queue; «رجّع اللعبة أصلية» (Restore game) undoes all of it. Deleting the
NoxBridge folder removes the app.

## الرخصة

[MIT](LICENSE)
