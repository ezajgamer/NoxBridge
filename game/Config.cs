// إعدادات NoxGame — من NoxBridge.json بجذر اللعبة (يكتبه المرقّع والبرنامج). تنقرا مرة مع بداية اللعبة.
using System;
using System.Collections.Generic;
using System.IO;

namespace NoxGame;

static class Config
{
    public static readonly string GameRoot = FindRoot();
    static readonly Dictionary<string, object> values = Load();

    /// <summary>صوت الشخصيات العربي من Grok.</summary>
    public static bool Voice => values.TryGetValue("Voice", out object v) && v as string == "grok";

    /// <summary>ترجمة النصوص الإنجليزية بالواجهة (شاشات الكمبيوتر داخل اللعبة).</summary>
    public static bool Translate => values.TryGetValue("Translate", out object v) && v is bool b && b;

    static string FindRoot()
    {
        // ...\Scam With Your Friends_Data\Managed\NoxGame.dll ← الجذر فوقها بمجلدين
        string managed = Path.GetDirectoryName(typeof(Config).Assembly.Location);
        return Path.GetDirectoryName(Path.GetDirectoryName(managed));
    }

    static Dictionary<string, object> Load()
    {
        try
        {
            return Json.Parse(File.ReadAllText(Path.Combine(GameRoot, "NoxBridge.json"))) as Dictionary<string, object>
                   ?? new Dictionary<string, object>();
        }
        catch (Exception)
        {
            return new Dictionary<string, object>();
        }
    }
}
