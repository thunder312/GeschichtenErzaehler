"""KI entwirft das Gerüst aus wenigen Randbedingungen (siehe ToDo.md "KI
designt Gerüst aus ein paar Randbedingungen" und app/core/geruest_ki.py für
die reine Prompt-/Zusammenbau-Logik).

Zwei Endpunkte, Muster 1:1 vom Analysator (app/api/analysator.py): "starten"
hängt die lang laufende KI-Anfrage als FastAPI-BackgroundTask an und gibt
sofort zurück, das Frontend pollt danach "status", bis "abgeschlossen"
gesetzt ist. Anders als beim Analysator wird KEIN Projekt angelegt - das
Projekt existiert bereits (der Nutzer öffnet das Overlay aus dem Gerüst-Editor
bzw. hat es beim Anlegen mit "KI entwirft das Gerüst" als vierten Weg
gewählt). Der Hintergrund-Task schreibt das fertige geruest.md direkt über
denselben pd.schreib()-Weg wie das Architekten-Interview; ein Ordner-Umbenennen
nach dem Titel übernimmt der nächste normale Speichern-Klick in GeruestPage
(app/api/projects.py:geruest_schreiben) - wie beim Analysator bewusst nicht
hier, um keinen sich ändernden Ordnerpfad während des Laufs verfolgen zu
müssen.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import ValidationError

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.core import architekt as arch
from app.core import fundus as fu
from app.core import geruest_ki as gk
from app.core import projekt_dateien as pd
from app.core.ollama_client import OllamaFehler, sammle_antwort
from app.schemas import Benutzer, KiGeruestStartAnfrage, KiGeruestStartAntwort, KiGeruestStatusAntwort
from app.services import fundus_datei, ollama_basis_url, projekt_pfad, rollen_modell_override

router = APIRouter(prefix="/api/projects", tags=["geruest-ki"])


def _status_update(projekt_root, **felder) -> None:
    status = gk.status_lesen(projekt_root)
    status.update(felder)
    gk.status_schreiben(projekt_root, status)


def _log_anhaengen(projekt_root, *zeilen: str, **weitere) -> None:
    status = gk.status_lesen(projekt_root)
    status["log"] = list(status.get("log", [])) + list(zeilen)
    status.update(weitere)
    gk.status_schreiben(projekt_root, status)


def _fundus_kontext(settings: Settings, username: str, projekt_root) -> str:
    """Fundus-Auszug der Projekt-Epoche (plus "## Allgemein") an den
    System-Prompt hängen, damit die KI vorhandene Namen bevorzugt statt
    bekannte Figuren/Orte neu zu erfinden (Spez. Kapitel 4, Regel 7) -
    dieselbe Logik wie app/api/architekt.py:_fundus_kontext, hier bewusst
    dupliziert (10 Zeilen, keine geteilte Abhängigkeit zwischen zwei
    api-Modulen)."""
    epoche = pd.epoche_von_projekt(projekt_root)
    if not epoche:
        return ""
    fundus_text = pd.lies(fundus_datei(settings, username), pflicht=False, ersatz="")
    if not fundus_text:
        return ""
    abschnitte = [
        fu.epoche_abschnitt_erkennen(fundus_text, epoche),
        fu.epoche_abschnitt_erkennen(fundus_text, "Allgemein"),
    ]
    zusammen = "\n".join(a.strip() for a in abschnitte if a).strip()
    return f"\n\n## FIGUREN UND ORTE DIESER EPOCHE (bevorzugt übernehmen)\n{zusammen}\n" if zusammen else ""


def _anfrage_zu_randbedingungen(anfrage: KiGeruestStartAnfrage) -> gk.Randbedingungen:
    return gk.Randbedingungen(
        praemisse=anfrage.praemisse,
        kapitelanzahl=anfrage.kapitelanzahl,
        setting=anfrage.setting,
        zielwortzahl_pro_kapitel=anfrage.zielwortzahl_pro_kapitel,
        figuren=[
            gk.Figur(name=f.name, alter=f.alter, rolle=f.rolle, kurzbeschreibung=f.kurzbeschreibung)
            for f in anfrage.figuren
        ],
        genre=anfrage.genre,
        verlauf=anfrage.verlauf,
        konflikt=anfrage.konflikt,
        dramatik=anfrage.dramatik,
        zeitraum=anfrage.zeitraum,
        schluss=anfrage.schluss,
        tabus=anfrage.tabus,
        sprache=anfrage.sprache,
        jahr=anfrage.jahr,
        jugendschutz_stufe=anfrage.jugendschutz_stufe,
    )


async def _entwurf_lauf(settings: Settings, username: str, projekt_root,
                         ssh_ziel_id: str | None, rb: gk.Randbedingungen,
                         epoche_anzeigename: str) -> None:
    _status_update(
        projekt_root, laeuft=True, phase="entwurf", abgeschlossen=False, fehler=None,
        log=[f"KI entwirft {rb.kapitelanzahl} Kapitel aus deinen Vorgaben..."],
    )
    try:
        system = gk.system_prompt(rb) + _fundus_kontext(settings, username, projekt_root)
        user = gk.randbedingungen_json(rb)
        modell = rollen_modell_override(settings, "geruest_dramaturg")

        with ollama_basis_url(settings, ssh_ziel_id) as base_url:
            ergebnis = None
            for versuch in (1, 2):
                nachricht = user if versuch == 1 else (
                    user + "\n\nDeine letzte Antwort war kein gültiges JSON im geforderten Format. "
                    "Antworte NUR mit dem JSON-Objekt, ohne Erklärung, ohne Markdown."
                )
                antwort_text, _meta = await sammle_antwort(
                    base_url, "geruest_dramaturg", system, nachricht,
                    format="json", modell_override=modell,
                )
                try:
                    ergebnis = gk.antwort_validieren(antwort_text, rb)
                    break
                except (ValidationError, ValueError, json.JSONDecodeError):
                    if versuch == 2:
                        raise
                    _log_anhaengen(projekt_root, "Antwort war unvollständig - zweiter Versuch...")

        assert ergebnis is not None
        for hinweis in ergebnis.hinweise:
            _log_anhaengen(projekt_root, hinweis)

        geruest_text = gk.geruest_zusammenbauen(rb, ergebnis.antwort, epoche_anzeigename)
        pd.schreib(pd.geruest_datei(projekt_root / "projekt"), geruest_text, force=True)

        ausgangslage = arch.ausgangslage_erkennen(geruest_text)
        if ausgangslage:
            pd.schreib(
                pd.stand_datei(projekt_root / "projekt", 0),
                "# STAND VOR KAPITEL EINS\n\n" + ausgangslage,
                force=True,
            )

        _log_anhaengen(
            projekt_root, "Gerüst-Entwurf gespeichert - bitte im Editor prüfen und ergänzen.",
            laeuft=False, phase="fertig", abgeschlossen=True,
        )
    except OllamaFehler as e:
        _log_anhaengen(projekt_root, f"Fehler: {e}", laeuft=False, fehler=str(e))
    except (ValidationError, ValueError, json.JSONDecodeError) as e:
        _log_anhaengen(
            projekt_root,
            "Die KI hat trotz zweitem Versuch kein verwertbares Gerüst geliefert. "
            "Bitte erneut starten, ggf. mit knapperen Vorgaben.",
            laeuft=False, fehler=str(e),
        )
    except Exception as e:  # Sicherheitsnetz, analog app/api/analysator.py
        _log_anhaengen(projekt_root, f"Unerwarteter Fehler: {e}", laeuft=False, fehler=str(e))


@router.post("/{ordner:path}/geruest-ki/starten", response_model=KiGeruestStartAntwort, status_code=202)
def geruest_ki_starten(ordner: str, anfrage: KiGeruestStartAnfrage, background_tasks: BackgroundTasks,
                        ssh_ziel_id: str | None = Query(None),
                        settings: Settings = Depends(get_settings),
                        benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    rb = _anfrage_zu_randbedingungen(anfrage)
    epoche_anzeigename = (pd.epoche_von_projekt(projekt_root) or "").replace("-", " ")
    background_tasks.add_task(
        _entwurf_lauf, settings, benutzer.username, projekt_root, ssh_ziel_id, rb, epoche_anzeigename,
    )
    return KiGeruestStartAntwort(gestartet=True)


@router.get("/{ordner:path}/geruest-ki/status", response_model=KiGeruestStatusAntwort)
def geruest_ki_status(ordner: str, settings: Settings = Depends(get_settings),
                       benutzer: Benutzer = Depends(get_current_user)):
    projekt_root = projekt_pfad(settings, benutzer.username, ordner)
    return KiGeruestStatusAntwort(**gk.status_lesen(projekt_root))
