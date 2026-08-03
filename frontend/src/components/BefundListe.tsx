import type { Befund, BefundKategorie } from "../api/types";

export const KATEGORIE_LABEL: Record<BefundKategorie, string> = {
  anachronismus: "Anachronismus",
  stimmigkeit: "Stimmigkeit",
  kontinuitaet: "Kontinuität",
  lektorat: "Lektorat",
};

export const KATEGORIE_CHIP: Record<BefundKategorie, string> = {
  anachronismus: "border-amber-400/40 bg-amber-400/15 text-amber-200",
  stimmigkeit: "border-violet-400/40 bg-violet-400/15 text-violet-200",
  kontinuitaet: "border-sky-400/40 bg-sky-400/15 text-sky-200",
  lektorat: "border-emerald-400/40 bg-emerald-400/15 text-emerald-200",
};

interface BefundListeProps {
  befunde: Befund[];
  aktiveId?: string | null;
  onSelect?: (befund: Befund) => void;
  /** Fundstelle wurde nach dem Pruef-Lauf durch eine ueberlappende Aenderung
   * im Editor entfernt (siehe befundReview.ts:pruefeVerwaist) - z.B. weil
   * eine vorige Automatik-Korrektur genau diese Stelle bereits ersetzt hat.
   * Diese Funde werden komplett ausgeblendet statt nur markiert (getrennt
   * von "gefunden", das sich auf den Zustand direkt NACH dem Pruef-Lauf
   * bezieht, bevor ueberhaupt editiert wurde). */
  orphanIds?: Set<string>;
  uebernommenIds?: Set<string>;
  /** Nur uebergeben, wenn ein Ein-Klick-Apply-Button in der Liste angeboten
   * werden soll (BefundEditor) - ohne diese Prop (z.B. in SchreibenPage) ist
   * die Liste rein informativ. */
  onUebernehmen?: (befund: Befund) => void;
  /** Nur uebergeben, wenn zusaetzlich ein Sammel-Button "Alle Lektorat-Funde
   * uebernehmen" angeboten werden soll - Lektorat liefert typischerweise
   * viele kleine Einzelfunde pro Kapitel (Endungen, Kommata, Tippfehler),
   * anders als die meist wenigen Funde der anderen Kategorien. */
  onUebernehmenAlle?: (befunde: Befund[]) => void;
  /** Nur uebergeben, wenn die Liste Funde ueber MEHRERE Kapitel hinweg
   * zeigt (siehe PruefenAnwendenPage: EINE gemeinsame Liste fuer den
   * gesamten, ueber alle Kapitel durchlaufenden Editor) - liefert je Fund
   * die Kapitelnummer fuer ein kleines Badge vor den Kategorie-Chips. */
  kapitelVon?: (befund: Befund) => number;
}

function kannUebernommenWerden(befund: Befund, uebernommen: boolean): boolean {
  return befund.gefunden && !befund.konflikt && !!befund.vorschlag && !uebernommen;
}

export function BefundListe({
  befunde,
  aktiveId,
  onSelect,
  orphanIds,
  uebernommenIds,
  onUebernehmen,
  onUebernehmenAlle,
  kapitelVon,
}: BefundListeProps) {
  // Verwaiste Funde (Fundstelle stimmt nicht mehr mit dem aktuellen Text
  // ueberein, siehe befundReview.ts:pruefeVerwaist) sind i.d.R. bereits
  // durch eine automatische Korrektur behoben - als weiterhin "offen"
  // gelistet waeren sie nur verwirrend, da fuer sie ohnehin keine Aktion
  // mehr moeglich ist. Komplett ausgeblendet statt nur markiert.
  const versteckteAnzahl = orphanIds ? befunde.filter((b) => orphanIds.has(b.id)).length : 0;
  const sichtbareBefunde = orphanIds ? befunde.filter((b) => !orphanIds.has(b.id)) : befunde;

  if (sichtbareBefunde.length === 0) {
    return (
      <p className="text-sm text-text-muted">
        {versteckteAnzahl > 0
          ? `Keine offenen Befunde mehr (${versteckteAnzahl} bereits erledigt, Text wurde inzwischen geändert).`
          : "Keine Befunde."}
      </p>
    );
  }

  const lektoratSammelbar = sichtbareBefunde.filter(
    (b) => b.kategorien.includes("lektorat") && kannUebernommenWerden(b, uebernommenIds?.has(b.id) ?? false),
  );

  return (
    <div className="space-y-2">
      {versteckteAnzahl > 0 && (
        <p className="text-xs text-text-muted">
          {versteckteAnzahl} weitere(r) Fund/Funde ausgeblendet (bereits erledigt, Text wurde inzwischen geändert).
        </p>
      )}
      {onUebernehmenAlle && lektoratSammelbar.length > 1 && (
        <button
          type="button"
          onClick={() => onUebernehmenAlle(lektoratSammelbar)}
          className="w-full rounded-md border border-emerald-400/40 bg-emerald-400/15 px-2 py-1 text-xs font-medium text-emerald-200 hover:bg-emerald-400/25"
        >
          Alle {lektoratSammelbar.length} Lektorat-Funde übernehmen
        </button>
      )}
      <ul className="space-y-2">
      {sichtbareBefunde.map((befund) => {
        const uebernommen = uebernommenIds?.has(befund.id) ?? false;
        const kannUebernehmen = !!onUebernehmen && kannUebernommenWerden(befund, uebernommen);

        return (
          <li
            key={befund.id}
            onClick={onSelect ? () => onSelect(befund) : undefined}
            className={`rounded-lg border px-3 py-2 text-sm transition-colors ${
              befund.konflikt
                ? "border-red-400/40 bg-red-400/10"
                : "border-border bg-surface"
            } ${onSelect ? "cursor-pointer hover:bg-surface-hover" : ""} ${
              aktiveId === befund.id ? "ring-1 ring-accent" : ""
            }`}
          >
            <div className="mb-1 flex flex-wrap items-center gap-1.5">
              {kapitelVon && (
                <span className="rounded-full border border-border px-2 py-0.5 text-xs font-medium text-text-muted">
                  Kapitel {kapitelVon(befund)}
                </span>
              )}
              {befund.kategorien.map((k) => (
                <span key={k} className={`rounded-full border px-2 py-0.5 text-xs font-medium ${KATEGORIE_CHIP[k]}`}>
                  {KATEGORIE_LABEL[k]}
                </span>
              ))}
              {befund.sicherheit && (
                <span className="text-xs text-text-muted">Sicherheit: {befund.sicherheit}</span>
              )}
              {befund.konflikt && (
                <span className="rounded-full border border-red-400/40 bg-red-400/15 px-2 py-0.5 text-xs font-medium text-red-200">
                  Konflikt
                </span>
              )}
              {!befund.gefunden && (
                <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
                  Stelle im Text nicht gefunden
                </span>
              )}
              {uebernommen && (
                <span className="rounded-full border border-accent/40 bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent-light">
                  ✓ Übernommen
                </span>
              )}
            </div>

            <p className="mb-1 font-mono text-xs text-text-muted">„{befund.fundstelle}"</p>

            {befund.beschreibungen.map((b, i) => (
              <p key={i} className="text-text">
                <span className="text-text-muted">{KATEGORIE_LABEL[b.quelle as BefundKategorie] ?? b.quelle}:</span>{" "}
                {b.text}
              </p>
            ))}

            {befund.konflikt && befund.konflikt_vorschlaege ? (
              <div className="mt-1 space-y-0.5">
                <p className="text-xs text-text-muted">Widersprüchliche Vorschläge - manuell entscheiden:</p>
                {befund.konflikt_vorschlaege.map((v, i) => (
                  <p key={i} className="text-xs">
                    <span className="text-text-muted">{KATEGORIE_LABEL[v.quelle as BefundKategorie] ?? v.quelle}:</span>{" "}
                    „{v.text}"
                  </p>
                ))}
              </div>
            ) : befund.vorschlag ? (
              <div className="mt-1 flex items-center justify-between gap-2">
                <p className="text-xs">
                  <span className="text-text-muted">Vorschlag:</span> „{befund.vorschlag}"
                </p>
                {kannUebernehmen && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onUebernehmen?.(befund);
                    }}
                    className="shrink-0 rounded-md border border-accent/40 bg-accent-soft px-2 py-0.5 text-xs font-medium text-accent-light hover:bg-accent-soft/80"
                  >
                    Übernehmen
                  </button>
                )}
              </div>
            ) : null}
          </li>
        );
      })}
      </ul>
    </div>
  );
}
