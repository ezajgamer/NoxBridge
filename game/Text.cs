// NoxGame.Text — ترجمة حيّة للنصوص الإنجليزية اللي تطلع بواجهة اللعبة (شاشات الكمبيوتر داخل اللعبة
// وغيرها مما مو بجداول ترجمة اللعبة الرسمية).
//
// المرقّع يزرع نداء بأول TextElement.SetRenderedText (النص اللي ينرسم بس — النص المنطقي اللي
// تقراه اللعبة ما يتغيّر). أي نص إنجليزي ما له ترجمة ينضاف لطابور، وخيط بالخلفية يرسله للجسر
// (http://127.0.0.1:8797/nox/v1/translate) اللي يترجمه بـGrok ويحفظه بـNoxText.json بمجلد اللعبة.
// المرة الجاية اللي يطلع فيها النص، ينرسم عربي ومن اليمين لليسار بخط اللعبة العربي.
//
// الأرقام ووسوم التنسيق (<b>…) تتحوّل لعلامات ⟦0⟧ قبل البحث، فـ«$500» و«$700» نفس المدخل.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Threading;

namespace NoxGame;

public static class Text
{
    const int MaxLength = 600;
    const int Batch = 40;

    static readonly bool enabled = Config.Translate;
    static readonly Regex Tokens = new Regex(@"<[^<>]{1,80}>|\d+(?:[.,:/]\d+)*");
    static readonly Regex Slot = new Regex(@"⟦(\d+)⟧");

    static readonly object gate = new object();
    static Dictionary<string, string> table;                 // قالب إنجليزي ← قالب عربي
    static readonly HashSet<string> waiting = new HashSet<string>();
    static readonly List<string> queue = new List<string>();
    static Thread worker;
    static object arabicFont;
    static bool fontLooked;

    /// <summary>بأول TextElement.SetRenderedText (element = this): يرجّع النص اللي ينرسم.</summary>
    public static string Render(object element, string value)
    {
        if (!enabled || string.IsNullOrEmpty(value) || value.Length > MaxLength || !HasLatinLetter(value))
        {
            return value;
        }
        try
        {
            if (!Unity.Ready() || Unity.LanguageCode() != "ar")
            {
                return value;
            }
            // خانات الكتابة (اللاعب يكتب فيها) ما نلمسها
            if (element != null && Unity.InsideTextField(element))
            {
                return value;
            }
            var parts = new List<string>();
            string key = Tokens.Replace(value, m =>
            {
                parts.Add(m.Value);
                return "⟦" + (parts.Count - 1) + "⟧";
            });
            if (!HasLatinLetter(Slot.Replace(key, "")))
            {
                return value;
            }
            string translated;
            lock (gate)
            {
                if (table == null)
                {
                    table = Load();
                }
                if (!table.TryGetValue(key, out translated))
                {
                    if (waiting.Add(key))
                    {
                        queue.Add(key);
                        StartWorker();
                    }
                    return value;
                }
            }
            string result = Fill(translated, parts);
            if (result == null)
            {
                return value;
            }
            Present(element);
            return result;
        }
        catch (Exception)
        {
            return value;
        }
    }

    static bool HasLatinLetter(string s)
    {
        foreach (char c in s)
        {
            if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z'))
            {
                return true;
            }
        }
        return false;
    }

    /// <summary>يرجّع الأرقام والوسوم مكان علاماتها. null لو الترجمة ضيّعت علامة.</summary>
    static string Fill(string template, List<string> parts)
    {
        bool ok = true;
        var used = new bool[parts.Count];
        string result = Slot.Replace(template, m =>
        {
            int i = int.Parse(m.Groups[1].Value);
            if (i >= parts.Count)
            {
                ok = false;
                return "";
            }
            used[i] = true;
            return parts[i];
        });
        foreach (bool u in used)
        {
            ok &= u;
        }
        return ok ? result : null;
    }

    /// <summary>العربي: مولّد النص المتقدم (يشبك الحروف)، من اليمين، وخط اللعبة العربي — نفس اللي تسويه اللعبة لنصوصها.</summary>
    static void Present(object element)
    {
        if (element == null)
        {
            return;
        }
        if (!fontLooked)
        {
            fontLooked = true;
            arabicFont = Unity.ArabicFont();
        }
        Unity.MakeArabic(element, arabicFont);
    }

    static Dictionary<string, string> Load()
    {
        var result = new Dictionary<string, string>();
        try
        {
            string path = Path.Combine(Config.GameRoot, "NoxText.json");
            if (File.Exists(path))
            {
                if (Json.Parse(File.ReadAllText(path)) is Dictionary<string, object> saved)
                {
                    foreach (var pair in saved)
                    {
                        if (pair.Value is string ar)
                        {
                            result[pair.Key] = ar;
                        }
                    }
                }
            }
        }
        catch (Exception)
        {
        }
        return result;
    }

    // ───────────────────────── الخلفية ─────────────────────────
    static void StartWorker()
    {
        if (worker != null)
        {
            return;
        }
        worker = new Thread(Work) { IsBackground = true, Name = "NoxGame.Text" };
        worker.Start();
    }

    static void Work()
    {
        int pause = 800;
        while (true)
        {
            Thread.Sleep(pause);
            List<string> batch;
            lock (gate)
            {
                if (queue.Count == 0)
                {
                    pause = 800;
                    continue;
                }
                batch = queue.GetRange(0, Math.Min(Batch, queue.Count));
                queue.RemoveRange(0, batch.Count);
            }
            try
            {
                var body = new StringBuilder("{\"texts\":[");
                for (int n = 0; n < batch.Count; n++)
                {
                    body.Append(n == 0 ? "" : ",").Append(Json.Quote(batch[n]));
                }
                body.Append("]}");
                int status = Http.Post("/nox/v1/translate", body.ToString(), 60000, CancellationToken.None, out string json);
                if (status != 200)
                {
                    throw new InvalidOperationException(json);
                }
                var reply = Json.Parse(json) as Dictionary<string, object>;
                var translations = reply != null && reply.TryGetValue("translations", out object t) ? t as Dictionary<string, object> : null;
                lock (gate)
                {
                    foreach (string key in batch)
                    {
                        string ar = translations != null && translations.TryGetValue(key, out object v) ? v as string : null;
                        if (!string.IsNullOrEmpty(ar))
                        {
                            table[key] = ar;
                        }
                        waiting.Remove(key);   // اللي ما ترجم يرجع يندز لو طلع مرة ثانية
                    }
                }
                pause = 800;
            }
            catch (Exception)
            {
                // الجسر طافي أو فشل: نرجّعها للطابور ونهدّي (لين ١٥ ثانية)
                lock (gate)
                {
                    queue.InsertRange(0, batch);
                }
                pause = Math.Min(pause * 2, 15000);
            }
        }
    }
}

/// <summary>Unity واللعبة بالـReflection (اللغة، خانات الكتابة، الخط العربي، الاتجاه). لو شي ما انلقى
/// (تحديث للعبة) الترجمة تطفي بهدوء بدل ما تطيّح.</summary>
static class Unity
{
    static bool? ready;
    static PropertyInfo effectiveCode;
    static MethodInfo uiFont, ancestorOfTextField;
    static Type labelType;

    // تنسيق النص — من أنواع خصائص العنصر نفسه (ما نحتاج أسماء namespaces)
    static PropertyInfo styleProp, generatorProp, directionProp, fontDefProp;
    static object advanced, rtl;
    static bool presentBroken;

    public static bool Ready()
    {
        if (ready.HasValue)
        {
            return ready.Value;
        }
        try
        {
            Type languages = Game.Need("LanguageManager");
            effectiveCode = Game.Property(languages, "EffectiveCode");
            uiFont = Game.Method(languages, "GetUiFontForCode", typeof(string));
            labelType = Game.Need("UnityEngine.UIElements.Label");
            Type textField = Game.Need("UnityEngine.UIElements.TextField");
            Type visual = Game.Need("UnityEngine.UIElements.VisualElement");
            ancestorOfTextField = Game.Method(visual, "GetFirstAncestorOfType").MakeGenericMethod(textField);
            ready = true;
        }
        catch (Exception e)
        {
            Voice.UnityLog("NoxGame.Text: " + e.Message + " — ترجمة الشاشات طافية");
            ready = false;
        }
        return ready.Value;
    }

    public static string LanguageCode() => effectiveCode.GetValue(null, null) as string;

    public static bool InsideTextField(object element) =>
        !labelType.IsInstanceOfType(element) && ancestorOfTextField.Invoke(element, null) != null;

    public static object ArabicFont()
    {
        try
        {
            return uiFont.Invoke(null, new object[] { "ar" });
        }
        catch (Exception)
        {
            return null;
        }
    }

    public static void MakeArabic(object element, object font)
    {
        if (presentBroken)
        {
            return;
        }
        try
        {
            if (styleProp == null)
            {
                Type t = element.GetType();
                styleProp = Game.Property(t, "style");
                directionProp = Game.Property(t, "languageDirection");
                rtl = Enum.Parse(directionProp.PropertyType, "RTL");
                generatorProp = Game.Property(styleProp.PropertyType, "unityTextGenerator");
                advanced = Enum.Parse(generatorProp.PropertyType.GetGenericArguments()[0], "Advanced");
                fontDefProp = Game.Property(styleProp.PropertyType, "unityFontDefinition");
            }
            object style = styleProp.GetValue(element, null);
            object generator = generatorProp.GetValue(style, null);
            if (!Equals(Game.Property(generator.GetType(), "value").GetValue(generator, null), advanced))
            {
                generatorProp.SetValue(style, Activator.CreateInstance(generatorProp.PropertyType, advanced), null);
            }
            if (!Equals(directionProp.GetValue(element, null), rtl))
            {
                directionProp.SetValue(element, rtl, null);
            }
            if (font == null)
            {
                return;
            }
            object styleFont = fontDefProp.GetValue(style, null);
            object definition = Game.Property(styleFont.GetType(), "value").GetValue(styleFont, null);
            if (!ReferenceEquals(Game.Property(definition.GetType(), "font").GetValue(definition, null), font))
            {
                object newDefinition = Game.Method(definition.GetType(), "FromFont", font.GetType()).Invoke(null, new[] { font });
                fontDefProp.SetValue(style, Activator.CreateInstance(fontDefProp.PropertyType, newDefinition), null);
            }
        }
        catch (Exception e)
        {
            presentBroken = true;   // نكمل نترجم بس بدون تنسيق
            Voice.UnityLog("NoxGame.Text: تنسيق العربي ما ضبط — " + e.Message);
        }
    }
}
