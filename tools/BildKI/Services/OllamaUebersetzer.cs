using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace BildKI.Services;

/// <summary>
/// Übersetzt einen deutschen Bildprompt per lokalem Ollama (POST /api/chat) ins Englische.
/// System-Prompt und Sampling-Optionen entsprechen der "cover_prompt"-Rolle des
/// GeschichtenErzählers (geruest.py: COVER_PROMPT_UEBERSETZEN_SYSTEM, rollen.py).
/// </summary>
public sealed class OllamaUebersetzer
{
    private const string SystemPrompt =
        "Du übersetzt einen stichwortartigen Bildprompt für ein Bildgenerierungsmodell " +
        "(Stable Diffusion / FLUX) von Deutsch nach Englisch. Übersetze möglichst wörtlich, " +
        "nutze dabei die im Englischen übliche Fachterminologie für Bildstil/Beleuchtung " +
        "(z.B. 'painterly illustration', 'cinematic lighting', 'epic'). Erfinde KEINE neuen " +
        "Details, ändere NICHTS am Inhalt, kürze nichts. Antworte NUR mit dem übersetzten " +
        "Prompt als eine einzige Zeile kommagetrennter Stichworte, ohne Erklärung, ohne " +
        "Anführungszeichen.";

    private readonly HttpClient _http;

    public OllamaUebersetzer(HttpClient http) => _http = http;

    public async Task<string> UebersetzeAsync(string baseUrl, string modell, string deutsch, CancellationToken ct)
    {
        var anfrage = new ChatAnfrage
        {
            Model = modell,
            Stream = false,
            Think = false,
            Messages =
            [
                new Nachricht { Role = "system", Content = SystemPrompt },
                new Nachricht { Role = "user", Content = deutsch.Trim() },
            ],
            Options = new Optionen(),
        };

        using var antwort = await _http.PostAsJsonAsync($"{baseUrl.TrimEnd('/')}/api/chat", anfrage, ct);
        var body = await antwort.Content.ReadAsStringAsync(ct);
        if (!antwort.IsSuccessStatusCode)
            throw new InvalidOperationException($"Ollama antwortet mit HTTP {(int)antwort.StatusCode}: {Kurz(body)}");

        var chat = JsonSerializer.Deserialize<ChatAntwort>(body);
        var text = chat?.Message?.Content?.Trim();
        if (string.IsNullOrWhiteSpace(text))
            throw new InvalidOperationException($"Ollama hat keinen Text geliefert: {Kurz(body)}");

        // Modelle setzen gelegentlich Anführungszeichen oder Zeilenumbrüche – auf eine Zeile normalisieren.
        text = text.Trim('"', '\'', '`');
        return string.Join(" ", text.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries));
    }

    private static string Kurz(string s) => s.Length > 400 ? s[..400] + "…" : s;

    // ---- JSON-Modelle (Ollama /api/chat) ----

    private sealed class ChatAnfrage
    {
        [JsonPropertyName("model")] public string Model { get; set; } = "";
        [JsonPropertyName("messages")] public List<Nachricht> Messages { get; set; } = [];
        [JsonPropertyName("stream")] public bool Stream { get; set; }
        [JsonPropertyName("think")] public bool Think { get; set; }
        [JsonPropertyName("options")] public Optionen Options { get; set; } = new();
    }

    private sealed class Nachricht
    {
        [JsonPropertyName("role")] public string Role { get; set; } = "";
        [JsonPropertyName("content")] public string? Content { get; set; }
    }

    private sealed class Optionen
    {
        [JsonPropertyName("temperature")] public double Temperature { get; set; } = 0.3;
        [JsonPropertyName("top_p")] public double TopP { get; set; } = 0.8;
        [JsonPropertyName("min_p")] public double MinP { get; set; } = 0.05;
        [JsonPropertyName("top_k")] public int TopK { get; set; } = 40;
        [JsonPropertyName("repeat_penalty")] public double RepeatPenalty { get; set; } = 1.1;
        [JsonPropertyName("num_ctx")] public int NumCtx { get; set; } = 8192;
        [JsonPropertyName("num_predict")] public int NumPredict { get; set; } = 300;
        [JsonPropertyName("seed")] public int Seed { get; set; } = 42;
    }

    private sealed class ChatAntwort
    {
        [JsonPropertyName("message")] public Nachricht? Message { get; set; }
    }
}
