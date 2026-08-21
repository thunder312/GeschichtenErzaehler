"""Analysator: neuer Haupt-Tab (siehe ToDo.md), importiert eine bestehende
Geschichte/Novelle als Rohtext und erzeugt daraus automatisch ein
vollstaendiges Projekt zum Neu-Schreiben - siehe app/core/analysator.py fuer
die eigentliche Zerlege-/Zusammenfassungslogik.

Zwei Endpunkte, analog zum Automatikmodus-Muster (app/api/pipeline.py:
automatik_start/automatik_status): "starten" legt SOFORT ein neues Projekt
an (wie app/api/projects.py:projekt_anlegen) und haengt die eigentliche,
lang laufende Analyse als FastAPI-BackgroundTask an - der Rueckgabewert
(ordner) ist von Anfang an fix, das Frontend pollt danach "status", bis
"abgeschlossen" gesetzt ist. Bewusst KEIN automatisches Umbenennen des
Projektordners nach dem vom Modell vorgeschlagenen Titel (anders als beim
Architekten-Interview) - erspart die sonst noetige Nachverfolgung eines
sich waehrenddessen aendernden Ordnerpfads waehrend des Hintergrund-Laufs;
der naechste normale Speichervorgang in GeruestPage (app/api/projects.py:
geruest_schreiben) benennt bei Bedarf ohnehin automatisch um."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.core import analysator as an
from app.core import architekt as arch
from app.core import projekt_dateien as pd
from app.core.ollama_client import OllamaFehler, sammle_antwort
from app.core.textutil import woerter
from app.schemas import AnalysatorStartAnfrage, AnalysatorStartAntwort, AnalysatorStatusAntwort, Benutzer
from app.services import (
    neuer_projekt_pfad, ollama_basis_url, projekt_pfad, projekte_wurzel, rollen_modell_override,
)

router = APIRouter(prefix="/api", tags=["analysator"])


def _status_update(projekt_root, **felder) -> dict:
    status = an.status_lesen(projekt_root)
    status.update(felder)
    an.status_schreiben(projekt_root, status)
    return status


def _log_anhaengen(projekt_root, zeile: str, **weitere_felder) -> dict:
    status = an.status_lesen(projekt_root)
    status["log"] = list(status.get("log", [])) + [zeile]
    status.update(weitere_felder)
    an.status_schreiben(projekt_root, status)
    return status


async def _analysieren_lauf(settings: Settings, projekt_root, ssh_ziel_id: str | None, text: str) -> None:
    _status_update(
        projekt_root, laeuft=True, phase="teilen", aktuelles_kapitel=None, gesamt_kapitel=None,
        log=["Text wird in Kapitel aufgeteilt..."], abgeschlossen=False, fehler=None,
    )
    try:
        abschnitte = an.text_in_kapitel_teilen(text)
        if not abschnitte:
            raise ValueError("Im importierten Text konnte kein auswertbarer Inhalt gefunden werden.")
        gesamt = len(abschnitte)
        _log_anhaengen(projekt_root, f"{gesamt} Abschnitt(e) erkannt.", gesamt_kapitel=gesamt)

        analysator_persona = pd.lies(settings.shared_personas_dir / "analysator.txt")
        eintraege: list[tuple[an.KapitelAnalyse, int]] = []

        with ollama_basis_url(settings, ssh_ziel_id) as base_url:
            for i, abschnitt in enumerate(abschnitte, start=1):
                _log_anhaengen(
                    projekt_root, f"Analysiere Kapitel {i} von {gesamt}...",
                    phase="kapitel_analyse", aktuelles_kapitel=i,
                )
                antwort, _meta = await sammle_antwort(
                    base_url, "analysator",
                    an.kapitel_analyse_system(analysator_persona),
                    an.kapitel_analyse_user(abschnitt),
                    modell_override=rollen_modell_override(settings, "analysator"),
                )
                eintraege.append((an.kapitel_analyse_parsen(antwort), woerter(abschnitt)))

            _log_anhaengen(
                projekt_root, "Fasse Gesamt-Gerüst zusammen...", phase="synthese", aktuelles_kapitel=None,
            )
            epoche_architekt_persona = pd.persona_lesen(projekt_root, "architekt")
            synth_antwort, _meta = await sammle_antwort(
                base_url, "analysator",
                an.synthese_system(analysator_persona, epoche_architekt_persona),
                an.synthese_user(an.kapitel_analysen_text_bauen(eintraege), an.textauszug_bauen(text)),
                modell_override=rollen_modell_override(settings, "analysator"),
            )

        geruest_text = an.geruest_zusammenbauen(synth_antwort, an.kapitelplan_block_bauen(eintraege))
        pd.schreib(pd.geruest_datei(projekt_root / "projekt"), geruest_text, force=True)

        ausgangslage = arch.ausgangslage_erkennen(geruest_text)
        if ausgangslage:
            pd.schreib(
                pd.stand_datei(projekt_root / "projekt", 0),
                "# STAND VOR KAPITEL EINS\n\n" + ausgangslage,
                force=True,
            )

        _log_anhaengen(
            projekt_root, "Analyse abgeschlossen - Gerüst gespeichert.",
            laeuft=False, phase="fertig", abgeschlossen=True,
        )
    except OllamaFehler as e:
        _log_anhaengen(projekt_root, f"Fehler: {e}", laeuft=False, fehler=str(e))
    except Exception as e:  # Sicherheitsnetz, analog app/core/automatik.py-Aufrufern
        _log_anhaengen(projekt_root, f"Unerwarteter Fehler: {e}", laeuft=False, fehler=str(e))


@router.post("/analysator/starten", response_model=AnalysatorStartAntwort, status_code=201)
def analysator_starten(anfrage: AnalysatorStartAnfrage, background_tasks: BackgroundTasks,
                        ssh_ziel_id: str | None = None,
                        settings: Settings = Depends(get_settings),
                        benutzer: Benutzer = Depends(get_current_user)):
    epoche_ordner = settings.epochen_dir / anfrage.epoche
    if not epoche_ordner.is_dir():
        raise HTTPException(404, f"Epoche '{anfrage.epoche}' nicht gefunden.")
    zweite_epoche_ordner = None
    zweite_epoche_name = anfrage.zweite_epoche.strip() if anfrage.zweite_epoche else None
    if zweite_epoche_name:
        if zweite_epoche_name == anfrage.epoche:
            raise HTTPException(422, "Zweite Epoche muss sich von der ersten unterscheiden.")
        zweite_epoche_ordner = settings.epochen_dir / zweite_epoche_name
        if not zweite_epoche_ordner.is_dir():
            raise HTTPException(404, f"Zweite Epoche '{zweite_epoche_name}' nicht gefunden.")

    basis_titel = anfrage.titel.strip() or "neu"
    ziel = neuer_projekt_pfad(settings, benutzer.username, basis_titel, anfrage.epoche)
    pd.projekt_anlegen(ziel, epoche_ordner, settings.shared_personas_dir, anfrage.epoche,
                        zweite_epoche_ordner, zweite_epoche_name)

    ordner = ziel.relative_to(projekte_wurzel(settings, benutzer.username)).as_posix()
    background_tasks.add_task(_analysieren_lauf, settings, ziel, ssh_ziel_id, anfrage.text)
    return AnalysatorStartAntwort(ordner=ordner)


@router.get("/projects/{ordner:path}/analysator-status", response_model=AnalysatorStatusAntwort)
def analysator_status(ordner: str, settings: Settings = Depends(get_settings),
                       benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    return AnalysatorStatusAntwort(**an.status_lesen(projekt_root))
