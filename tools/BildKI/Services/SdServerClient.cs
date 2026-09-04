using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace BildKI.Services;

/// <summary>
/// Client für die native asynchrone API von sd-server (stable-diffusion.cpp, Präfix /sdcpp/v1):
/// POST /sdcpp/v1/img_gen liefert sofort eine Job-ID (HTTP 202), das Bild wird per
/// GET /sdcpp/v1/jobs/{id} abgeholt, sobald status == "completed"
/// (Base64-PNG unter result.images[0].b64_json). Entspricht bild_generierung.py.
/// </summary>
public sealed class SdServerClient
{
    private static readonly TimeSpan PollIntervall = TimeSpan.FromSeconds(3);
    private readonly HttpClient _http;

    public SdServerClient(HttpClient http) => _http = http;

    public async Task<byte[]> GeneriereAsync(
        string baseUrl, string prompt, string negativPrompt,
        int breite, int hoehe, int schritte, TimeSpan timeout,
        IProgress<string>? status, CancellationToken ct,
        string? sampleMethod = null, double? cfgScale = null,
        IReadOnlyList<LoraEintrag>? lora = null)
    {
        baseUrl = baseUrl.TrimEnd('/');
        var payload = new JobAnfrage
        {
            Prompt = prompt,
            NegativePrompt = string.IsNullOrWhiteSpace(negativPrompt) ? null : negativPrompt,
            Width = breite,
            Height = hoehe,
            SampleParams = new SampleParams
            {
                SampleSteps = schritte,
                SampleMethod = sampleMethod,
                Guidance = cfgScale is { } cfg ? new Guidance { TxtCfg = cfg } : null,
            },
            Lora = lora is { Count: > 0 } ? lora : null,
        };

        var frist = DateTime.UtcNow + timeout;

        using var start = await _http.PostAsJsonAsync($"{baseUrl}/sdcpp/v1/img_gen", payload, ct);
        var startBody = await start.Content.ReadAsStringAsync(ct);
        if (!start.IsSuccessStatusCode)
            throw new InvalidOperationException($"sd-server lehnt den Bild-Job ab (HTTP {(int)start.StatusCode}): {Kurz(startBody)}");

        var jobId = JsonSerializer.Deserialize<JobStart>(startBody)?.Id;
        if (string.IsNullOrWhiteSpace(jobId))
            throw new InvalidOperationException($"sd-server hat keine Job-ID geliefert: {Kurz(startBody)}");

        var jobUrl = $"{baseUrl}/sdcpp/v1/jobs/{jobId}";
        var beginn = DateTime.UtcNow;

        while (true)
        {
            ct.ThrowIfCancellationRequested();

            using var stand = await _http.GetAsync(jobUrl, ct);
            var body = await stand.Content.ReadAsStringAsync(ct);
            if (!stand.IsSuccessStatusCode)
                throw new InvalidOperationException($"Job-Status nicht abrufbar (HTTP {(int)stand.StatusCode}): {Kurz(body)}");

            var job = JsonSerializer.Deserialize<JobStatus>(body) ?? new JobStatus();
            var s = (job.Status ?? "").ToLowerInvariant();

            switch (s)
            {
                case "completed":
                    var b64 = job.Result?.Images?.FirstOrDefault()?.B64Json;
                    if (string.IsNullOrWhiteSpace(b64))
                        throw new InvalidOperationException("Job ist fertig, enthält aber kein Bild.");
                    return Convert.FromBase64String(b64);

                case "failed":
                case "cancelled":
                case "canceled":
                    throw new InvalidOperationException($"sd-server-Job fehlgeschlagen: {job.Error?.Message ?? s}");
            }

            if (DateTime.UtcNow >= frist)
                throw new TimeoutException($"sd-server wurde nach {timeout.TotalSeconds:0}s nicht fertig (letzter Status: {(s == "" ? "unbekannt" : s)}).");

            var vergangen = DateTime.UtcNow - beginn;
            status?.Report($"Bild wird berechnet … Status: {(s == "" ? "unbekannt" : s)} ({vergangen:m\\:ss})");
            await Task.Delay(PollIntervall, ct);
        }
    }

    private static string Kurz(string s) => s.Length > 400 ? s[..400] + "…" : s;

    // ---- JSON-Modelle (sd-server examples/server/api.md) ----

    private sealed class JobAnfrage
    {
        [JsonPropertyName("prompt")] public string Prompt { get; set; } = "";
        [JsonPropertyName("negative_prompt"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? NegativePrompt { get; set; }
        [JsonPropertyName("width")] public int Width { get; set; }
        [JsonPropertyName("height")] public int Height { get; set; }
        [JsonPropertyName("output_format")] public string OutputFormat { get; set; } = "png";
        [JsonPropertyName("sample_params")] public SampleParams SampleParams { get; set; } = new();
        // Eigenes Top-Level-Feld, NICHT die "<lora:name:gewicht>"-Prompt-Syntax
        // der CLI - siehe examples/server/api.md der nativen sd-server-API.
        [JsonPropertyName("lora"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public IReadOnlyList<LoraEintrag>? Lora { get; set; }
    }

    private sealed class SampleParams
    {
        [JsonPropertyName("sample_steps")] public int SampleSteps { get; set; }
        [JsonPropertyName("sample_method"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public string? SampleMethod { get; set; }
        [JsonPropertyName("guidance"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public Guidance? Guidance { get; set; }
    }

    private sealed class Guidance
    {
        [JsonPropertyName("txt_cfg")] public double TxtCfg { get; set; }
    }

    public sealed class LoraEintrag
    {
        [JsonPropertyName("path")] public string Path { get; set; } = "";
        [JsonPropertyName("multiplier")] public double Multiplier { get; set; } = 1.0;
    }

    private sealed class JobStart
    {
        [JsonPropertyName("id")] public string? Id { get; set; }
    }

    private sealed class JobStatus
    {
        [JsonPropertyName("status")] public string? Status { get; set; }
        [JsonPropertyName("result")] public JobResult? Result { get; set; }
        [JsonPropertyName("error")] public JobFehler? Error { get; set; }
    }

    private sealed class JobResult
    {
        [JsonPropertyName("images")] public List<JobBild>? Images { get; set; }
    }

    private sealed class JobBild
    {
        [JsonPropertyName("b64_json")] public string? B64Json { get; set; }
    }

    private sealed class JobFehler
    {
        [JsonPropertyName("message")] public string? Message { get; set; }
    }
}
