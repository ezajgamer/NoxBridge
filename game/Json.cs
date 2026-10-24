// NoxGame.Json — قارئ/كاتب JSON صغير (بدل Newtonsoft اللي باللعبة، عشان ما نحتاج مكتباتها وقت البناء).
// يكفي ملفاتنا: NoxBridge.json، وNoxText.json، وطلبات/ردود الترجمة.
// القيم: Dictionary<string, object> / List<object> / string / double / bool / null.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace NoxGame;

static class Json
{
    public static object Parse(string text)
    {
        int i = 0;
        object value = Value(text, ref i);
        Space(text, ref i);
        if (i != text.Length)
        {
            throw new FormatException("JSON: زيادة بعد القيمة عند " + i);
        }
        return value;
    }

    public static string Quote(string value)
    {
        var sb = new StringBuilder("\"");
        foreach (char c in value ?? "")
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                default:
                    if (c < 0x20)
                    {
                        sb.Append("\\u").Append(((int)c).ToString("x4"));
                    }
                    else
                    {
                        sb.Append(c);
                    }
                    break;
            }
        }
        return sb.Append('"').ToString();
    }

    static void Space(string s, ref int i)
    {
        while (i < s.Length && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r' || s[i] == '﻿'))
        {
            i++;
        }
    }

    static object Value(string s, ref int i)
    {
        Space(s, ref i);
        if (i >= s.Length)
        {
            throw new FormatException("JSON: انتهى النص");
        }
        char c = s[i];
        if (c == '{')
        {
            var obj = new Dictionary<string, object>();
            i++;
            Space(s, ref i);
            if (i < s.Length && s[i] == '}')
            {
                i++;
                return obj;
            }
            while (true)
            {
                Space(s, ref i);
                string key = String(s, ref i);
                Space(s, ref i);
                Expect(s, ref i, ':');
                obj[key] = Value(s, ref i);
                Space(s, ref i);
                if (i < s.Length && s[i] == ',')
                {
                    i++;
                    continue;
                }
                Expect(s, ref i, '}');
                return obj;
            }
        }
        if (c == '[')
        {
            var list = new List<object>();
            i++;
            Space(s, ref i);
            if (i < s.Length && s[i] == ']')
            {
                i++;
                return list;
            }
            while (true)
            {
                list.Add(Value(s, ref i));
                Space(s, ref i);
                if (i < s.Length && s[i] == ',')
                {
                    i++;
                    continue;
                }
                Expect(s, ref i, ']');
                return list;
            }
        }
        if (c == '"')
        {
            return String(s, ref i);
        }
        if (Word(s, ref i, "true"))
        {
            return true;
        }
        if (Word(s, ref i, "false"))
        {
            return false;
        }
        if (Word(s, ref i, "null"))
        {
            return null;
        }
        int start = i;
        while (i < s.Length && "+-0123456789.eE".IndexOf(s[i]) >= 0)
        {
            i++;
        }
        if (i == start)
        {
            throw new FormatException("JSON: حرف غير متوقع عند " + i);
        }
        return double.Parse(s.Substring(start, i - start), NumberStyles.Float, CultureInfo.InvariantCulture);
    }

    static bool Word(string s, ref int i, string word)
    {
        if (string.CompareOrdinal(s, i, word, 0, word.Length) != 0)
        {
            return false;
        }
        i += word.Length;
        return true;
    }

    static void Expect(string s, ref int i, char c)
    {
        if (i >= s.Length || s[i] != c)
        {
            throw new FormatException("JSON: متوقع '" + c + "' عند " + i);
        }
        i++;
    }

    static string String(string s, ref int i)
    {
        Expect(s, ref i, '"');
        var sb = new StringBuilder();
        while (i < s.Length)
        {
            char c = s[i++];
            if (c == '"')
            {
                return sb.ToString();
            }
            if (c != '\\')
            {
                sb.Append(c);
                continue;
            }
            if (i >= s.Length)
            {
                break;
            }
            char e = s[i++];
            switch (e)
            {
                case 'n': sb.Append('\n'); break;
                case 'r': sb.Append('\r'); break;
                case 't': sb.Append('\t'); break;
                case 'b': sb.Append('\b'); break;
                case 'f': sb.Append('\f'); break;
                case 'u':
                    if (i + 4 > s.Length)
                    {
                        throw new FormatException("JSON: \\u ناقص");
                    }
                    sb.Append((char)int.Parse(s.Substring(i, 4), NumberStyles.HexNumber, CultureInfo.InvariantCulture));
                    i += 4;
                    break;
                default: sb.Append(e); break;   // \" \\ \/
            }
        }
        throw new FormatException("JSON: نص بلا نهاية");
    }
}
