// Start-Skelett fuer den Weg "Gerüst selbst schreiben" (Alternative zum
// Architekten-Interview, siehe ProjektePage.tsx "Neues Projekt anlegen").
// Struktur 1:1 nach dem "## Ausgabe"-Abschnitt in
// backend/app/data/personas/architekt.txt (bzw. der epochenspezifischen
// Kopie) - exakt das Dokument, das am Ende eines gefuehrten Interviews
// entsteht, nur mit Platzhaltern statt fertigem Inhalt. Bewusst OHNE
// "## Kapitelplan"-Ueberschrift: geruest_schreiben() im Backend (siehe
// app/api/projects.py) lehnt ein deklariertes Kapitel ohne Zielwortzahl per
// kapitelplan_pruefen() ab - ein hier mitgeliefertes, noch unbefuelltes
// Startkapitel wuerde also den allerersten (in anlegen() unten sofort
// ausgeloesten) Speicherversuch scheitern lassen und der try/catch dort
// wuerde das Scheitern verschlucken, sodass das Projekt am Ende OHNE
// geruest.md dastuende. Das erste, noch leere Kapitel bekommt der Nutzer
// stattdessen automatisch beim Oeffnen des Gerüst-Editors (siehe
// GeruestPage.tsx), wo es erst beim tatsaechlichen Speichern validiert wird.
//
// Die drei woertlichen Pflicht-Marker (Jugendschutz-Stufe, Autor-Modell,
// Automatische Fortsetzung) sind mit sinnvollen Standardwerten vorbelegt
// (siehe backend/app/core/geruest.py: genau diese Werte liefern die
// *_erkennen()-Funktionen ohnehin als Fallback, wenn das Feld fehlt oder
// unlesbar ist - hier stehen sie nur bereits sichtbar und korrekt
// geschrieben, statt dass der Nutzer die exakte Syntax erraten muss).

// Ort/Zeitraum, die bei der Epochen-Erstellung frei eingegeben wurden (siehe
// backend/app/core/epoche.py:EpocheAntworten.orte/.zeitraum) - werden dort
// NICHT strukturiert gespeichert, sondern landen nur eingebettet im
// generierten architekt.txt-Fliesstext (Fragenkatalog Punkt 4/5). Diese
// beiden Saetze sind beim Erzeugen wortgleich fest verdrahtet, siehe
// architekt_vorlage() dort - eine Epoche, deren architekt.txt seither frei
// umformuliert wurde, liefert hier einfach nichts (best effort, kein Fehler).
export function epochenAnhaltspunkteAusArchitektTxt(
  architektText: string,
): { ort: string | null; zeitraum: string | null } {
  const ort = architektText.match(/Ort und Region:\s*([^\n]+?)\.\s*Fiktiv oder an reale Orte angelehnt\?/i);
  const zeitraum = architektText.match(/Zeitangabe:\s*([^\n]+?)\.\s*Wichtig, weil daran später die Prüfung hängt\.?/i);
  return {
    ort: ort ? ort[1].trim() : null,
    zeitraum: zeitraum ? zeitraum[1].trim() : null,
  };
}

export interface EpochenAnhaltspunkte {
  ort?: string | null;
  zeitraum?: string | null;
  genre?: string | null;
}

export function leeresGeruestSkelett(titel: string, epoche?: EpochenAnhaltspunkte): string {
  const titelZeile = titel.trim() || "[Arbeitstitel]";
  const zeitangabeZeile = epoche?.zeitraum
    ? `*   **Zeitangabe:** Jahr [genaue vierstellige Jahreszahl eintragen, passend zu "${epoche.zeitraum}"]`
    : `*   **Zeitangabe:** Jahr [hier die vierstellige Jahreszahl eintragen]`;
  const ortZeile = epoche?.ort ? `*   **Ort:** ${epoche.ort}` : `*   **Ort:** [Schauplatz]`;
  const tonlageZeile = epoche?.genre
    ? `*   **Tonlage:** [z.B. leidenschaftlich, tragisch, leicht ...] (Genre-Prägung der Epoche: ${epoche.genre})`
    : `*   **Tonlage:** [z.B. leidenschaftlich, tragisch, leicht ...]`;

  return `# STORY-GERUEST

## Rahmen
${zeitangabeZeile}
${ortZeile}
*   **Erzählperspektive:** Dritte Person
*   **Tempus:** Vergangenheitsform
${tonlageZeile}
*   **Jugendschutz-Stufe:** Jugendschutz-Stufe: Voll
*   **Autor-Modell:** Autor-Modell: Mistral
*   **Automatische Fortsetzung:** Automatische Fortsetzung: Aus

## Titel
${titelZeile}

## Unerhörte Begebenheit
[Das eine ungewöhnliche Ereignis, auf das alle Kapitel zulaufen oder aus dem sie folgen - ein Satz.]

## Figuren
*   **[Name]:** Alter: [Zahl]. [Rang/Titel/Stand]: [...]. Ziel: [...]. Größte Angst: [...]. Geheimnis: [...]. Entwicklungsbogen: [...].

## Konflikt
[Was will die Hauptfigur, was steht dagegen - ein Satz.]

## Nebenstrang

## Offene Punkte
[Fragen, die beim Schreiben noch zu klären sind - kann auch leer bleiben.]

## Regeln
Keine Prosa, keine Beispielsätze, keine Dialoge. Nur Struktur in Stichpunkten.
Das Jahr MUSS vierstellig im Gerüst stehen.
Die Jugendschutz-Stufe MUSS wörtlich "Jugendschutz-Stufe: Voll" oder "Jugendschutz-Stufe: Angedeutet" oder "Jugendschutz-Stufe: Jugendfrei" lauten.
Das LETZTE Kapitel im Kapitelplan MUSS die vollständige Auflösung des Kernkonflikts (und eines evtl. Nebenstrangs) enthalten, kein offener Cliffhanger.
`;
}
