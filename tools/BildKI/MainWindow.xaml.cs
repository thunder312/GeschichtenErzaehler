using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media.Imaging;
using BildKI.Services;
using Microsoft.Win32;

namespace BildKI;

public partial class MainWindow : Window
{
    private const string HochformatPraefix = "Hochformat, ";
    // Pony Diffusion wurde mit einem Aesthetic-Score-System trainiert - ohne
    // diese absteigende Tag-Kette am Prompt-Anfang wirken Bilder flau/unfertig.
    private const string PonyScoreTagsPraefix =
        "score_9, score_8_up, score_7_up, score_6_up, score_5_up, score_4_up, ";

    private readonly Einstellungen _einst = Einstellungen.Laden();
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(300) }; // pro Einzelrequest; Ollama muss ggf. erst das Modell laden
    private readonly OllamaUebersetzer _uebersetzer;
    private readonly SdServerClient _sd;

    private CancellationTokenSource? _cts;
    private byte[]? _bildBytes;
    private string _letzterPromptDe = "";
    private string _letzterPromptEn = "";
    private bool _formatWirdGesetzt;
    /// <summary>Modell der letzten (erfolgreichen) Generierung - fuer die Schritte-Angabe
    /// in der gespeicherten .txt-Begleitdatei (siehe PromptDateiSchreiben).</summary>
    private bool _letzteGenerierungIstPony;

    public MainWindow()
    {
        InitializeComponent();
        _uebersetzer = new OllamaUebersetzer(_http);
        _sd = new SdServerClient(_http);
        EinstellungenInUiLaden();
    }

    // ------------------------------------------------------------------
    // Einstellungen <-> UI
    // ------------------------------------------------------------------

    private void EinstellungenInUiLaden()
    {
        TxtSdUrl.Text = _einst.SdServerUrl;
        TxtSdUrlPony.Text = _einst.SdServerUrlPony;
        TxtCfgPony.Text = _einst.CfgPony.ToString();
        TxtSampleMethodPony.Text = _einst.SampleMethodPony;
        TxtLoraPfadPony.Text = _einst.LoraPfadPony;
        TxtLoraGewichtPony.Text = _einst.LoraGewichtPony.ToString();
        TxtOllamaUrl.Text = _einst.OllamaUrl;
        TxtOllamaModell.Text = _einst.OllamaModell;
        TxtTimeout.Text = _einst.TimeoutSekunden.ToString();
        TxtOrdner.Text = _einst.SpeicherOrdner;
        ChkAutoSpeichern.IsChecked = _einst.AutomatischSpeichern;
        ChkPromptDatei.IsChecked = _einst.PromptDateiMitspeichern;
        TxtNegativ.Text = _einst.NegativPrompt;

        _formatWirdGesetzt = true;
        TxtBreite.Text = _einst.Breite.ToString();
        TxtHoehe.Text = _einst.Hoehe.ToString();
        _formatWirdGesetzt = false;
        FormatComboAnGroesseAnpassen();

        var istPony = _einst.AktivesModell == "pony";
        RbtnPony.IsChecked = istPony;
        RbtnFlux.IsChecked = !istPony;
        TxtSchritte.Text = (istPony ? _einst.SchrittePony : _einst.Schritte).ToString();
        ChkScoreTags.IsChecked = istPony;
    }

    private bool AktivesModellIstPony => RbtnPony.IsChecked == true;

    private bool UiInEinstellungenUebernehmen(bool leise = false)
    {
        void Meldung(string t) { if (!leise) Fehler(t); }

        if (!int.TryParse(TxtBreite.Text.Trim(), out var b) || b < 64 || b > 4096 ||
            !int.TryParse(TxtHoehe.Text.Trim(), out var h) || h < 64 || h > 4096)
        {
            Meldung("Breite und Höhe müssen Zahlen zwischen 64 und 4096 sein.");
            return false;
        }
        if (!int.TryParse(TxtSchritte.Text.Trim(), out var s) || s < 1 || s > 100)
        {
            Meldung("Schritte müssen eine Zahl zwischen 1 und 100 sein.");
            return false;
        }
        if (!int.TryParse(TxtTimeout.Text.Trim(), out var t) || t < 10)
        {
            Meldung("Das Zeitlimit muss mindestens 10 Sekunden betragen.");
            return false;
        }
        if (!Uri.TryCreate(TxtSdUrl.Text.Trim(), UriKind.Absolute, out _) ||
            !Uri.TryCreate(TxtSdUrlPony.Text.Trim(), UriKind.Absolute, out _) ||
            !Uri.TryCreate(TxtOllamaUrl.Text.Trim(), UriKind.Absolute, out _))
        {
            Meldung("sd-server-URL (FLUX und Pony) und Ollama-URL müssen vollständige Adressen sein (z. B. http://192.168.188.181:7860).");
            return false;
        }
        if (!double.TryParse(TxtCfgPony.Text.Trim(), out var cfgPony) || cfgPony <= 0)
        {
            Meldung("Pony-CFG muss eine Zahl größer 0 sein.");
            return false;
        }
        if (!double.TryParse(TxtLoraGewichtPony.Text.Trim(), out var loraGewicht) || loraGewicht <= 0)
        {
            Meldung("Pony-LoRA-Gewicht muss eine Zahl größer 0 sein.");
            return false;
        }
        if (string.IsNullOrWhiteSpace(TxtSampleMethodPony.Text) || string.IsNullOrWhiteSpace(TxtLoraPfadPony.Text))
        {
            Meldung("Pony-Sampler und Pony-LoRA-Datei dürfen nicht leer sein.");
            return false;
        }

        _einst.Breite = b;
        _einst.Hoehe = h;
        // TxtSchritte ist ein gemeinsames Feld fuer beide Modelle (siehe
        // Modell_Changed) - beim Speichern in das gerade aktive Modell schreiben.
        if (AktivesModellIstPony) _einst.SchrittePony = s; else _einst.Schritte = s;
        _einst.TimeoutSekunden = t;
        _einst.SdServerUrl = TxtSdUrl.Text.Trim();
        _einst.SdServerUrlPony = TxtSdUrlPony.Text.Trim();
        _einst.CfgPony = cfgPony;
        _einst.SampleMethodPony = TxtSampleMethodPony.Text.Trim();
        _einst.LoraPfadPony = TxtLoraPfadPony.Text.Trim();
        _einst.LoraGewichtPony = loraGewicht;
        _einst.AktivesModell = AktivesModellIstPony ? "pony" : "flux";
        _einst.OllamaUrl = TxtOllamaUrl.Text.Trim();
        _einst.OllamaModell = TxtOllamaModell.Text.Trim();
        _einst.SpeicherOrdner = TxtOrdner.Text.Trim();
        _einst.AutomatischSpeichern = ChkAutoSpeichern.IsChecked == true;
        _einst.PromptDateiMitspeichern = ChkPromptDatei.IsChecked == true;
        _einst.NegativPrompt = TxtNegativ.Text.Trim();
        return true;
    }

    private void BtnEinstellungenSpeichern_Click(object sender, RoutedEventArgs e)
    {
        if (!UiInEinstellungenUebernehmen()) return;
        try
        {
            _einst.Speichern();
            Status("Einstellungen gespeichert.");
        }
        catch (Exception ex)
        {
            Fehler("Einstellungen konnten nicht gespeichert werden: " + ex.Message);
        }
    }

    private void Fenster_Closing(object? sender, System.ComponentModel.CancelEventArgs e)
    {
        _cts?.Cancel();
        if (UiInEinstellungenUebernehmen(leise: true))
        {
            try { _einst.Speichern(); } catch { /* beim Schließen nicht stören */ }
        }
    }

    // ------------------------------------------------------------------
    // Format-Auswahl
    // ------------------------------------------------------------------

    private void CmbFormat_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_formatWirdGesetzt) return;
        if (CmbFormat.SelectedItem is not ComboBoxItem item) return;
        var tag = item.Tag as string;
        if (string.IsNullOrEmpty(tag)) return; // "Eigene Größe"

        var teile = tag.Split('x');
        _formatWirdGesetzt = true;
        TxtBreite.Text = teile[0];
        TxtHoehe.Text = teile[1];
        _formatWirdGesetzt = false;
    }

    private void Groesse_TextChanged(object sender, TextChangedEventArgs e)
    {
        if (_formatWirdGesetzt) return;
        FormatComboAnGroesseAnpassen();
    }

    private void FormatComboAnGroesseAnpassen()
    {
        var tag = $"{TxtBreite.Text.Trim()}x{TxtHoehe.Text.Trim()}";
        _formatWirdGesetzt = true;
        var passend = CmbFormat.Items.OfType<ComboBoxItem>().FirstOrDefault(i => (i.Tag as string) == tag);
        CmbFormat.SelectedItem = passend ?? CmbFormat.Items.OfType<ComboBoxItem>().Last();
        _formatWirdGesetzt = false;
    }

    private void ChkHochformat_Changed(object sender, RoutedEventArgs e)
    {
        var text = TxtDeutsch.Text.TrimStart();
        var hat = text.StartsWith(HochformatPraefix.TrimEnd(), StringComparison.OrdinalIgnoreCase);
        if (ChkHochformat.IsChecked == true && !hat)
            TxtDeutsch.Text = HochformatPraefix + text;
        else if (ChkHochformat.IsChecked != true && hat)
            TxtDeutsch.Text = Regex.Replace(text, @"^Hochformat,?\s*", "", RegexOptions.IgnoreCase);
    }

    private void Modell_Changed(object sender, RoutedEventArgs e)
    {
        if (TxtSchritte == null) return; // feuert schon waehrend InitializeComponent()
        var wechseltZuPony = AktivesModellIstPony;
        // Aktuellen Wert im bisherigen Modell sichern, bevor das Feld ueberschrieben wird
        // (TxtSchritte ist ein gemeinsames Feld fuer FLUX/Pony, siehe UiInEinstellungenUebernehmen).
        if (int.TryParse(TxtSchritte.Text.Trim(), out var aktuell))
        {
            if (wechseltZuPony) _einst.Schritte = aktuell; else _einst.SchrittePony = aktuell;
        }
        TxtSchritte.Text = (wechseltZuPony ? _einst.SchrittePony : _einst.Schritte).ToString();
        ChkScoreTags.IsChecked = wechseltZuPony;
    }

    // ------------------------------------------------------------------
    // Übersetzen & Generieren
    // ------------------------------------------------------------------

    private async void BtnUebersetzen_Click(object sender, RoutedEventArgs e)
    {
        if (!UiInEinstellungenUebernehmen()) return;
        var deutsch = TxtDeutsch.Text.Trim();
        if (deutsch.Length == 0) { Fehler("Bitte zuerst eine deutsche Bildbeschreibung eingeben."); return; }

        Beschaeftigt(true);
        try
        {
            var englisch = await UebersetzeAsync(deutsch, _cts!.Token);
            TxtEnglisch.Text = englisch;
            Status("Übersetzung fertig – bei Bedarf korrigieren, dann „Bild erzeugen“.");
        }
        catch (OperationCanceledException) { Status("Abgebrochen."); }
        catch (Exception ex) { Fehler(ex.Message); }
        finally { Beschaeftigt(false); }
    }

    private async void BtnGenerieren_Click(object sender, RoutedEventArgs e)
    {
        if (!UiInEinstellungenUebernehmen()) return;

        var deutsch = TxtDeutsch.Text.Trim();
        var englisch = TxtEnglisch.Text.Trim();
        if (deutsch.Length == 0 && englisch.Length == 0)
        {
            Fehler("Bitte eine Bildbeschreibung eingeben.");
            return;
        }

        Beschaeftigt(true);
        try
        {
            var ct = _cts!.Token;

            // Englisches Feld leer oder deutscher Text seit der letzten Übersetzung geändert -> neu übersetzen.
            if (englisch.Length == 0 || (deutsch.Length > 0 && deutsch != _letzterPromptDe && englisch == _letzterPromptEn))
            {
                englisch = await UebersetzeAsync(deutsch, ct);
                TxtEnglisch.Text = englisch;
            }

            var istPony = AktivesModellIstPony;
            // Score-Tags werden NICHT in TxtEnglisch geschrieben (fruehere Version tat
            // das und fuehrte dazu, dass die "ist das Feld leer -> uebersetzen"-Pruefung
            // oben faelschlich ein bereits uebersetztes Feld annahm, obwohl nur die
            // Tag-Kette drinstand - die eigentliche Uebersetzung wurde uebersprungen).
            // Stattdessen wird die Kette erst hier, unmittelbar vor dem Versand,
            // vorangestellt - TxtEnglisch zeigt weiterhin die reine Uebersetzung.
            var promptZumSenden = (istPony && ChkScoreTags.IsChecked == true)
                ? PonyScoreTagsPraefix + englisch
                : englisch;

            Status(istPony ? "Bild-Job wird an sd-server (Pony) geschickt …" : "Bild-Job wird an sd-server geschickt …");
            var fortschritt = new Progress<string>(Status);
            var bytes = await _sd.GeneriereAsync(
                istPony ? _einst.SdServerUrlPony : _einst.SdServerUrl,
                promptZumSenden, _einst.NegativPrompt,
                _einst.Breite, _einst.Hoehe,
                istPony ? _einst.SchrittePony : _einst.Schritte,
                TimeSpan.FromSeconds(_einst.TimeoutSekunden), fortschritt, ct,
                sampleMethod: istPony ? _einst.SampleMethodPony : null,
                cfgScale: istPony ? _einst.CfgPony : null,
                lora: istPony
                    ? new[] { new SdServerClient.LoraEintrag { Path = _einst.LoraPfadPony, Multiplier = _einst.LoraGewichtPony } }
                    : null);

            BildAnzeigen(bytes);
            _letzterPromptDe = deutsch;
            _letzterPromptEn = englisch;
            _letzteGenerierungIstPony = istPony;

            if (_einst.AutomatischSpeichern)
            {
                var pfad = AutomatischSpeichern(bytes, deutsch, promptZumSenden);
                LblGespeichert.Text = "Gespeichert: " + Path.GetFileName(pfad);
                LblGespeichert.ToolTip = pfad;
                Status($"Fertig – gespeichert unter {pfad}");
            }
            else
            {
                LblGespeichert.Text = "Noch nicht gespeichert";
                LblGespeichert.ToolTip = null;
                Status("Fertig – Bild mit „Speichern unter…“ ablegen.");
            }
        }
        catch (OperationCanceledException) { Status("Abgebrochen."); }
        catch (HttpRequestException ex)
        {
            Fehler($"Server nicht erreichbar: {ex.Message}\n\nLäuft der Container auf Athene? Adressen unter „Einstellungen“ prüfen.");
        }
        catch (Exception ex) { Fehler(ex.Message); }
        finally { Beschaeftigt(false); }
    }

    private async Task<string> UebersetzeAsync(string deutsch, CancellationToken ct)
    {
        Status($"Übersetze mit Ollama ({_einst.OllamaModell}) …");
        var englisch = await _uebersetzer.UebersetzeAsync(_einst.OllamaUrl, _einst.OllamaModell, deutsch, ct);
        _letzterPromptDe = deutsch;
        _letzterPromptEn = englisch;
        return englisch;
    }

    private void BtnAbbrechen_Click(object sender, RoutedEventArgs e)
    {
        _cts?.Cancel();
        Status("Abbruch angefordert …");
    }

    // ------------------------------------------------------------------
    // Bild anzeigen / speichern
    // ------------------------------------------------------------------

    private void BildAnzeigen(byte[] bytes)
    {
        _bildBytes = bytes;
        var bmp = new BitmapImage();
        using (var ms = new MemoryStream(bytes))
        {
            bmp.BeginInit();
            bmp.CacheOption = BitmapCacheOption.OnLoad;
            bmp.StreamSource = ms;
            bmp.EndInit();
        }
        bmp.Freeze();
        ImgErgebnis.Source = bmp;
        LblPlatzhalter.Visibility = Visibility.Collapsed;
        BtnSpeichernUnter.IsEnabled = true;
        BtnKopieren.IsEnabled = true;
    }

    private string AutomatischSpeichern(byte[] bytes, string deutsch, string englisch)
    {
        Directory.CreateDirectory(_einst.SpeicherOrdner);
        var name = $"{DateTime.Now:yyyyMMdd_HHmmss}_{Dateikuerzel(deutsch.Length > 0 ? deutsch : englisch)}.png";
        var pfad = Path.Combine(_einst.SpeicherOrdner, name);
        File.WriteAllBytes(pfad, bytes);
        if (_einst.PromptDateiMitspeichern)
            PromptDateiSchreiben(
                Path.ChangeExtension(pfad, ".txt"), deutsch, englisch,
                _letzteGenerierungIstPony ? _einst.SchrittePony : _einst.Schritte);
        return pfad;
    }

    private void BtnSpeichernUnter_Click(object sender, RoutedEventArgs e)
    {
        if (_bildBytes is null) return;
        var dlg = new SaveFileDialog
        {
            Title = "Bild speichern",
            Filter = "PNG-Bild (*.png)|*.png",
            DefaultExt = ".png",
            FileName = $"{DateTime.Now:yyyyMMdd_HHmmss}_{Dateikuerzel(_letzterPromptDe.Length > 0 ? _letzterPromptDe : _letzterPromptEn)}.png",
            InitialDirectory = Directory.Exists(_einst.SpeicherOrdner) ? _einst.SpeicherOrdner : null,
        };
        if (dlg.ShowDialog(this) != true) return;

        try
        {
            File.WriteAllBytes(dlg.FileName, _bildBytes);
            if (_einst.PromptDateiMitspeichern)
                PromptDateiSchreiben(
                    Path.ChangeExtension(dlg.FileName, ".txt"), _letzterPromptDe, _letzterPromptEn,
                    _letzteGenerierungIstPony ? _einst.SchrittePony : _einst.Schritte);
            LblGespeichert.Text = "Gespeichert: " + Path.GetFileName(dlg.FileName);
            LblGespeichert.ToolTip = dlg.FileName;
            Status($"Gespeichert unter {dlg.FileName}");
        }
        catch (Exception ex) { Fehler("Speichern fehlgeschlagen: " + ex.Message); }
    }

    private void PromptDateiSchreiben(string pfad, string deutsch, string englisch, int schritte)
    {
        var sb = new StringBuilder();
        sb.AppendLine($"Erstellt: {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
        sb.AppendLine($"Größe: {_einst.Breite}x{_einst.Hoehe}, Schritte: {schritte}");
        sb.AppendLine();
        sb.AppendLine("[Deutsch]");
        sb.AppendLine(deutsch);
        sb.AppendLine();
        sb.AppendLine("[Englisch – an sd-server gesendet]");
        sb.AppendLine(englisch);
        sb.AppendLine();
        sb.AppendLine("[Negativ-Prompt]");
        sb.AppendLine(_einst.NegativPrompt);
        File.WriteAllText(pfad, sb.ToString(), Encoding.UTF8);
    }

    private void BtnKopieren_Click(object sender, RoutedEventArgs e)
    {
        if (ImgErgebnis.Source is BitmapSource quelle)
        {
            Clipboard.SetImage(quelle);
            Status("Bild in die Zwischenablage kopiert.");
        }
    }

    private void BtnOrdnerOeffnen_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            Directory.CreateDirectory(_einst.SpeicherOrdner);
            Process.Start(new ProcessStartInfo("explorer.exe", $"\"{_einst.SpeicherOrdner}\"") { UseShellExecute = true });
        }
        catch (Exception ex) { Fehler("Ordner konnte nicht geöffnet werden: " + ex.Message); }
    }

    private void BtnOrdnerWaehlen_Click(object sender, RoutedEventArgs e)
    {
        var dlg = new OpenFolderDialog
        {
            Title = "Speicherordner wählen",
            InitialDirectory = Directory.Exists(TxtOrdner.Text) ? TxtOrdner.Text : null,
        };
        if (dlg.ShowDialog(this) == true)
            TxtOrdner.Text = dlg.FolderName;
    }

    // ------------------------------------------------------------------
    // Hilfsfunktionen
    // ------------------------------------------------------------------

    /// <summary>Macht aus dem Prompt ein kurzes, dateisystem-taugliches Namensstück.</summary>
    private static string Dateikuerzel(string prompt)
    {
        var text = Regex.Replace(prompt, @"^Hochformat,?\s*", "", RegexOptions.IgnoreCase);
        text = text.Replace('ä', 'a').Replace('ö', 'o').Replace('ü', 'u').Replace('ß', 's')
                   .Replace('Ä', 'A').Replace('Ö', 'O').Replace('Ü', 'U');
        text = Regex.Replace(text, @"[^A-Za-z0-9]+", "_").Trim('_');
        if (text.Length > 40) text = text[..40].TrimEnd('_');
        return text.Length == 0 ? "bild" : text;
    }

    private void Beschaeftigt(bool an)
    {
        if (an)
        {
            _cts?.Dispose();
            _cts = new CancellationTokenSource();
        }
        BtnGenerieren.IsEnabled = !an;
        BtnUebersetzen.IsEnabled = !an;
        BtnAbbrechen.IsEnabled = an;
        PrgStatus.IsIndeterminate = an;
        PrgStatus.Visibility = an ? Visibility.Visible : Visibility.Hidden;
        Cursor = an ? System.Windows.Input.Cursors.AppStarting : null;
    }

    private void Status(string text) => LblStatus.Text = text;

    private void Fehler(string text)
    {
        Status("Fehler: " + text.Split('\n')[0]);
        MessageBox.Show(this, text, "BildKI", MessageBoxButton.OK, MessageBoxImage.Warning);
    }
}
