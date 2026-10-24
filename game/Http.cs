// NoxGame.Http — طلب POST للجسر المحلي (127.0.0.1:8797) فوق TcpClient.
// تحديث اللعبة (24/10) شال HttpClient من System.Net.Http المقصوصة؛ TcpClient باقي بـSystem.dll.
// الجسر (http.server بايثون) يرد بـContent-Length، ونسكّر الاتصال بعد كل طلب (Connection: close).
using System;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Threading;

namespace NoxGame;

static class Http
{
    const string Host = "127.0.0.1";
    const int Port = 8797;

    /// <summary>يرجّع (كود الحالة، نص الرد). ct يقطع الاتصال.</summary>
    public static int Post(string path, string json, int timeoutMs, CancellationToken ct, out string reply)
    {
        byte[] body = Encoding.UTF8.GetBytes(json);
        var client = new TcpClient();
        using (ct.Register(() => client.Close()))
        {
            try
            {
                client.Connect(Host, Port);
                client.ReceiveTimeout = timeoutMs;
                client.SendTimeout = timeoutMs;
                NetworkStream stream = client.GetStream();
                string head = "POST " + path + " HTTP/1.1\r\nHost: " + Host + ":" + Port +
                              "\r\nContent-Type: application/json\r\nContent-Length: " + body.Length +
                              "\r\nConnection: close\r\n\r\n";
                byte[] headBytes = Encoding.ASCII.GetBytes(head);
                stream.Write(headBytes, 0, headBytes.Length);
                stream.Write(body, 0, body.Length);
                byte[] raw = ReadAll(stream);
                ct.ThrowIfCancellationRequested();
                return Parse(raw, out reply);
            }
            catch (Exception) when (ct.IsCancellationRequested)
            {
                throw new OperationCanceledException(ct);
            }
            finally
            {
                client.Close();
            }
        }
    }

    static byte[] ReadAll(NetworkStream stream)
    {
        var all = new MemoryStream();
        var buffer = new byte[16384];
        int n;
        while ((n = stream.Read(buffer, 0, buffer.Length)) > 0)
        {
            all.Write(buffer, 0, n);
        }
        return all.ToArray();
    }

    static int Parse(byte[] raw, out string reply)
    {
        int split = -1;
        for (int i = 0; i + 3 < raw.Length; i++)
        {
            if (raw[i] == '\r' && raw[i + 1] == '\n' && raw[i + 2] == '\r' && raw[i + 3] == '\n')
            {
                split = i;
                break;
            }
        }
        if (split < 0)
        {
            throw new IOException("NoxGame.Http: رد ناقص من الجسر");
        }
        string head = Encoding.ASCII.GetString(raw, 0, split);
        string[] status = head.Split('\n')[0].Split(' ');
        int code = status.Length > 1 ? int.Parse(status[1]) : 0;
        int start = split + 4, length = raw.Length - start;
        foreach (string line in head.Split('\n'))
        {
            int colon = line.IndexOf(':');
            if (colon > 0 && string.Equals(line.Substring(0, colon).Trim(), "Content-Length", StringComparison.OrdinalIgnoreCase))
            {
                length = Math.Min(length, int.Parse(line.Substring(colon + 1).Trim()));
            }
        }
        reply = Encoding.UTF8.GetString(raw, start, length);
        return code;
    }
}
