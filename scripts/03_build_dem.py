#!/usr/bin/env python3
"""Schritt 3: Aus den DGM1-Kacheln ein 10-m-Mosaik fuer den Fernhorizont bauen.

1 m Aufloesung waere fuer einen 5-km-Horizont Verschwendung: 100 Mio. Zellen
statt 1 Mio. Das Mosaik wird kachelweise dezimiert eingelesen, der
Speicherbedarf bleibt damit klein.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config as cfg  # noqa: E402

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402


def kachel_ecke(name: str) -> tuple[int, int]:
    teile = name.split("_")
    return int(teile[2]) * 1000, int(teile[3]) * 1000


def main():
    kacheln = sorted(cfg.TILES_DGM.glob("*.tif"))
    if not kacheln:
        sys.exit(f"Keine DGM1-Kacheln in {cfg.TILES_DGM}")
    print(f"{len(kacheln)} DGM1-Kacheln")

    ecken = [kachel_ecke(p.name) for p in kacheln]
    emin = min(e for e, _ in ecken)
    emax = max(e for e, _ in ecken) + 1000
    nmin = min(n for _, n in ecken)
    nmax = max(n for _, n in ecken) + 1000

    aufl = cfg.DEM_AUFLOESUNG
    breite = int((emax - emin) / aufl)
    hoehe = int((nmax - nmin) / aufl)
    print(f"Mosaik {breite} x {hoehe} Zellen bei {aufl:.0f} m "
          f"({breite * hoehe * 4 / 1e6:.0f} MB)")

    ausgabe = np.full((hoehe, breite), np.nan, dtype="float32")
    pro_kachel = int(1000 / aufl)

    for i, pfad in enumerate(kacheln, 1):
        e0, n0 = kachel_ecke(pfad.name)
        with rasterio.open(pfad) as src:
            block = src.read(
                1,
                out_shape=(pro_kachel, pro_kachel),
                resampling=rasterio.enums.Resampling.average,
                masked=True,
            ).filled(np.nan).astype("float32")

        spalte = int((e0 - emin) / aufl)
        zeile = int((nmax - (n0 + 1000)) / aufl)
        ausgabe[zeile:zeile + pro_kachel, spalte:spalte + pro_kachel] = block

        if i % 100 == 0 or i == len(kacheln):
            print(f"  {i}/{len(kacheln)}")

    profil = {
        "driver": "GTiff", "height": hoehe, "width": breite, "count": 1,
        "dtype": "float32", "crs": cfg.CRS_UTM32,
        "transform": from_origin(emin, nmax, aufl, aufl),
        "nodata": np.nan, "compress": "deflate", "tiled": True,
    }
    with rasterio.open(cfg.DEM_COARSE, "w", **profil) as dst:
        dst.write(ausgabe, 1)

    gueltig = np.isfinite(ausgabe)
    print(f"\nGeschrieben: {cfg.DEM_COARSE}")
    print(f"Abdeckung {gueltig.mean() * 100:.1f} %, "
          f"Hoehen {np.nanmin(ausgabe):.0f}-{np.nanmax(ausgabe):.0f} m")


if __name__ == "__main__":
    main()
