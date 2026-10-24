// NoxGame.Voice — صوت الشخصيات العربية من Grok بدل موديل اللعبة المحلي (MOSS TTS Nano).
//
// اللعبة تولّد الصوت العربي بـKolkata.MossTtsNano.MossOnnxRuntime: Synthesize(نص، صوت، emit)
// يرسل قطع صوت (24kHz) واللعبة تشغّلها وتعرض الكلمات. المرقّع (NoxPatcher2) يزرع نداءين:
//   ١) أول بنّاء MossOnnxRuntime: SkipModel() = true ⇒ ما يحمّل الموديل أصلاً (ذاكرة وCPU أقل).
//   ٢) أول Synthesize: Synthesize(...) ≥ 0 ⇒ رجع بدون الموديل؛ ‎-1 ⇒ يكمل الموديل الأصلي.
// الصوت يجي من الجسر المحلي (http://127.0.0.1:8797/nox/v1/tts) — يختار صوت Grok حسب جنس الشخصية.
// التشغيل/الإطفاء من NoxBridge.json بمجلد اللعبة ("Voice": "grok") — Config، يُقرأ مرة مع بداية اللعبة.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using System.Threading;

namespace NoxGame;

public static class Voice
{
    const int Rate = 24000;                 // معدّل اللعبة لكل الأصوات
    const int Slice = Rate / 2;             // نرسل الصوت قطع نص ثانية (الكلمات تنوزّع عليها)

    static readonly bool enabled = Config.Voice;

    // أنواع اللعبة (Kolkata.Speech: PocketTTS، وKolkata.MossTtsNano) — تنلقى وقت التشغيل
    static bool? ready;
    static MethodInfo parse, split, takeWords;
    static FieldInfo segIsPause, segPauseSamples, segText, chunkSpeech, chunkWords;
    static ConstructorInfo audioCtor;

    static bool Ready()
    {
        if (ready.HasValue)
        {
            return ready.Value;
        }
        try
        {
            Type parser = Game.Need("PocketTTS.PauseTagParser"), segment = Game.Need("PocketTTS.PromptSegment");
            Type audio = Game.Need("PocketTTS.PocketTtsAudioResponse"), word = Game.Need("PocketTTS.PocketTtsTranscriptWord");
            Type timing = Game.Need("PocketTTS.SpeechTranscriptTiming");
            Type chunker = Game.Need("Kolkata.MossTtsNano.MossTextChunker"), chunk = Game.Need("Kolkata.MossTtsNano.MossSpeechChunk");
            parse = Game.Method(parser, "Parse", typeof(string));
            split = Game.Method(chunker, "Split", typeof(string), typeof(Func<string, int>), typeof(int));
            takeWords = Game.Method(timing, "TakeTranscriptWords", typeof(Queue<string>), typeof(int).MakeByRefType(), typeof(int), typeof(bool));
            segIsPause = Game.Field(segment, "IsPause");
            segPauseSamples = Game.Field(segment, "PauseSamples");
            segText = Game.Field(segment, "Text");
            chunkSpeech = Game.Field(chunk, "Speech");
            chunkWords = Game.Field(chunk, "TranscriptWords");
            audioCtor = audio.GetConstructor(new[] { typeof(float[]), typeof(int), word.MakeArrayType() })
                       ?? throw new MissingMemberException("NoxGame: ما لقيت بنّاء PocketTtsAudioResponse");
            ready = true;
        }
        catch (Exception e)
        {
            // تحديث للعبة غيّر شي ⇒ نخلّي صوت اللعبة الأصلي يشتغل (أحسن من ما فيه صوت)
            UnityLog("NoxGame.Voice: " + e.Message + " — صوت اللعبة الأصلي");
            ready = false;
        }
        return ready.Value;
    }

    /// <summary>بنّاء MossOnnxRuntime: true = لا تحمّل الموديل.</summary>
    public static bool SkipModel() => enabled && Ready();

    /// <summary>بديل MossOnnxRuntime.Synthesize (emit = Action&lt;PocketTtsAudioResponse&gt;). يرجّع عدد القطع
    /// المقصوصة (0)، أو ‎-1 = خلّ الموديل الأصلي يشتغل.</summary>
    public static int Synthesize(string text, string voicePath, object emit, CancellationToken ct)
    {
        if (!enabled || !Ready() || !(emit is Delegate send))
        {
            return -1;
        }
        foreach (object segment in (IEnumerable)parse.Invoke(null, new object[] { text }))
        {
            ct.ThrowIfCancellationRequested();
            if ((bool)segIsPause.GetValue(segment))
            {
                int samples = (int)segPauseSamples.GetValue(segment);
                send.DynamicInvoke(audioCtor.Invoke(new object[] { new float[samples], samples, null }));
                continue;
            }
            string segmentText = (string)segText.GetValue(segment);
            if (string.IsNullOrWhiteSpace(segmentText))
            {
                continue;
            }
            // كلمات الترجمة المكتوبة نفس ما يطلّعها موديل اللعبة (مقسّمها هو اللي يحدد النص المنطوق)
            var words = new Queue<string>();
            var speech = new StringBuilder();
            Func<string, int> countTokens = s => s.Length / 3 + 1;
            foreach (object chunk in (IEnumerable)split.Invoke(null, new object[] { segmentText, countTokens, 60 }))
            {
                string said = (string)chunkSpeech.GetValue(chunk);
                if (string.IsNullOrWhiteSpace(said))
                {
                    continue;
                }
                speech.Append(said).Append(' ');
                foreach (string w in (string[])chunkWords.GetValue(chunk) ?? new string[0])
                {
                    words.Enqueue(w);
                }
            }
            if (speech.Length == 0)
            {
                continue;
            }
            float[] pcm = Fetch(speech.ToString().Trim(), voicePath, ct);
            int until = 0;
            for (int at = 0; at < pcm.Length; at += Slice)
            {
                ct.ThrowIfCancellationRequested();
                int length = Math.Min(Slice, pcm.Length - at);
                float[] part = new float[length];
                Array.Copy(pcm, at, part, 0, length);
                bool last = at + length >= pcm.Length;
                object[] args = { words, until, length, last };
                object spoken = takeWords.Invoke(null, args);
                until = (int)args[1];   // ref
                send.DynamicInvoke(audioCtor.Invoke(new object[] { part, length, spoken }));
            }
        }
        return 0;
    }

    internal static void UnityLog(string message)
    {
        try
        {
            Game.Method(Game.Need("UnityEngine.Debug"), "LogWarning", typeof(object)).Invoke(null, new object[] { message });
        }
        catch (Exception)
        {
        }
    }

    static float[] Fetch(string text, string voicePath, CancellationToken ct)
    {
        string json = "{\"text\":" + Json.Quote(text) + ",\"voice\":" + Json.Quote(voicePath ?? "") + "}";
        // الجسر يرجّع الصوت WAV مرمّز base64 داخل نص
        int status = Http.Post("/nox/v1/tts", json, 30000, ct, out string payload);
        if (status != 200)
        {
            throw new InvalidOperationException("NoxGame.Voice: الجسر ما رجّع صوت (" + status + "): " + payload);
        }
        return Wav.ToMono24k(Convert.FromBase64String(payload.Trim()));
    }
}

/// <summary>يفك WAV (PCM16، أي عدد قنوات وأي معدّل) ← قناة وحدة 24kHz. الجسر يضمن PCM16.</summary>
static class Wav
{
    public static float[] ToMono24k(byte[] wav)
    {
        if (wav.Length < 12 || Encoding.ASCII.GetString(wav, 0, 4) != "RIFF" || Encoding.ASCII.GetString(wav, 8, 4) != "WAVE")
        {
            throw new InvalidDataException("NoxGame.Voice: الرد مو WAV");
        }
        int format = 0, channels = 1, rate = 24000, bits = 16, dataAt = -1, dataLength = 0;
        int i = 12;
        while (i + 8 <= wav.Length)
        {
            string id = Encoding.ASCII.GetString(wav, i, 4);
            int size = BitConverter.ToInt32(wav, i + 4);
            if (id == "fmt ")
            {
                format = BitConverter.ToUInt16(wav, i + 8);
                channels = BitConverter.ToUInt16(wav, i + 10);
                rate = BitConverter.ToInt32(wav, i + 12);
                bits = BitConverter.ToUInt16(wav, i + 22);
            }
            else if (id == "data")
            {
                dataAt = i + 8;
                // بعض الخدمات تكتب حجم «غير معروف» للبث — نعتمد على طول الملف
                dataLength = size <= 0 || dataAt + size > wav.Length ? wav.Length - dataAt : size;
                break;
            }
            i += 8 + Math.Max(0, size) + (size & 1);
        }
        if (dataAt < 0 || channels < 1)
        {
            throw new InvalidDataException("NoxGame.Voice: WAV بلا بيانات");
        }
        if (format != 1 || bits != 16)
        {
            throw new InvalidDataException("NoxGame.Voice: WAV لازم PCM16 (وصل format=" + format + " bits=" + bits + ")");
        }
        int bytesPerSample = bits / 8;
        int frames = dataLength / (bytesPerSample * channels);
        var mono = new float[frames];
        for (int f = 0; f < frames; f++)
        {
            float sum = 0f;
            for (int c = 0; c < channels; c++)
            {
                int at = dataAt + (f * channels + c) * bytesPerSample;
                sum += (short)(wav[at] | wav[at + 1] << 8) / 32768f;
            }
            mono[f] = sum / channels;
        }
        return rate == 24000 ? mono : Resample(mono, rate, 24000);
    }

    static float[] Resample(float[] input, int from, int to)
    {
        int length = (int)((long)input.Length * to / from);
        var output = new float[length];
        double step = (double)from / to;
        for (int n = 0; n < length; n++)
        {
            double pos = n * step;
            int a = (int)pos;
            int b = Math.Min(a + 1, input.Length - 1);
            float t = (float)(pos - a);
            output[n] = input[a] * (1f - t) + input[b] * t;
        }
        return output;
    }
}
