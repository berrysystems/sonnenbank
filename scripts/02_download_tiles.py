#!/usr/bin/env python3
"""Schritt 2: Geobasis-Kacheln herunterladen.

Bestimmt aus den Bankkoordinaten die benoetigten 1-km-Kacheln und laedt
  - LoD2-Gebaeudemodelle  (Bank +/- RADIUS_GEBAEUDE)
  - DGM1-Gelaendemodell   (Bank +/- RADIUS_GELAENDE)

Die Dateinamen enthalten beim DGM1 ein Erhebungsjahr, das je Kachel variiert.
Deshalb wird das Verzeichnisverzeichnis (XML-Index) ausgelesen statt Namen
zu raten.

Daten: Geobasis NRW, Datenlizenz Deutschland Zero 2.0
"""
from __future__ import annotations

import argparse
import sys
import time
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg  # noqa: E402

import json  # noqa: E402

KOPF = {"User-Agent": "sonnenbank-pipeline/1.0"}


def namen_aus_index(rohdaten: bytes) -> list[str]:
    """Dateinamen aus einem Verzeichnisindex holen.

    OpenGeodata liefert je nach Produkt und Aushandlung XML oder JSON, deshalb
    wird beides versucht und als letzte Stufe der Rohtext durchsucht.
    """
    text = rohdaten.decode("utf-8", errors="replace")

    try:
        daten = json.loads(text)
        namen = [d["name"] for d in daten.get("files", []) if "name" in d]
        if namen:
            return namen
    except (json.JSONDecodeError, AttributeError, TypeError):
        pass

    try:
        wurzel = ET.fromstring(rohdaten)
        namen = [el.get("name", "") for el in wurzel.iter("file")]
        if any(namen):
            return [n for n in namen if n]
    except ET.ParseError:
        pass

    return re.findall(r'[\w.-]+_\d{3}_\d{4}_[\w.-]*\.(?:gml|tif|tiff|laz)', text)


def index_lesen(url: str) -> dict[tuple[int, int], str]:
    """Verzeichnisindex einlesen. Rueckgabe: (ost_km, nord_km) -> Dateiname."""
    print(f"Index laden: {url}")
    anfrage = urllib.request.Request(url, headers=KOPF)
    with urllib.request.urlopen(anfrage, timeout=120) as antwort:
        namen = namen_aus_index(antwort.read())

    if not namen:
        sys.exit(f"Index von {url} lieferte keine Dateinamen. "
                 "Vermutlich hat sich das Format geaendert.")

    karte = {}
    for name in namen:
        teile = name.split("_")
        # LoD2_32_374_5654_1_NW.gml  /  dgm1_32_374_5654_1_nw_2022.tif
        if len(teile) < 4:
            continue
        try:
            ost, nord = int(teile[2]), int(teile[3])
        except ValueError:
            continue
        karte[(ost, nord)] = name
    print(f"  {len(karte)} Kacheln im Index")
    return karte


def kacheln_fuer(baenke, radius: float) -> set[tuple[int, int]]:
    noetig = set()
    for b in baenke:
        o0, o1 = int((b["e"] - radius) // 1000), int((b["e"] + radius) // 1000)
        n0, n1 = int((b["n"] - radius) // 1000), int((b["n"] + radius) // 1000)
        for o in range(o0, o1 + 1):
            for n in range(n0, n1 + 1):
                noetig.add((o, n))
    return noetig


def herunterladen(basis_url: str, index: dict, kacheln: set, ziel: Path,
                  pause: float = 0.2) -> None:
    ziel.mkdir(parents=True, exist_ok=True)
    fehlend, geladen, uebersprungen = [], 0, 0

    vorhanden = {p.name for p in ziel.iterdir()}
    aufgaben = []
    for kachel in sorted(kacheln):
        name = index.get(kachel)
        if name is None:
            fehlend.append(kachel)
        elif name in vorhanden:
            uebersprungen += 1
        else:
            aufgaben.append(name)

    print(f"{len(aufgaben)} zu laden, {uebersprungen} vorhanden, "
          f"{len(fehlend)} nicht im Index")

    for i, name in enumerate(aufgaben, 1):
        url = basis_url + name
        tmp = ziel / (name + ".part")
        try:
            anfrage = urllib.request.Request(url, headers=KOPF)
            with urllib.request.urlopen(anfrage, timeout=300) as antwort, \
                    open(tmp, "wb") as datei:
                while chunk := antwort.read(1 << 20):
                    datei.write(chunk)
            tmp.rename(ziel / name)
            geladen += 1
        except Exception as fehler:                      # noqa: BLE001
            tmp.unlink(missing_ok=True)
            print(f"  FEHLER {name}: {fehler}")
        if i % 25 == 0 or i == len(aufgaben):
            print(f"  {i}/{len(aufgaben)}")
        time.sleep(pause)

    print(f"{geladen} Dateien geladen nach {ziel}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--nur", choices=["lod2", "dgm1", "ndom50"],
                   help="nur ein Produkt laden")
    p.add_argument("--ohne-vegetation", action="store_true",
                   help="nDOM50 ueberspringen")
    args = p.parse_args()

    baenke = json.loads(cfg.BENCHES_FILE.read_text(encoding="utf-8"))
    print(f"{len(baenke)} Baenke")

    if args.nur in (None, "lod2"):
        kacheln = kacheln_fuer(baenke, cfg.RADIUS_GEBAEUDE)
        print(f"\nLoD2: {len(kacheln)} Kacheln noetig")
        herunterladen(cfg.URL_LOD2, index_lesen(cfg.URL_LOD2),
                      kacheln, cfg.TILES_LOD2)

    if args.nur in (None, "dgm1"):
        kacheln = kacheln_fuer(baenke, cfg.RADIUS_GELAENDE)
        print(f"\nDGM1: {len(kacheln)} Kacheln noetig "
              f"(ca. {len(kacheln) * 2 / 1024:.1f} GB)")
        herunterladen(cfg.URL_DGM1, index_lesen(cfg.URL_DGM1),
                      kacheln, cfg.TILES_DGM)

    if args.nur in (None, "ndom50") and not args.ohne_vegetation:
        kacheln = kacheln_fuer(baenke, cfg.RADIUS_VEGETATION)
        print(f"\nnDOM50: {len(kacheln)} Kacheln noetig")
        herunterladen(cfg.URL_NDOM50, index_lesen(cfg.URL_NDOM50),
                      kacheln, cfg.TILES_NDOM)


if __name__ == "__main__":
    main()
