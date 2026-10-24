// NoxGame.Game — يلقى أنواع اللعبة وUnity وقت التشغيل (Reflection).
// NoxGame ينبني على مكتبات .NET العامة بس (بدون ملفات اللعبة)، عشان المشروع ينبني من الكود المنشور
// لحاله. كل نوع/دالة من اللعبة ينطلب بالاسم هني، وينحفظ بعد أول مرة.
using System;
using System.Collections.Generic;
using System.Reflection;

namespace NoxGame;

static class Game
{
    const BindingFlags Any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
    static readonly Dictionary<string, Type> types = new Dictionary<string, Type>();

    /// <summary>نوع بالاسم الكامل من أي مكتبة محمّلة باللعبة، أو null.</summary>
    public static Type Type(string fullName)
    {
        lock (types)
        {
            if (types.TryGetValue(fullName, out Type found) && found != null)
            {
                return found;
            }
            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type t = assembly.GetType(fullName, false, false);
                if (t != null)
                {
                    types[fullName] = t;
                    return t;
                }
            }
            return null;   // ما ينحفظ: يمكن مكتبتها ما تحمّلت بعد
        }
    }

    public static Type Need(string fullName) =>
        Type(fullName) ?? throw new MissingMemberException("NoxGame: ما لقيت " + fullName);

    public static MethodInfo Method(Type type, string name, params Type[] args) =>
        (args.Length == 0 ? type.GetMethod(name, Any) : type.GetMethod(name, Any, null, args, null))
        ?? throw new MissingMemberException("NoxGame: ما لقيت " + type.FullName + "." + name);

    public static PropertyInfo Property(Type type, string name) =>
        type.GetProperty(name, Any) ?? throw new MissingMemberException("NoxGame: ما لقيت " + type.FullName + "." + name);

    public static FieldInfo Field(Type type, string name) =>
        type.GetField(name, Any) ?? throw new MissingMemberException("NoxGame: ما لقيت " + type.FullName + "." + name);
}
