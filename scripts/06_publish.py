#!/usr/bin/env python3
"""Schritt 6: Horizontprofile veroeffentlichen.

Zwei Ausgabewege, beide aus derselben horizons.json:

  --firestore   schreibt je Bank ein Feld horizonB64 ins Bank-Dokument.
                Die App braucht dann keine zweite Datenquelle.
  --bundle      erzeugt data/horizons.min.json fuer statisches Hosting
                (GitHub Pages, Firebase Hosting).

Kodierung: 360 Bytes, je ein Byte pro Grad Azimut, Wert = Horizonthoehe in
halben Grad (0..180). Das sind nach Base64 480 Zeichen pro Bank - klein genug,
um ohne Nachdenken in jedes Dokument zu passen.

    python scripts/06_publish.py --bundle
    python scripts/06_publish.py --firestore
    python scripts/06_publish.py --firestore --trockenlauf
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg  # noqa: E402


def kodieren(zehntelgrad: list[int]) -> str:
    """360 Werte in Zehntelgrad -> Base64 mit 0.5 Grad Aufloesung."""
    if len(zehntelgrad) != 360:
        raise ValueError(f"Profil hat {len(zehntelgrad)} statt 360 Werte")
    bytes_ = bytes(min(180, max(0, round(w / 5))) for w in zehntelgrad)
    return base64.b64encode(bytes_).decode("ascii")


def dekodieren(text: str) -> list[float]:
    """Gegenstueck zu kodieren, fuer Tests und Kontrollen."""
    return [b / 2.0 for b in base64.b64decode(text)]


def profile_lesen() -> dict:
    if not cfg.HORIZONS_FILE.exists():
        sys.exit(f"Fehlt: {cfg.HORIZONS_FILE} - erst Schritt 4 laufen lassen")
    return json.loads(cfg.HORIZONS_FILE.read_text(encoding="utf-8"))


def bundle(profile: dict) -> None:
    """Kompaktes JSON fuer statisches Hosting."""
    klein = {
        bank_id: {
            "h": kodieren(eintrag["horizont"]),
            "lat": eintrag["lat"],
            "lon": eintrag["lon"],
        }
        for bank_id, eintrag in profile.items()
    }
    nutzlast = {"version": cfg.HORIZONT_VERSION, "benches": klein}
    cfg.BUNDLE_FILE.write_text(
        json.dumps(nutzlast, separators=(",", ":")), encoding="utf-8")

    gross = cfg.HORIZONS_FILE.stat().st_size
    klein_groesse = cfg.BUNDLE_FILE.stat().st_size
    print(f"{len(klein)} Profile -> {cfg.BUNDLE_FILE}")
    print(f"{klein_groesse / 1024:.0f} KB statt {gross / 1024:.0f} KB "
          f"({klein_groesse / max(len(klein), 1):.0f} B pro Bank)")


def nach_firestore(profile: dict, trockenlauf: bool) -> None:
    if not trockenlauf:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not cfg.FIRESTORE_CREDENTIALS.exists():
            sys.exit(f"Service-Account-Key fehlt: {cfg.FIRESTORE_CREDENTIALS}")
        firebase_admin.initialize_app(
            credentials.Certificate(str(cfg.FIRESTORE_CREDENTIALS)))
        db = firestore.client()
        sammlung = db.collection(cfg.FIRESTORE_COLLECTION)

    stapel, offen, geschrieben = None, 0, 0
    for bank_id, eintrag in profile.items():
        daten = {
            cfg.FELD_HORIZONT: kodieren(eintrag["horizont"]),
            cfg.FELD_HORIZONT_VERSION: cfg.HORIZONT_VERSION,
        }
        if trockenlauf:
            if geschrieben < 2:
                print(f"  {bank_id}: {daten[cfg.FELD_HORIZONT][:48]}... "
                      f"({len(daten[cfg.FELD_HORIZONT])} Zeichen)")
            geschrieben += 1
            continue

        if stapel is None:
            stapel = db.batch()
        # merge, damit nur diese beiden Felder angefasst werden
        stapel.set(sammlung.document(bank_id), daten, merge=True)
        offen += 1
        geschrieben += 1

        if offen == 400:            # Firestore erlaubt 500 Operationen je Stapel
            stapel.commit()
            print(f"  {geschrieben} geschrieben")
            stapel, offen = None, 0

    if not trockenlauf and offen:
        stapel.commit()

    wort = "wuerden geschrieben" if trockenlauf else "geschrieben"
    print(f"{geschrieben} Profile {wort} "
          f"(Feld {cfg.FELD_HORIZONT}, Version {cfg.HORIZONT_VERSION})")

    if not trockenlauf:
        print("\nDenk an die Firestore-Regeln: horizonB64 soll serverseitig "
              "gesetzt und clientseitig nur gelesen werden.")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--firestore", action="store_true",
                   help="Profile in die Bank-Dokumente schreiben")
    p.add_argument("--bundle", action="store_true",
                   help="statisches JSON fuer Hosting erzeugen")
    p.add_argument("--trockenlauf", action="store_true",
                   help="nichts schreiben, nur zeigen was passieren wuerde")
    args = p.parse_args()

    if not (args.firestore or args.bundle):
        p.error("Waehle --firestore und/oder --bundle")

    profile = profile_lesen()
    print(f"{len(profile)} Profile aus {cfg.HORIZONS_FILE}")

    # Kontrolle: Kodierung darf das Ergebnis nicht nennenswert verfaelschen
    abweichung = 0.0
    for eintrag in profile.values():
        roh = eintrag["horizont"]
        zurueck = dekodieren(kodieren(roh))
        abweichung = max(abweichung,
                         max(abs(a / 10 - b) for a, b in zip(roh, zurueck)))
    print(f"Groesster Kodierfehler: {abweichung:.2f} Grad")

    if args.bundle:
        bundle(profile)
    if args.firestore:
        nach_firestore(profile, args.trockenlauf)


if __name__ == "__main__":
    main()
