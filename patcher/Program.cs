// NoxPatcher2 — يركّب NoxBridge 2 على لعبة Scam With Your Friends.
//
// اللعبة فيها خيارات رسمية نستغلها بدل ما نكتب مود كامل:
//   • «OpenRouter بمفتاحك» (Host Settings) — طلبات الذكاء الاصطناعي لرابط ثابت ← نحوّله للجسر.
//   • «Deepgram» لتفريغ المايك (إصدارات اللعبة قبل 24/10/2026) — رابط ثابت ← نحوّله للجسر (Grok يفرّغ).
//   • العربي ولغة المكالمة — من اللعبة نفسها.
// الأشياء اللي تحتاج كود داخل اللعبة (مكتبة NoxGame.dll حقنا): صوت الشخصيات العربي (خطافين بموديل
// MOSS المحلي) وترجمة الشاشات الإنجليزية (خطاف بالنص المرسوم). ومعها: مهلة الرد، وشخصياتنا وطابور المكالمات.
//
//   NoxPatcher2 install [--game <dir>] [--data <dir>] [--game-dll <NoxGame.dll>] [--translate on|off]
//                       [--seconds 15] [--voice grok|game] [--stt grok|game] [--settings <local.json>]
//   NoxPatcher2 restore [--game <dir>] [--settings <local.json>]
using System.Diagnostics;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using Mono.Cecil;
using Mono.Cecil.Cil;

Console.OutputEncoding = Encoding.UTF8;
try
{
    var o = Options.Parse(args);
    var p = new Patcher(o);
    if (o.Command == "restore") p.Restore(); else p.Install();
    return 0;
}
catch (Exception ex)
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.WriteLine("❌ " + ex.Message);
    Console.ResetColor();
    return 1;
}

sealed class Options
{
    public string Command = "install";
    public string GameDir;        // مجلد اللعبة — البرنامج يلقاه من ستيم ويرسله
    public string DataDir;
    public string GameDll;
    public bool Translate = true;
    public string SettingsPath;   // للاختبار: نسخة من إعدادات اللعبة بدل الحقيقية
    public double Seconds = 15;   // ١٥ = الأصل حق اللعبة
    public string Voice = "grok";
    public string Stt = "grok";

    public static Options Parse(string[] args)
    {
        var o = new Options();
        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "install": case "restore": o.Command = args[i]; break;
                case "--game": o.GameDir = args[++i]; break;
                case "--data": o.DataDir = args[++i]; break;
                case "--game-dll": o.GameDll = args[++i]; break;
                case "--translate": o.Translate = args[++i] != "off"; break;
                case "--settings": o.SettingsPath = args[++i]; break;
                case "--seconds": o.Seconds = double.Parse(args[++i], System.Globalization.CultureInfo.InvariantCulture); break;
                case "--voice": o.Voice = args[++i] == "game" ? "game" : "grok"; break;
                case "--stt": o.Stt = args[++i] == "game" ? "game" : "grok"; break;
                default: throw new ArgumentException("خيار غير معروف: " + args[i]);
            }
        }
        if (string.IsNullOrEmpty(o.GameDir) || !File.Exists(Path.Combine(o.GameDir, "Scam With Your Friends.exe")))
            throw new ArgumentException("حدد مجلد اللعبة الصحيح: --game <المجلد اللي فيه Scam With Your Friends.exe>");
        return o;
    }
}

sealed class Patcher
{
    const string Bridge = "http://127.0.0.1:8797/nox/";
    const string ChatUrl = "https://openrouter.ai/api/v1/chat/completions";
    const string DeepgramUrl = "https://api.deepgram.com/v1/listen?model=nova-3&language=";
    const string Marker = "NoxBridge2";           // المفاتيح الوهمية بإعدادات اللعبة = علامة إن الإعداد حقنا
    const string CallersFile = "nox-callers.json";
    const string LegacyCallersFile = "nox-kuwait.json";   // اسمه بالإصدارات الأولى
    const string GameAssembly = "NoxGame";

    const string AC = "Assembly-CSharp.dll", SA = "ScriptsAssDef.dll", MT = "Kolkata.MossTtsNano.dll", UI = "UnityEngine.UIElementsModule.dll";
    static readonly string[] Targets = { AC, SA, MT, UI };

    // مودات سابقة تعدّل نفس الملفات (GroqBridge/NoxBridge.dll) — ترجع أصلية قبل التركيب
    static readonly string[] V1Targets = { AC, SA, MT, UI };
    static readonly string[] V1Bridges = { "GroqBridge", "NoxBridge" };

    // TypeInfoResolver: قيم نصية بالـJsonArray (QueuedCallers) تحتاجه وقت الكتابة على .NET Framework
    static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = true, Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        TypeInfoResolver = new System.Text.Json.Serialization.Metadata.DefaultJsonTypeInfoResolver(),
    };

    // ‎.NET Framework ما فيه File.Move(overwrite)
    static void MoveOver(string src, string dst)
    {
        if (File.Exists(dst)) File.Delete(dst);
        File.Move(src, dst);
    }

    readonly Options o;
    readonly string game, managed, assets, backups, settingsPath;

    public Patcher(Options o)
    {
        this.o = o;
        game = Path.GetFullPath(o.GameDir);
        managed = Path.Combine(game, "Scam With Your Friends_Data", "Managed");
        assets = Path.Combine(game, "Scam With Your Friends_Data", "StreamingAssets");
        backups = Path.Combine(game, "NoxBridge-Backups");
        // إعدادات اللعبة (MetaSave): %USERPROFILE%\AppData\LocalLow\Jatater Worldwide\Scam With Your Friends\MetaSave\local.json
        settingsPath = o.SettingsPath ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            "AppData", "LocalLow", "Jatater Worldwide", "Scam With Your Friends", "MetaSave", "local.json");
        if (!File.Exists(Path.Combine(managed, AC)))
            throw new Exception("ما لقيت اللعبة بـ: " + game + " (مرّر المجلد بـ--game)");
        if (Process.GetProcessesByName("Scam With Your Friends").Length > 0)
            throw new Exception("سكّر اللعبة أول — ملفاتها وإعداداتها مقفولة وهي شغّالة");
    }

    static void Log(string s) => Console.WriteLine(s);

    JsonObject ReadInfo()
    {
        string path = Path.Combine(game, "NoxBridge.json");
        try { return File.Exists(path) ? JsonNode.Parse(File.ReadAllText(path, Encoding.UTF8)) as JsonObject : null; }
        catch (Exception) { return null; }
    }

    // ───────────────────────── التركيب ─────────────────────────
    public void Install()
    {
        Directory.CreateDirectory(backups);
        RemoveV1();
        foreach (var name in Targets) EnsureOriginal(name);
        CopyGameLibrary();
        PatchFiles();
        EditSettings(EnableGameOptions);
        CopyCallers();
        CleanLegacyQueue();
        string infoPath = Path.Combine(game, "NoxBridge.json");
        var queue = OnlyOurCallers(ReadInfo());
        File.WriteAllText(infoPath, new JsonObject
        {
            ["Version"] = 2,
            ["TurnBudgetSeconds"] = o.Seconds,
            ["Voice"] = o.Voice,
            ["Stt"] = o.Stt,
            ["Translate"] = o.Translate,
            ["InstalledAt"] = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss"),
            // الطابور: اللي أضفناها (ما نرجّع وحدة شالها اللاعب) + طابور اللعبة الأصلي للإرجاع
            ["QueuedCallers"] = queue["QueuedCallers"]?.DeepClone(),
            ["OriginalQueue"] = queue["OriginalQueue"]?.DeepClone(),
            ["OriginalRandomCommunity"] = queue["OriginalRandomCommunity"]?.DeepClone(),
        }.ToJsonString(Json), new UTF8Encoding(false));
        Log("✅ NoxBridge 2 مركّب. افتح NoxBridge وشغّل اللعبة منه.");
    }

    public void Restore()
    {
        foreach (var name in Targets)
        {
            string path = Path.Combine(managed, name);
            if (!File.Exists(path + ".orig") || !IsPatched(path)) continue;
            CheckSameBuild(path, path + ".orig");
            File.Copy(path + ".orig", path, overwrite: true);
            Log("• رجّعت " + name);
        }
        string lib = Path.Combine(managed, GameAssembly + ".dll");
        if (File.Exists(lib)) { File.Delete(lib); Log("• شلت NoxGame.dll"); }
        string callers = Path.Combine(assets, "kolkata-json", "caller-identities", CallersFile);
        if (File.Exists(callers)) { File.Delete(callers); Log("• شلت شخصيات NoxBridge"); }
        string legacyCallers = Path.Combine(assets, "kolkata-json", "caller-identities", LegacyCallersFile);
        if (File.Exists(legacyCallers)) File.Delete(legacyCallers);
        RestoreQueue(ReadInfo());
        EditSettings(DisableGameOptions);
        string info = Path.Combine(game, "NoxBridge.json");
        if (File.Exists(info)) File.Delete(info);
        Log("✅ اللعبة رجعت أصلية.");
    }

    // ───────────────────────── النسخ الأصلية ─────────────────────────
    static bool ReferencesAny(string path, string[] names)
    {
        using var m = ModuleDefinition.ReadModule(path, new ReaderParameters { InMemory = true });
        return m.AssemblyReferences.Any(r => names.Contains(r.Name));
    }

    // مرقّع = فيه رابط الجسر (الملفين اللي غيّرنا روابطهم) أو يشير لمكتبة NoxGame (ملف الصوت والنص)
    static bool IsPatched(string path) =>
        File.ReadAllBytes(path).AsSpan().IndexOf(Encoding.Unicode.GetBytes(Bridge)) >= 0
        || ReferencesAny(path, new[] { GameAssembly });

    static void CheckSameBuild(string path, string orig)
    {
        using var a = ModuleDefinition.ReadModule(path, new ReaderParameters { InMemory = true });
        using var b = ModuleDefinition.ReadModule(orig, new ReaderParameters { InMemory = true });
        if (a.Mvid != b.Mvid)
            throw new Exception(Path.GetFileName(path) + ": النسخة الأصلية من تحديث ثاني — سوّ Verify من ستيم وعيد التركيب");
    }

    void EnsureOriginal(string name)
    {
        string path = Path.Combine(managed, name), orig = path + ".orig";
        if (IsPatched(path))
        {
            if (!File.Exists(orig)) throw new Exception(name + " معدّل وما له نسخة أصلية — سوّ Verify من ستيم");
            CheckSameBuild(path, orig);
            return;
        }
        File.Copy(path, orig, overwrite: true);   // ملف ستيم نظيف = الأصل الجديد
        Log("• نسخة أصلية جديدة: " + name);
    }

    // النسخة الأولى (خطافات + DLL) ترجع أصلية، والـDLL حقها ينشال
    void RemoveV1()
    {
        foreach (var name in V1Targets)
        {
            string path = Path.Combine(managed, name), orig = path + ".orig";
            if (!File.Exists(path) || !ReferencesAny(path, V1Bridges)) continue;
            if (!File.Exists(orig)) throw new Exception($"{name} معدّل من النسخة الأولى وما له نسخة أصلية — سوّ Verify من ستيم");
            CheckSameBuild(path, orig);
            File.Copy(orig, path, overwrite: true);
            Log("• رجّعت " + name + " (من النسخة الأولى)");
        }
        foreach (var dll in new[] { "NoxBridge.dll", "GroqBridge.dll" })
        {
            string path = Path.Combine(managed, dll);
            if (!File.Exists(path)) continue;
            MoveOver(path, Path.Combine(backups, $"{Path.GetFileNameWithoutExtension(dll)}-{DateTime.Now:yyyyMMdd-HHmmss}.dll"));
            Log("• شلت " + dll + " (احتياط بـNoxBridge-Backups)");
        }
    }

    void CopyGameLibrary()
    {
        string src = o.GameDll ?? Path.Combine(AppContext.BaseDirectory, GameAssembly + ".dll");
        if (!File.Exists(src)) throw new Exception("ما لقيت " + src + " — ابنِ game أول");
        File.Copy(src, Path.Combine(managed, GameAssembly + ".dll"), overwrite: true);
        Log("• نسخت NoxGame.dll (الصوت العربي وترجمة الشاشات)");
    }

    // ───────────────────────── التعديلات ─────────────────────────
    bool deepgram;   // اللعبة فيها رابط Deepgram (قبل تحديث 24/10)

    void PatchFiles()
    {
        var resolver = new DefaultAssemblyResolver();
        resolver.AddSearchDirectory(managed);
        var read = new ReaderParameters { AssemblyResolver = resolver, InMemory = true };
        var modules = Targets.ToDictionary(n => n, n => ModuleDefinition.ReadModule(Path.Combine(managed, n + ".orig"), read));
        var lib = ModuleDefinition.ReadModule(Path.Combine(managed, GameAssembly + ".dll"), read);
        try
        {
            ReplaceString(modules[AC], ChatUrl, Bridge + "v1/chat/completions", "رابط الذكاء الاصطناعي ← الجسر");
            ExtendTimeout(modules[AC]);
            // تحديث 24/10 شال Deepgram من اللعبة (التفريغ صار محلي بس: Whisper/Moonshine) — نتخطاه
            deepgram = AllInstructions(modules[SA]).Any(i => i.OpCode == OpCodes.Ldstr && (string)i.Operand == DeepgramUrl);
            if (deepgram)
                ReplaceString(modules[SA], DeepgramUrl, Bridge + "deepgram/listen?model=nova-3&language=", "رابط تفريغ المايك (Deepgram) ← الجسر");
            else
                Log("⚠️ تفريغ المايك: هالإصدار من اللعبة ما فيه Deepgram — يبقى تفريغ اللعبة المحلي");
            HookVoice(modules[MT], lib);
            HookText(modules[UI], lib);

            foreach (var (name, mod) in modules.Select(kv => (kv.Key, kv.Value)))
            {
                Guid mvid = mod.Mvid;
                string tmp = Path.Combine(managed, name + ".nox-tmp");
                mod.Write(tmp);
                using var check = ModuleDefinition.ReadModule(tmp, new ReaderParameters { InMemory = true });
                if (check.Mvid != mvid) throw new Exception(name + ": المعرّف (Mvid) تغيّر بعد الكتابة — ما طبّقت شي");
            }
        }
        catch
        {
            foreach (var name in Targets) File.Delete(Path.Combine(managed, name + ".nox-tmp"));
            throw;
        }
        finally
        {
            foreach (var mod in modules.Values) mod.Dispose();
            lib.Dispose();
            resolver.Dispose();   // يمسك ملفات اللعبة مفتوحة — لازم قبل التبديل
        }
        foreach (var name in Targets)
            MoveOver(Path.Combine(managed, name + ".nox-tmp"), Path.Combine(managed, name));
    }

    static IEnumerable<Instruction> AllInstructions(ModuleDefinition mod) =>
        mod.GetTypes().SelectMany(t => t.Methods).Where(m => m.HasBody).SelectMany(m => m.Body.Instructions);

    static void ReplaceString(ModuleDefinition mod, string from, string to, string what)
    {
        var hits = AllInstructions(mod).Where(i => i.OpCode == OpCodes.Ldstr && (string)i.Operand == from).ToList();
        if (hits.Count != 1) throw new Exception($"{what}: النص مو بمكان واحد ({hits.Count}) — تحديث للعبة غيّر الكود");
        hits[0].Operand = to;
        Log("• " + what);
    }

    // مهلة رد الشخصية: CallerAiPipeline — ldc.r8 N ← TimeSpan.FromSeconds ← CancelAfter
    void ExtendTimeout(ModuleDefinition mod)
    {
        var type = mod.GetType("CallerAiPipeline") ?? throw new Exception("ما لقيت CallerAiPipeline — تحديث للعبة غيّر الكود");
        var sites = new[] { type }.Concat(type.NestedTypes).SelectMany(t => t.Methods).Where(m => m.HasBody)
            .SelectMany(m => m.Body.Instructions)
            .Where(i => i.OpCode == OpCodes.Ldc_R8
                && (i.Next?.Operand as MethodReference)?.FullName == "System.TimeSpan System.TimeSpan::FromSeconds(System.Double)"
                && (i.Next.Next?.Operand as MethodReference)?.FullName.Contains("CancellationTokenSource::CancelAfter") == true)
            .ToList();
        if (sites.Count != 1) throw new Exception($"مهلة الرد مو بمكان واحد ({sites.Count}) — تحديث للعبة غيّر الكود");
        double old = (double)sites[0].Operand;
        sites[0].Operand = o.Seconds;
        var field = type.Fields.FirstOrDefault(f => f.Name == "TurnBudgetSeconds");
        if (field != null) field.Constant = o.Seconds;
        Log($"• مهلة رد الشخصية: {old} ← {o.Seconds} ثانية");
    }

    // موديل الصوت المحلي (MOSS): البنّاء ما يحمّل الموديل لو صوت Grok شغّال، وSynthesize يجيب الصوت من الجسر
    static void HookVoice(ModuleDefinition mod, ModuleDefinition voice)
    {
        var runtime = mod.GetType("Kolkata.MossTtsNano.MossOnnxRuntime") ?? throw new Exception("ما لقيت MossOnnxRuntime — تحديث للعبة غيّر الكود");
        var api = voice.GetType("NoxGame.Voice");
        var skip = mod.ImportReference(api.Methods.Single(m => m.Name == "SkipModel"));
        var synth = mod.ImportReference(api.Methods.Single(m => m.Name == "Synthesize"));

        // ١) البنّاء: بعد نداء object::.ctor مباشرة ← if (SkipModel()) return;
        var ctors = runtime.Methods.Where(m => m.IsConstructor && !m.IsStatic).ToList();
        if (ctors.Count != 1) throw new Exception($"بنّاء MossOnnxRuntime مو واحد ({ctors.Count}) — تحديث للعبة غيّر الكود");
        var ctor = ctors[0];
        var baseCall = ctor.Body.Instructions.FirstOrDefault(i => i.OpCode == OpCodes.Call
            && (i.Operand as MethodReference)?.FullName == "System.Void System.Object::.ctor()")
            ?? throw new Exception("بنّاء MossOnnxRuntime بشكل غير متوقع — تحديث للعبة غيّر الكود");
        var il = ctor.Body.GetILProcessor();
        var resume = baseCall.Next;
        il.InsertAfter(baseCall, Instruction.Create(OpCodes.Call, skip));
        il.InsertAfter(baseCall.Next, Instruction.Create(OpCodes.Brfalse, resume));
        il.InsertAfter(baseCall.Next.Next, Instruction.Create(OpCodes.Ret));

        // ٢) Synthesize(text, voicePath, emit, ct): r = NoxGame.Voice.Synthesize(...); if (r != -1) return r;
        var method = runtime.Methods.Where(m => m.Name == "Synthesize" && m.Parameters.Count == 4).ToList();
        if (method.Count != 1) throw new Exception($"Synthesize مو واحد ({method.Count}) — تحديث للعبة غيّر الكود");
        var sm = method[0];
        var first = sm.Body.Instructions[0];
        var orig = Instruction.Create(OpCodes.Pop);
        il = sm.Body.GetILProcessor();
        foreach (var ins in new[]
        {
            Instruction.Create(OpCodes.Ldarg, sm.Parameters[0]), Instruction.Create(OpCodes.Ldarg, sm.Parameters[1]),
            Instruction.Create(OpCodes.Ldarg, sm.Parameters[2]), Instruction.Create(OpCodes.Ldarg, sm.Parameters[3]),
            Instruction.Create(OpCodes.Call, synth),
            Instruction.Create(OpCodes.Dup), Instruction.Create(OpCodes.Ldc_I4_M1), Instruction.Create(OpCodes.Beq, orig),
            Instruction.Create(OpCodes.Ret), orig,
        })
            il.InsertBefore(first, ins);
        Log("• صوت الشخصيات العربي ← Grok (خطافين بموديل MOSS)");
    }

    // ترجمة الشاشات: أول TextElement.SetRenderedText(value) ← value = NoxGame.Text.Render(this, value)
    // (النص المرسوم بس — النص اللي تقراه اللعبة بمنطقها ما يتغيّر)
    static void HookText(ModuleDefinition mod, ModuleDefinition lib)
    {
        var type = mod.GetType("UnityEngine.UIElements.TextElement") ?? throw new Exception("ما لقيت TextElement — تحديث للعبة غيّر يونتي");
        var targets = type.Methods.Where(m => m.Name == "SetRenderedText" && m.Parameters.Count == 1).ToList();
        if (targets.Count != 1) throw new Exception($"SetRenderedText مو واحد ({targets.Count}) — تحديث للعبة غيّر يونتي");
        var method = targets[0];
        var render = mod.ImportReference(lib.GetType("NoxGame.Text").Methods.Single(m => m.Name == "Render"));
        var il = method.Body.GetILProcessor();
        var first = method.Body.Instructions[0];
        foreach (var ins in new[]
        {
            Instruction.Create(OpCodes.Ldarg_0), Instruction.Create(OpCodes.Ldarg_1),
            Instruction.Create(OpCodes.Call, render), Instruction.Create(OpCodes.Starg, method.Parameters[0]),
        })
            il.InsertBefore(first, ins);
        Log("• ترجمة الشاشات الإنجليزية (خطاف بالنص المرسوم)");
    }

    // ───────────────────────── إعدادات اللعبة ─────────────────────────
    // «OpenRouter بمفتاحك» (Backend=1 + مفتاح + موديل) و«Deepgram» للتفريغ. المفاتيح والموديل
    // ما لهم معنى عندنا — الجسر يستخدم الموديل المختار بالبرنامج، وGrok للتفريغ.
    void EnableGameOptions(JsonObject values)
    {
        values["HostAI.Backend"] = 1;
        values["HostAI.OpenRouterKey"] = Marker;
        values["HostAI.OpenRouterModel"] = new JsonObject
        {
            ["Id"] = "noxbridge/game",
            ["Name"] = "NoxBridge",
            ["SupportedParameters"] = new JsonArray("temperature", "top_p", "max_tokens", "response_format", "structured_outputs"),
            ["MaxCompletionTokens"] = 8192,
        }.ToJsonString();
        Log("• فعّلت «OpenRouter بمفتاحك» بإعدادات اللعبة (يروح للجسر)");
        if (o.Stt == "grok" && deepgram)
        {
            values["SpeechRecognition.Provider"] = "Deepgram";
            values["SpeechRecognition.DeepgramKey"] = Marker;
            Log("• تفريغ المايك: Deepgram بإعدادات اللعبة (يروح للجسر ← Grok)");
        }
        else
        {
            RemoveOurStt(values);
        }
    }

    void DisableGameOptions(JsonObject values)
    {
        if ((values["HostAI.OpenRouterKey"] as JsonValue)?.ToString() == Marker)
        {
            values.Remove("HostAI.Backend");
            values.Remove("HostAI.OpenRouterKey");
            values.Remove("HostAI.OpenRouterModel");
            Log("• رجّعت إعداد الذكاء الاصطناعي حق اللعبة للأصلي");
        }
        RemoveOurStt(values);
    }

    static void RemoveOurStt(JsonObject values)
    {
        if ((values["SpeechRecognition.DeepgramKey"] as JsonValue)?.ToString() != Marker) return;   // مو حقنا
        values.Remove("SpeechRecognition.DeepgramKey");
        values.Remove("SpeechRecognition.Provider");
        Log("• رجّعت تفريغ المايك حق اللعبة للأصلي");
    }

    void EditSettings(Action<JsonObject> edit)
    {
        if (!File.Exists(settingsPath))
        {
            Log("⚠️ ما لقيت إعدادات اللعبة (شغّلها مرة وسكّرها) — فعّل «OpenRouter بمفتاحك» و«Deepgram» يدوي");
            return;
        }
        var root = JsonNode.Parse(File.ReadAllText(settingsPath, Encoding.UTF8)) as JsonObject
                   ?? throw new Exception("ملف إعدادات اللعبة تالف: " + settingsPath);
        var values = root["values"] as JsonObject ?? throw new Exception("ملف إعدادات اللعبة بشكل غير متوقع");
        string before = root.ToJsonString();
        edit(values);
        if (root.ToJsonString() == before) return;
        Directory.CreateDirectory(backups);
        File.Copy(settingsPath, Path.Combine(backups, $"local-{DateTime.Now:yyyyMMdd-HHmmss}.json"), overwrite: true);
        string tmp = settingsPath + ".nox-tmp";
        File.WriteAllText(tmp, root.ToJsonString(Json), new UTF8Encoding(false));
        MoveOver(tmp, settingsPath);
    }

    // ───────────────────────── الشخصيات ─────────────────────────
    void CopyCallers()
    {
        string src = Path.Combine(o.DataDir ?? Path.Combine(AppContext.BaseDirectory, "data"), CallersFile);
        if (!File.Exists(src)) { Log("⚠️ ما لقيت " + CallersFile); return; }
        string dir = Path.Combine(assets, "kolkata-json", "caller-identities"), dst = Path.Combine(dir, CallersFile);
        string legacy = Path.Combine(dir, LegacyCallersFile);
        if (File.Exists(legacy)) File.Delete(legacy);
        if (File.Exists(dst) && File.ReadAllBytes(dst).AsSpan().SequenceEqual(File.ReadAllBytes(src))) return;
        Directory.CreateDirectory(dir);
        File.Copy(src, dst, overwrite: true);
        Log("• أضفت شخصيات NoxBridge");
    }

    // طابور المكالمات اليومي: نص JSON بمفتاح «DailyCallers» داخل MetaSave (local.json).
    // daily-callers.json القديم تقراه اللعبة بس لو المفتاح ناقص. اللعبة تعبّي الطابور مرة وحدة
    // (defaultsInitialized)، فاحنا نخلّيه شخصياتنا بس، ونحفظ الأصلي بـNoxBridge.json يرجع بالإرجاع.
    const string OurPrefix = "nox_";
    const string QueueKey = "DailyCallers";
    string QueuePath => Path.Combine(Path.GetDirectoryName(Path.GetDirectoryName(settingsPath)), "daily-callers.json");

    static bool IsOurs(string id) => id != null && id.StartsWith(OurPrefix, StringComparison.OrdinalIgnoreCase);
    static List<string> Strings(JsonArray a) => (a ?? new JsonArray()).Select(n => n?.ToString()).Where(s => !string.IsNullOrEmpty(s)).ToList();

    static JsonObject NewQueue() => new JsonObject
    {
        ["enabled"] = true, ["randomCommunityCallers"] = false, ["randomCommunityOnly"] = false,
        ["autoLocalizedCommunityVoices"] = false, ["letPlayersModifyQueue"] = true, ["randomSources"] = 2,
        ["callerIds"] = new JsonArray(), ["lastCallerId"] = null, ["day"] = 0, ["defaultsInitialized"] = true,
    };

    /// يخلّي الطابور شخصياتنا بس. info = NoxBridge.json القديم (لو موجود)؛ يرجّع الحقول اللي تنحفظ فيه.
    JsonObject OnlyOurCallers(JsonObject info)
    {
        var ours = OurCallerIds();
        // QueuedCallers من نسخة 70c0de8 (بدون OriginalQueue) كانت للملف القديم — ما تنحسب
        var prevQueued = new HashSet<string>(info?["OriginalQueue"] is JsonArray ? Strings(info["QueuedCallers"] as JsonArray) : new List<string>(),
                                             StringComparer.OrdinalIgnoreCase);
        var original = Strings(info?["OriginalQueue"] as JsonArray);
        bool? originalRandom = (info?["OriginalRandomCommunity"] as JsonValue)?.GetValue<bool>();
        var state = new JsonObject();
        EditSettings(values =>
        {
            JsonObject q = null;
            bool created = false;
            if (values[QueueKey] is JsonValue s && s.TryGetValue<string>(out var text) && !string.IsNullOrWhiteSpace(text))
                q = JsonNode.Parse(text) as JsonObject;
            if (q == null) { q = NewQueue(); created = true; }
            var current = Strings(q["callerIds"] as JsonArray);
            // شخصيات اللعبة اللي بالطابور الحين ← تنحفظ (الأصلي من التركيب الأول + أي جديد بعد تحديث)
            foreach (var id in current.Where(id => !IsOurs(id)))
                if (!original.Contains(id, StringComparer.OrdinalIgnoreCase)) original.Add(id);
            var kept = current.Where(id => IsOurs(id) && ours.Contains(id, StringComparer.OrdinalIgnoreCase)).ToList();
            // ما نرجّع شخصية من شخصياتنا شالها اللاعب بنفسه
            var added = ours.Where(id => !kept.Contains(id, StringComparer.OrdinalIgnoreCase) && !prevQueued.Contains(id)).ToList();
            int removed = current.Count(id => !IsOurs(id));
            q["callerIds"] = new JsonArray(kept.Concat(added).Select(id => (JsonNode)id).ToArray());
            if (!IsOurs(q["lastCallerId"]?.ToString())) q["lastCallerId"] = null;
            if (q["randomCommunityCallers"]?.GetValue<bool>() == true)
            {
                originalRandom ??= true;
                q["randomCommunityCallers"] = false;   // المتصلين العشوائيين من الورشة = مو شخصياتنا
            }
            originalRandom ??= false;
            values[QueueKey] = q.ToJsonString();
            Log(created ? $"• سويت طابور مكالمات فيه شخصياتنا ({added.Count})"
                        : $"• طابور المكالمات: شخصياتنا بس ({kept.Count + added.Count})" + (removed > 0 ? $"، شلت {removed} من شخصيات اللعبة (ترجع بالإرجاع)" : ""));
        });
        state["QueuedCallers"] = new JsonArray(prevQueued.Union(ours, StringComparer.OrdinalIgnoreCase).Select(id => (JsonNode)id).ToArray());
        state["OriginalQueue"] = new JsonArray(original.Select(id => (JsonNode)id).ToArray());
        state["OriginalRandomCommunity"] = originalRandom ?? false;
        return state;
    }

    /// يرجّع طابور اللعبة الأصلي (المحفوظ وقت التركيب) ويشيل شخصياتنا.
    void RestoreQueue(JsonObject info)
    {
        var original = Strings(info?["OriginalQueue"] as JsonArray);
        bool? originalRandom = (info?["OriginalRandomCommunity"] as JsonValue)?.GetValue<bool>();
        EditSettings(values =>
        {
            if (!(values[QueueKey] is JsonValue s && s.TryGetValue<string>(out var text)) || !(JsonNode.Parse(text) is JsonObject q)) return;
            var current = Strings(q["callerIds"] as JsonArray);
            var back = original.Concat(current.Where(id => !IsOurs(id) && !original.Contains(id, StringComparer.OrdinalIgnoreCase))).ToList();
            if (back.SequenceEqual(current) && originalRandom == null) return;
            q["callerIds"] = new JsonArray(back.Select(id => (JsonNode)id).ToArray());
            if (IsOurs(q["lastCallerId"]?.ToString())) q["lastCallerId"] = null;
            if (originalRandom == true) q["randomCommunityCallers"] = true;
            values[QueueKey] = q.ToJsonString();
            Log($"• رجّعت طابور المكالمات الأصلي ({back.Count})");
        });
        CleanLegacyQueue();
    }

    // نسخة 70c0de8 كانت تضيف شخصياتنا لـdaily-callers.json القديم — ننظفه
    void CleanLegacyQueue()
    {
        if (!File.Exists(QueuePath)) return;
        var root = JsonNode.Parse(File.ReadAllText(QueuePath, Encoding.UTF8)) as JsonObject;
        if (root?["callerIds"] is not JsonArray list) return;
        var ours = list.Where(n => IsOurs(n?.ToString())).ToList();
        if (ours.Count == 0) return;
        foreach (var n in ours) list.Remove(n);
        Directory.CreateDirectory(backups);
        File.Copy(QueuePath, Path.Combine(backups, $"daily-callers-{DateTime.Now:yyyyMMdd-HHmmss}.json"), overwrite: true);
        string tmp = QueuePath + ".nox-tmp";
        File.WriteAllText(tmp, root.ToJsonString(Json), new UTF8Encoding(false));
        MoveOver(tmp, QueuePath);
    }

    List<string> OurCallerIds()
    {
        string src = Path.Combine(o.DataDir ?? Path.Combine(AppContext.BaseDirectory, "data"), CallersFile);
        if (!File.Exists(src)) return new List<string>();
        return ((JsonNode.Parse(File.ReadAllText(src, Encoding.UTF8)) as JsonArray) ?? new JsonArray())
            .Select(c => (c?["id"] as JsonValue)?.ToString()).Where(id => !string.IsNullOrEmpty(id)).ToList();
    }

}
