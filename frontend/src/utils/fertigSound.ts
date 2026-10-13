// Signalton "Geschichte fertig" (Option "Signalton" im Automatikmodus). Alle
// Sounds werden per Web Audio erzeugt statt aus Audio-Dateien - kein Asset,
// kein Lizenz-/Ladeproblem. Die Auswahl (soundWaehlen) wird im Browser
// gemerkt und gilt beim Lauf-Ende.
//
// Browser geben Audio erst nach einer Nutzer-Interaktion frei: der
// AudioContext wird deshalb beim Klick auf "Starten"/"Vorhören"
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

// ---------------------------------------------------------------------------
// Bausteine

type Ziel = AudioNode;

interface TonOptionen {
  hz: number;
  start: number; // absolute Zeit im AudioContext
  dauer: number;
  typ?: OscillatorType;
  gain?: number;
  attack?: number;
  /** Frequenz gleitet bis zum Ende der Dauer auf diesen Wert. */
  gleitZu?: number;
  /** Tiefpass-Grenzfrequenz (Hz); sie faellt wie bei gezupften Saiten ab. */
  filterStart?: number;
  filterEnde?: number;
  vibratoHz?: number;
  vibratoTiefe?: number; // in Hz
  verstimmt?: number; // in Cent, fuer Schwebung
}

function ton(c: AudioContext, ziel: Ziel, o: TonOptionen): void {
  const osc = c.createOscillator();
  const gain = c.createGain();
  osc.type = o.typ ?? "sine";
  osc.frequency.setValueAtTime(o.hz, o.start);
  if (o.gleitZu) osc.frequency.exponentialRampToValueAtTime(o.gleitZu, o.start + o.dauer);
  if (o.verstimmt) osc.detune.value = o.verstimmt;
  const spitze = o.gain ?? 0.25;
  const attack = o.attack ?? 0.02;
  gain.gain.setValueAtTime(0.0001, o.start);
  gain.gain.exponentialRampToValueAtTime(spitze, o.start + attack);
  gain.gain.exponentialRampToValueAtTime(0.0001, o.start + o.dauer);

  let ausgang: AudioNode = osc;
  if (o.filterStart) {
    const f = c.createBiquadFilter();
    f.type = "lowpass";
    f.frequency.setValueAtTime(o.filterStart, o.start);
    if (o.filterEnde) f.frequency.exponentialRampToValueAtTime(o.filterEnde, o.start + o.dauer);
    osc.connect(f);
    ausgang = f;
  }
  ausgang.connect(gain).connect(ziel);

  if (o.vibratoHz) {
    const lfo = c.createOscillator();
    const tiefe = c.createGain();
    lfo.frequency.value = o.vibratoHz;
    tiefe.gain.value = o.vibratoTiefe ?? o.hz * 0.01;
    lfo.connect(tiefe).connect(osc.frequency);
    lfo.start(o.start);
    lfo.stop(o.start + o.dauer + 0.05);
  }
  osc.start(o.start);
  osc.stop(o.start + o.dauer + 0.05);
}

/** Weisses Rauschen (Becken, Hauch), durch einen Hochpass gefiltert. */
function rauschen(c: AudioContext, ziel: Ziel, start: number, dauer: number, gain: number, hochpassHz: number): void {
  const laenge = Math.ceil(c.sampleRate * dauer);
  const puffer = c.createBuffer(1, laenge, c.sampleRate);
  const daten = puffer.getChannelData(0);
  for (let i = 0; i < laenge; i++) daten[i] = Math.random() * 2 - 1;
  const quelle = c.createBufferSource();
  quelle.buffer = puffer;
  const filter = c.createBiquadFilter();
  filter.type = "highpass";
  filter.frequency.value = hochpassHz;
  const g = c.createGain();
  g.gain.setValueAtTime(gain, start);
  g.gain.exponentialRampToValueAtTime(0.0001, start + dauer);
  quelle.connect(filter).connect(g).connect(ziel);
  quelle.start(start);
  quelle.stop(start + dauer + 0.05);
}

/** Uebersteuerung fuer Gitarrenklaenge. */
function verzerrer(c: AudioContext, staerke: number): WaveShaperNode {
  const w = c.createWaveShaper();
  const n = 1024;
  const kurve = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const x = (i * 2) / n - 1;
    kurve[i] = Math.tanh(x * staerke);
  }
  w.curve = kurve;
  w.oversample = "4x";
  return w;
}

const mtof = (midi: number) => 440 * Math.pow(2, (midi - 69) / 12);

// ---------------------------------------------------------------------------
// Sounds

type SpielFn = (c: AudioContext, ziel: Ziel, t0: number) => void;

export interface SoundEintrag {
  id: string;
  name: string;
  gruppe: "Allgemein" | "Themen";
  /** Lautstaerke-Angleichung (Faktor), per Offline-Rendering auf aehnlichen RMS getrimmt. */
  pegel: number;
  spiel: SpielFn;
}

// C-Dur-Akkord aufsteigend (C5-E5-G5-C6), am Ende ein ausklingender Ton.
const standard: SpielFn = (c, ziel, t0) => {
  [523.25, 659.25, 783.99, 1046.5].forEach((hz, i, a) => {
    const letzter = i === a.length - 1;
    ton(c, ziel, { hz, start: t0 + i * 0.28, dauer: letzter ? 1.4 : 0.5, gain: 0.25, attack: 0.03 });
  });
};

// Glocke: unharmonische Teiltoene, lange Ausklingzeit.
const glocke: SpielFn = (c, ziel, t0) => {
  const grund = 392; // G4
  [[1, 0.3], [2.76, 0.18], [5.4, 0.1], [8.93, 0.05]].forEach(([faktor, g]) => {
    ton(c, ziel, { hz: grund * faktor, start: t0, dauer: 3.2 / Math.sqrt(faktor), gain: g, attack: 0.005 });
  });
  [[1, 0.25], [2.76, 0.15]].forEach(([faktor, g]) => {
    ton(c, ziel, { hz: grund * 1.5 * faktor, start: t0 + 0.9, dauer: 2.4 / Math.sqrt(faktor), gain: g, attack: 0.005 });
  });
};

// Fanfare: Blechblaeser-aehnliche Saegezaehne (Tiefpass oeffnet sich), Dur-Dreiklang.
const fanfare: SpielFn = (c, ziel, t0) => {
  const note = (midi: number, start: number, dauer: number) =>
    ton(c, ziel, {
      hz: mtof(midi), start, dauer, typ: "sawtooth", gain: 0.12, attack: 0.04,
      filterStart: 500, filterEnde: 2400, verstimmt: 6,
    });
  note(60, t0, 0.22);
  note(60, t0 + 0.26, 0.22);
  note(64, t0 + 0.52, 0.22);
  [60, 64, 67, 72].forEach((m) => note(m, t0 + 0.8, 1.5));
};

// Marimba/Pling: kurze gezupfte Toene einer Pentatonik, aufsteigend.
const pling: SpielFn = (c, ziel, t0) => {
  [72, 74, 76, 79, 81, 84].forEach((m, i) => {
    ton(c, ziel, { hz: mtof(m), start: t0 + i * 0.13, dauer: 0.7, typ: "triangle", gain: 0.22, attack: 0.004 });
  });
};

// Kurzer Doppelton, dezent.
const ping: SpielFn = (c, ziel, t0) => {
  ton(c, ziel, { hz: 1318.5, start: t0, dauer: 0.45, gain: 0.2, attack: 0.005 });
  ton(c, ziel, { hz: 1760, start: t0 + 0.18, dauer: 0.9, gain: 0.2, attack: 0.005 });
};

// Spooky: absteigendes Theremin-Heulen mit Vibrato, Tritonus-Dissonanz, tiefer Glockenschlag.
const spooky: SpielFn = (c, ziel, t0) => {
  ton(c, ziel, {
    hz: 740, gleitZu: 330, start: t0, dauer: 2.4, gain: 0.16, attack: 0.5, vibratoHz: 5.5, vibratoTiefe: 14,
  });
  ton(c, ziel, {
    hz: 740 * 1.414, gleitZu: 330 * 1.414, start: t0 + 0.2, dauer: 2.2, gain: 0.08, attack: 0.6,
    vibratoHz: 4.8, vibratoTiefe: 16,
  });
  rauschen(c, ziel, t0 + 0.1, 2.4, 0.03, 4000);
  // Totenglocke: tiefes A mit unharmonischen Obertoenen.
  [[1, 0.3], [2.4, 0.15], [4.1, 0.08]].forEach(([faktor, g]) => {
    ton(c, ziel, { hz: 110 * faktor, start: t0 + 1.9, dauer: 3 / Math.sqrt(faktor), gain: g, attack: 0.01 });
  });
};

// Regency: Cembalo (gezupfter Saegezahn, Tiefpass faellt schnell), barocke Kadenz in D-Dur mit Triller.
const regency: SpielFn = (c, ziel, t0) => {
  const zupf = (midi: number, start: number, dauer = 0.9, gain = 0.1) => {
    ton(c, ziel, { hz: mtof(midi), start, dauer, typ: "sawtooth", gain, attack: 0.003, filterStart: 3500, filterEnde: 500 });
    ton(c, ziel, { hz: mtof(midi + 12), start, dauer: dauer * 0.6, typ: "triangle", gain: gain * 0.5, attack: 0.003 });
  };
  // Aufstieg D-E-F#-A
  [62, 64, 66, 69].forEach((m, i) => zupf(m, t0 + i * 0.16, 0.6));
  // Triller E-F# auf der Septime, dann Aufloesung
  [76, 74, 76, 74, 76].forEach((m, i) => zupf(m, t0 + 0.7 + i * 0.09, 0.4, 0.07));
  zupf(74, t0 + 1.2, 0.9, 0.09);
  // Schlussakkord D-Dur
  [50, 62, 66, 69, 74].forEach((m) => zupf(m, t0 + 1.55, 1.8, 0.09));
};

// Metal: verzerrte Powerchords (E5), Palm-Mutes, Schlussakkord mit Crash-Becken.
const metal: SpielFn = (c, ziel, t0) => {
  const dist = verzerrer(c, 6);
  const tp = c.createBiquadFilter();
  tp.type = "lowpass";
  tp.frequency.value = 3200;
  dist.connect(tp).connect(ziel);
  const power = (grundMidi: number, start: number, dauer: number, gain: number) => {
    [0, 7, 12].forEach((halb) => {
      ton(c, dist, { hz: mtof(grundMidi + halb), start, dauer, typ: "sawtooth", gain, attack: 0.004, verstimmt: 5 });
      ton(c, dist, { hz: mtof(grundMidi + halb), start, dauer, typ: "sawtooth", gain: gain * 0.8, attack: 0.004, verstimmt: -5 });
    });
  };
  // Gallop: kurz-kurz-lang (E, E, G) mit Palm-Mute
  power(40, t0, 0.12, 0.05);
  power(40, t0 + 0.16, 0.12, 0.05);
  power(40, t0 + 0.32, 0.12, 0.05);
  power(43, t0 + 0.55, 0.12, 0.05);
  power(45, t0 + 0.71, 0.12, 0.05);
  power(47, t0 + 0.87, 0.18, 0.05);
  // Finale: E-Powerchord laut + Crash + Basstrommel-Schlag
  power(40, t0 + 1.2, 2.2, 0.06);
  rauschen(c, ziel, t0 + 1.2, 2.2, 0.35, 5000);
  ton(c, ziel, { hz: 120, gleitZu: 40, start: t0 + 1.2, dauer: 0.35, gain: 0.7, attack: 0.002 });
};

// Blues: Blue-Note-Lick (Moll-Terz bendet in die Dur-Terz), danach A7-Schlussakkord.
const blues: SpielFn = (c, ziel, t0) => {
  const gitarre = (midi: number, start: number, dauer: number, opt: Partial<TonOptionen> = {}) =>
    ton(c, ziel, {
      hz: mtof(midi), start, dauer, typ: "sawtooth", gain: 0.1, attack: 0.01,
      filterStart: 2400, filterEnde: 600, vibratoHz: 5, vibratoTiefe: mtof(midi) * 0.006, ...opt,
    });
  gitarre(57, t0, 0.3); // A3
  gitarre(60, t0 + 0.32, 0.3); // C4 (b3)
  gitarre(62, t0 + 0.64, 0.3); // D4
  gitarre(63, t0 + 0.96, 0.3); // Eb4 (blue note)
  gitarre(63, t0 + 1.28, 0.6, { gleitZu: mtof(64) }); // Bend Eb -> E
  // A7-Schlussakkord, leicht arpeggiert
  [45, 52, 57, 61, 64, 67].forEach((m, i) => gitarre(m, t0 + 2.0 + i * 0.05, 2.2, { gain: 0.07, vibratoHz: 0 }));
};

export const SOUND_LISTE: SoundEintrag[] = [
  { id: "standard", name: "Standard (Akkord)", gruppe: "Allgemein", pegel: 1, spiel: standard },
  { id: "glocke", name: "Glocke", gruppe: "Allgemein", pegel: 0.7, spiel: glocke },
  { id: "fanfare", name: "Fanfare", gruppe: "Allgemein", pegel: 1.7, spiel: fanfare },
  { id: "pling", name: "Pling (Marimba)", gruppe: "Allgemein", pegel: 1.1, spiel: pling },
  { id: "ping", name: "Ping (dezent)", gruppe: "Allgemein", pegel: 1.6, spiel: ping },
  { id: "spooky", name: "Spooky", gruppe: "Themen", pegel: 0.8, spiel: spooky },
  { id: "regency", name: "Regency (Cembalo)", gruppe: "Themen", pegel: 1.3, spiel: regency },
  { id: "metal", name: "Metal", gruppe: "Themen", pegel: 0.5, spiel: metal },
  { id: "blues", name: "Blues", gruppe: "Themen", pegel: 1.7, spiel: blues },
];

const SPEICHER_SCHLUESSEL = "automatikFertigSoundId";

export function gewaehlterSound(): string {
  try {
    const id = localStorage.getItem(SPEICHER_SCHLUESSEL);
    if (id && SOUND_LISTE.some((s) => s.id === id)) return id;
  } catch {
    /* ohne Speicher gilt der Standard */
  }
  return "standard";
}

export function soundWaehlen(id: string): void {
  try {
    localStorage.setItem(SPEICHER_SCHLUESSEL, id);
  } catch {
    /* ohne Speicher einfach nicht merken */
  }
}

/** Spielt den gewaehlten (oder angegebenen) Sound. Schlaegt still fehl, wenn
 * der Browser Audio nicht erlaubt. */
export function fertigSoundAbspielen(id: string = gewaehlterSound()): void {
  const c = ctx();
  if (!c) return;
  void c.resume().catch(() => {});
  const eintrag = SOUND_LISTE.find((s) => s.id === id) ?? SOUND_LISTE[0];
  // Gemeinsamer Ausgang mit Kompressor, damit verzerrte/laute Sounds nicht
  // uebersteuern und alle Sounds ungefaehr gleich laut sind.
  const kompressor = c.createDynamicsCompressor();
  const master = c.createGain();
  master.gain.value = 0.9 * eintrag.pegel;
  kompressor.connect(master).connect(c.destination);
  eintrag.spiel(c, kompressor, c.currentTime + 0.05);
}
