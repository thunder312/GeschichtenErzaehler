// Signalton "Geschichte fertig" (Option "Sound bei Fertigstellung" im
// Automatikmodus). Per Web Audio erzeugt statt aus einer Audio-Datei - kein
// Asset, kein Lizenz-/Ladeproblem.
//
// Browser geben Audio erst nach einer Nutzer-Interaktion frei: der
// AudioContext wird deshalb beim Klick auf "Automatikmodus starten"
// angelegt/geweckt (soundFreischalten), spaeter - Stunden danach, beim
// Lauf-Ende - darf er dann auch ohne Klick klingen.

let kontext: AudioContext | null = null;

function ctx(): AudioContext | null {
  try {
    if (!kontext) {
      const Ctor =
        window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctor) return null;
      kontext = new Ctor();
    }
    return kontext;
  } catch {
    return null;
  }
}

/** Beim Klick auf "Starten" aufrufen, damit der Ton spaeter erlaubt ist. */
export function soundFreischalten(): void {
  const c = ctx();
  if (c && c.state === "suspended") void c.resume().catch(() => {});
}

// C-Dur-Akkord aufsteigend (C5-E5-G5-C6), am Ende ein ausklingender Ton.
const NOTEN_HZ = [523.25, 659.25, 783.99, 1046.5];

/** Spielt den Fertig-Ton (ca. 2,5 s). Schlaegt still fehl, wenn der Browser
 * Audio nicht erlaubt. */
export function fertigSoundAbspielen(): void {
  const c = ctx();
  if (!c) return;
  void c.resume().catch(() => {});
  const start = c.currentTime + 0.05;
  NOTEN_HZ.forEach((hz, i) => {
    const t0 = start + i * 0.28;
    const letzter = i === NOTEN_HZ.length - 1;
    const dauer = letzter ? 1.4 : 0.5;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = "sine";
    osc.frequency.value = hz;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.25, t0 + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dauer);
    osc.connect(gain).connect(c.destination);
    osc.start(t0);
    osc.stop(t0 + dauer + 0.05);
  });
}
