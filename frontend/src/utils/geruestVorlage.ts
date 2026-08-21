// Start-Skelett fuer den Weg "Gerüst selbst schreiben" (Alternative zum
// Architekten-Interview, siehe ProjektePage.tsx "Neues Projekt anlegen").
// Struktur 1:1 nach dem "## Ausgabe"-Abschnitt in
// backend/app/data/personas/architekt.txt (bzw. der epochenspezifischen
// Kopie) - exakt das Dokument, das am Ende eines gefuehrten Interviews
// entsteht, nur mit Platzhaltern statt fertigem Inhalt. Bewusst OHNE
// "## Kapitelplan"-Ueberschrift: ein komplett fehlender Abschnitt ist laut
// kapitelplanAusGeruestExtrahieren()/kapitelplan_pruefen() kein Fehler,
// der Nutzer legt das erste Kapitel stattdessen bequem per "+ Kapitel" im
// (jetzt einklappbaren) KapitelplanEditor an, statt den Bullet-Syntax hier
// von Hand nachzubauen.
//
// Die drei woertlichen Pflicht-Marker (Jugendschutz-Stufe, Autor-Modell,
// Automatische Fortsetzung) sind mit sinnvollen Standardwerten vorbelegt
// (siehe backend/app/core/geruest.py: genau diese Werte liefern die
// *_erkennen()-Funktionen ohnehin als Fallback, wenn das Feld fehlt oder
// unlesbar ist - hier stehen sie nur bereits sichtbar und korrekt
// geschrieben, statt dass der Nutzer die exakte Syntax erraten muss).
export function leeresGeruestSkelett(titel: string): string {
  const titelZeile = titel.trim() || "[Arbeitstitel]";
  return `# STORY-GERUEST

## Rahmen
*   **Zeitangabe:** Jahr [hier die vierstellige Jahreszahl eintragen]
*   **Ort:** [Schauplatz]
*   **Erzählperspektive:** Dritte Person
*   **Tempus:** Vergangenheitsform
*   **Tonlage:** [z.B. leidenschaftlich, tragisch, leicht ...]
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
[Optional. Falls gewünscht: welche Indizien werden in welchem Kapitel gelegt, wie wird aufgelöst. Sonst diesen Abschnitt einfach löschen.]

## Offene Punkte
[Fragen, die beim Schreiben noch zu klären sind - kann auch leer bleiben.]

## Regeln
Keine Prosa, keine Beispielsätze, keine Dialoge. Nur Struktur in Stichpunkten.
Das Jahr MUSS vierstellig im Gerüst stehen.
Die Jugendschutz-Stufe MUSS wörtlich "Jugendschutz-Stufe: Voll" oder "Jugendschutz-Stufe: Angedeutet" oder "Jugendschutz-Stufe: Jugendfrei" lauten.
Das LETZTE Kapitel im Kapitelplan MUSS die vollständige Auflösung des Kernkonflikts (und eines evtl. Nebenstrangs) enthalten, kein offener Cliffhanger.
`;
}
