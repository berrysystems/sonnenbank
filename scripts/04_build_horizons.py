#!/usr/bin/env python3
"""Schritt 4: Horizontprofile fuer alle Baenke berechnen.

Ergebnis: data/horizons.json - je Bank 360 Werte in Zehntelgrad.
Das ist der einzige Datensatz, den die App zur Laufzeit braucht.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import config as cfg  # noqa: E402

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from shapely.strtree import STRtree  # noqa: E402

from citygml import gebaeude_laden  # noqa: E402
from horizont import Gelaende, Vegetation, profil_berechnen  # noqa: E402


def bodenhoehe_dgm1(e: float, n: float) -> float | None:
    """Praezise Gelaendehoehe aus der 1-m-Kachel am Standort der Bank."""
    ost, nord = int(e // 1000), int(n // 1000)
    treffer = list(cfg.TILES_DGM.glob(f"dgm1_32_{ost}_{nord}_*.tif"))
    if not treffer:
        return None
    with rasterio.open(treffer[0]) as src:
        wert = next(src.sample([(e, n)]))[0]
    return None if wert is None or not np.isfinite(wert) else float(wert)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, help="nur die ersten N Baenke rechnen")
    p.add_argument("--ohne-vegetation", action="store_true",
                   help="nDOM50 ignorieren, nur Gebaeude und Gelaende")
    args = p.parse_args()

    baenke = json.loads(cfg.BENCHES_FILE.read_text(encoding="utf-8"))
    if args.limit:
        baenke = baenke[:args.limit]
    print(f"{len(baenke)} Baenke")

    print("Gelaendemodell laden ...")
    dem = Gelaende(cfg.DEM_COARSE)

    emin = min(b["e"] for b in baenke) - cfg.RADIUS_GEBAEUDE
    emax = max(b["e"] for b in baenke) + cfg.RADIUS_GEBAEUDE
    nmin = min(b["n"] for b in baenke) - cfg.RADIUS_GEBAEUDE
    nmax = max(b["n"] for b in baenke) + cfg.RADIUS_GEBAEUDE

    print("Gebaeude aus CityGML laden ...")
    t0 = time.time()
    polygone, hoehen = gebaeude_laden(cfg.TILES_LOD2, (emin, nmin, emax, nmax))
    print(f"  {len(polygone)} Gebaeude in {time.time() - t0:.0f} s")
    baum = STRtree(polygone) if polygone else STRtree([])

    vegetation = None
    if not args.ohne_vegetation:
        vegetation = Vegetation(cfg.TILES_NDOM, cfg.VEG_RASTER,
                                cfg.VEG_MIN_HOEHE, cfg.GEBAEUDE_PUFFER)
        if vegetation.vorhanden:
            print(f"Vegetation: {len(vegetation.kacheln)} nDOM50-Kacheln")
        else:
            print("Keine nDOM50-Kacheln gefunden, rechne ohne Bewuchs")
            vegetation = None

    ergebnis, ohne_boden = {}, 0
    t0 = time.time()
    for i, b in enumerate(baenke, 1):
        boden = bodenhoehe_dgm1(b["e"], b["n"])
        if boden is None:
            boden = dem.hoehe_an(b["e"], b["n"])
            ohne_boden += 1
        if not np.isfinite(boden):
            print(f"  {b['id']}: keine Gelaendehoehe, uebersprungen")
            continue

        profil = profil_berechnen(
            b["e"], b["n"], float(boden), dem, polygone, hoehen, baum, cfg,
            vegetation)
        profil["lat"], profil["lon"] = b["lat"], b["lon"]
        if b.get("bearing") is not None:
            profil["bearing"] = b["bearing"]
        for feld in ("title", "address"):
            if b.get(feld):
                profil[feld] = b[feld]
        ergebnis[b["id"]] = profil

        if i % 50 == 0 or i == len(baenke):
            tempo = i / max(time.time() - t0, 1e-6)
            print(f"  {i}/{len(baenke)}  ({tempo:.1f} Baenke/s)")

    cfg.HORIZONS_FILE.write_text(
        json.dumps(ergebnis, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")

    groesse = cfg.HORIZONS_FILE.stat().st_size
    print(f"\n{len(ergebnis)} Profile in {cfg.HORIZONS_FILE} "
          f"({groesse / 1024:.0f} KB, {groesse / max(len(ergebnis), 1):.0f} B/Bank)")
    if ohne_boden:
        print(f"{ohne_boden} Baenke ohne 1-m-Kachel, 10-m-DEM benutzt")

    mit_veg = [p for p in ergebnis.values() if "horizont_veg" in p]
    if mit_veg:
        anteil = sum(p["bewuchs_azimute"] for p in mit_veg) / len(mit_veg)
        print(f"{len(mit_veg)} Profile mit Bewuchs, im Mittel {anteil:.0f} "
              f"von 360 Richtungen zusaetzlich verdeckt")


if __name__ == "__main__":
    main()
