using System.IO;
using System.Text.Json;

namespace BildKI;

/// <summary>
/// Persistente Einstellungen, abgelegt unter %APPDATA%\BildKI\einstellungen.json.
/// Die Defaults entsprechen dem Setup des GeschichtenErzählers:
/// sd-server (stable-diffusion.cpp, FLUX.1-schnell) und Ollama auf Athene.
/// </summary>
public class Einstellungen
{
    public string SdServerUrl { get; set; } = "http://192.168.188.181:7860";
    public string OllamaUrl { get; set; } = "http://192.168.188.181:11434";
    public string OllamaModell { get; set; } = "gemma4";

    public int Breite { get; set; } = 1024;
    public int Hoehe { get; set; } = 1024;
    /// <summary>FLUX.1-schnell ist auf 4 Schritte distilliert.</summary>
    public int Schritte { get; set; } = 4;
    /// <summary>Gesamt-Zeitbudget für einen Bild-Job (FLUX auf der 780M-iGPU braucht Minuten).</summary>
    public int TimeoutSekunden { get; set; } = 600;

    // ---- Zweites Modell: Pony Diffusion V6 XL + Realism-LoRA (eigene
    // sd-server-Instanz auf Athene, ~/docker/sd-server-pony-compose.yaml) ----
    public string SdServerUrlPony { get; set; } = "http://192.168.188.181:7861";
    /// <summary>Kein Turbo-Modell wie FLUX.1-schnell - braucht echtes CFG und mehr Schritte.</summary>
    public int SchrittePony { get; set; } = 24;
    public double CfgPony { get; set; } = 5.0;
    public string SampleMethodPony { get; set; } = "dpm++2m";
    /// <summary>Dateiname relativ zu --lora-model-dir auf der Pony-Instanz (siehe GET /sdcpp/v1/capabilities -&gt; "loras").</summary>
    public string LoraPfadPony { get; set; } = "Realism Lora By Stable Yogi_V3_Lite.safetensors";
    /// <summary>Empfohlene Spanne laut Civitai: 0.4-1.5.</summary>
    public double LoraGewichtPony { get; set; } = 1.0;
    /// <summary>Zuletzt gewähltes Modell ("flux"/"pony") - beim nächsten Start wiederhergestellt.</summary>
    public string AktivesModell { get; set; } = "flux";

    public bool AutomatischSpeichern { get; set; } = true;
    public bool PromptDateiMitspeichern { get; set; } = true;
    public string SpeicherOrdner { get; set; } =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyPictures), "BildKI");

    /// <summary>
    /// Fester Negativ-Prompt gegen typische Diffusions-Artefakte (übernommen aus
    /// bild_generierung.py). Bei CFG==1 (FLUX.1-schnell) ignoriert sd-server ihn,
    /// er wird trotzdem mitgeschickt, damit er bei einem Modellwechsel greift.
    /// </summary>
    public string NegativPrompt { get; set; } =
        "extra limbs, extra arms, extra hands, extra legs, extra fingers, " +
        "extra arm, third arm, three arms, duplicate arm, duplicate hand, " +
        "fused fingers, missing fingers, deformed hands, mutated hands, " +
        "malformed limbs, disfigured, duplicate body parts, bad anatomy, " +
        "uncanny face, asymmetric face, deformed face, distorted face, " +
        "waxy skin, empty stare, dead eyes, " +
        "duplicate person, cloned figure, twins, identical duplicate, " +
        "blurry, low quality, watermark, text";

    private static readonly string Pfad = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "BildKI", "einstellungen.json");

    private static readonly JsonSerializerOptions JsonOpts = new() { WriteIndented = true };

    public static Einstellungen Laden()
    {
        try
        {
            if (File.Exists(Pfad))
                return JsonSerializer.Deserialize<Einstellungen>(File.ReadAllText(Pfad), JsonOpts) ?? new Einstellungen();
        }
        catch
        {
            // Kaputte Datei -> Defaults verwenden, beim nächsten Speichern wird sie überschrieben.
        }
        return new Einstellungen();
    }

    public void Speichern()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Pfad)!);
        File.WriteAllText(Pfad, JsonSerializer.Serialize(this, JsonOpts));
    }
}
