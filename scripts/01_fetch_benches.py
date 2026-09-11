#!/usr/bin/env python3
"""Schritt 1: Baenke aus Firestore exportieren.

Angepasst an das Schema benches/{benchId}:
  - GeoPoint liegt verschachtelt unter geo.geopoint (geoflutterfire_plus)
  - nur status == "active" wird verarbeitet
  - Blickrichtung wird aus imageBearings abgeleitet (Zirkulaermittel)

Ergebnis: data/benches.json

Aufruf:
    python scripts/01_fetch_benches.py
    python scripts/01_fetch_benches.py --aus-datei export.json
    python scripts/01_fetch_benches.py --alle-status
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg  # noqa: E402

from pyproj import Transformer  # noqa: E402

NACH_UTM = Transformer.from_crs(cfg.CRS_WGS84, cfg.CRS_UTM32, always_xy=True)


def feld(daten: dict, pfad: str):
    """Feldzugriff mit Punktnotation, z. B. 'geo.geopoint'."""
    wert = daten
    for teil in pfad.split("."):
        if not isinstance(wert, dict) or teil not in wert:
            return None
        wert = wert[teil]
    return wert


def koordinaten_aus_dokument(daten: dict):
    """lat/lon aus GeoPoint (verschachtelt oder flach) oder Einzelfeldern."""
    punkt = feld(daten, cfg.FELD_GEOPOINT)

    if punkt is not None:
        # Firestore-SDK liefert ein GeoPoint-Objekt
        if hasattr(punkt, "latitude"):
            return float(punkt.latitude), float(punkt.longitude)
        # JSON-Export liefert ein Dict, je nach Exportweg anders benannt
        if isinstance(punkt, dict):
            lat = punkt.get("latitude", punkt.get("lat", punkt.get("_latitude")))
            lon = punkt.get("longitude", punkt.get("lng", punkt.get("_longitude")))
            if lat is not None and lon is not None:
                return float(lat), float(lon)
        # Manche Exporte schreiben [lat, lon]
        if isinstance(punkt, (list, tuple)) and len(punkt) == 2:
            return float(punkt[0]), float(punkt[1])

    if cfg.FELD_LAT in daten and cfg.FELD_LON in daten:
        return float(daten[cfg.FELD_LAT]), float(daten[cfg.FELD_LON])
    return None


def ausrichtung(daten: dict):
    """Zirkulaeres Mittel der Foto-Kompassrichtungen.

    Ein arithmetisches Mittel waere hier falsch: aus 350 und 10 Grad wuerde
    180 statt 0.
    """
    werte = feld(daten, cfg.FELD_AUSRICHTUNG)
    if not isinstance(werte, (list, tuple)):
        return None
    gueltig = [float(w) for w in werte
               if isinstance(w, (int, float)) and math.isfinite(float(w))]
    if not gueltig:
        return None
    x = sum(math.cos(math.radians(w)) for w in gueltig)
    y = sum(math.sin(math.radians(w)) for w in gueltig)
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return None
    return round(math.degrees(math.atan2(y, x)) % 360.0, 1) % 360.0


def aus_firestore(alle_status: bool):
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not cfg.FIRESTORE_CREDENTIALS.exists():
        sys.exit(f"Service-Account-Key fehlt: {cfg.FIRESTORE_CREDENTIALS}")

    firebase_admin.initialize_app(
        credentials.Certificate(str(cfg.FIRESTORE_CREDENTIALS)))
    db = firestore.client()

    abfrage = db.collection(cfg.FIRESTORE_COLLECTION)
    if not alle_status and len(cfg.STATUS_ERLAUBT) == 1:
        # Serverseitig filtern spart Lesevorgaenge
        abfrage = abfrage.where("status", "==", next(iter(cfg.STATUS_ERLAUBT)))

    for doc in abfrage.stream():
        yield doc.id, doc.to_dict()


def aus_datei(pfad: Path):
    roh = json.loads(pfad.read_text(encoding="utf-8"))
    if isinstance(roh, dict):
        yield from roh.items()
    else:
        for i, wert in enumerate(roh):
            yield str(wert.get("id", i)), wert


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--aus-datei", type=Path,
                   help="JSON-Export statt Live-Zugriff auf Firestore")
    p.add_argument("--alle-status", action="store_true",
                   help="auch reported und removed verarbeiten")
    args = p.parse_args()

    quelle = (aus_datei(args.aus_datei) if args.aus_datei
              else aus_firestore(args.alle_status))

    baenke = []
    grund = Counter()

    for doc_id, daten in quelle:
        daten = daten or {}

        status = daten.get("status", "active")
        if not args.alle_status and status not in cfg.STATUS_ERLAUBT:
            grund[f"status={status}"] += 1
            continue

        if cfg.AI_FILTER and daten.get("aiNoBenchDetected"):
            grund["aiNoBenchDetected"] += 1
            continue

        koord = koordinaten_aus_dokument(daten)
        if koord is None:
            grund["keine Koordinate"] += 1
            continue

        lat, lon = koord
        if not (47.0 < lat < 55.5 and 5.5 < lon < 15.5):
            grund["ausserhalb Deutschlands"] += 1
            continue

        e, n = NACH_UTM.transform(lon, lat)
        eintrag = {
            "id": doc_id,
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "e": round(e, 2),
            "n": round(n, 2),
            "bearing": ausrichtung(daten),
        }
        for name in cfg.FELDER_UEBERNEHMEN:
            if name in daten and daten[name] is not None:
                eintrag[name] = daten[name]
        baenke.append(eintrag)

    cfg.BENCHES_FILE.write_text(
        json.dumps(baenke, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(baenke)} Baenke geschrieben nach {cfg.BENCHES_FILE}")
    for text, anzahl in grund.most_common():
        print(f"  uebersprungen ({text}): {anzahl}")

    if not baenke:
        return

    e = [b["e"] for b in baenke]
    n = [b["n"] for b in baenke]
    print(f"\nBBox UTM32: {min(e):.0f} {min(n):.0f} .. {max(e):.0f} {max(n):.0f}")
    print(f"Ausdehnung: {(max(e) - min(e)) / 1000:.1f} x "
          f"{(max(n) - min(n)) / 1000:.1f} km")

    mit_bearing = sum(1 for b in baenke if b["bearing"] is not None)
    print(f"Mit Blickrichtung aus Fotos: {mit_bearing} von {len(baenke)}")

    mit_shade = sum(1 for b in baenke if b.get("hasShade"))
    if mit_shade:
        print(f"Nutzerangabe hasShade=true: {mit_shade} "
              f"({mit_shade / len(baenke) * 100:.0f} %) - "
              f"brauchbar zur Gegenpruefung des Modells")

    kacheln = {(int(b["e"] // 1000), int(b["n"] // 1000)) for b in baenke}
    print(f"\nBankkacheln: {len(kacheln)} (LoD2-Download in dieser "
          f"Groessenordnung plus Rand)")


if __name__ == "__main__":
    main()
