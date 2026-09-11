#!/usr/bin/env python3
"""Selbsttest der Rechenkerne mit synthetischen Daten.

Prueft gegen analytisch bekannte Ergebnisse:
  - Sonnenstand zur Sonnenwende
  - Gebaeudehorizont: Wuerfel bekannter Hoehe in bekanntem Abstand
  - Gelaendehorizont: kuenstlicher Hang
  - CityGML-Parser an einer erzeugten Minimaldatei

Laeuft ohne Netzzugang und ohne echte Geobasisdaten.
"""
from __future__ import annotations

import math
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon
from shapely.strtree import STRtree

import config as cfg
from citygml import gebaeude_aus_datei
from horizont import Gelaende, gebaeudehorizont, gelaendehorizont
from sun import sonnenstand

FEHLER = []


def pruefe(name, ist, soll, toleranz):
    ok = abs(ist - soll) <= toleranz
    print(f"  [{'ok' if ok else 'FEHLER'}] {name}: {ist:.3f} "
          f"(erwartet {soll:.3f} +/- {toleranz})")
    if not ok:
        FEHLER.append(name)


print("1) Sonnenstand")
lat, lon = 51.0267, 7.5636          # Gummersbach
mittag_sommer = datetime(2026, 6, 21, 11, 31, tzinfo=timezone.utc)
az, h = sonnenstand(mittag_sommer, lat, lon)
pruefe("Hoehe Sommersonnenwende mittags", h, 90 - lat + 23.44, 0.1)
pruefe("Azimut mittags (Sued)", az, 180.0, 1.0)

mittag_winter = datetime(2026, 12, 21, 11, 32, tzinfo=timezone.utc)
_, h = sonnenstand(mittag_winter, lat, lon)
pruefe("Hoehe Wintersonnenwende mittags", h, 90 - lat - 23.44, 0.1)

print("\n2) Gebaeudehorizont")
# Wuerfel 20 m x 20 m, Firsthoehe 110 m, Suedkante 50 m noerdlich der Bank
e0, n0, boden = 400000.0, 5650000.0, 100.0
obs = boden + 1.2
haus = Polygon([(e0 - 10, n0 + 50), (e0 + 10, n0 + 50),
                (e0 + 10, n0 + 70), (e0 - 10, n0 + 70)])
hoehen = np.array([110.0])
baum = STRtree([haus])
hb = gebaeudehorizont(e0, n0, obs, [haus], hoehen, baum, 600.0)
erwartet = math.degrees(math.atan2(110.0 - obs, 50.0))
pruefe("Elevation nach Norden", hb[0], erwartet, 0.05)
pruefe("Elevation nach Sueden (frei)", hb[180], -90.0, 0.01)
# Winkelbreite: halbe Breite 10 m in 50 m Abstand -> atan(10/50) = 11.3 Grad
breite = int((hb > -89).sum())
pruefe("Azimutale Breite in Grad", breite, 2 * math.degrees(math.atan2(10, 50)), 3.0)

print("\n3) Gelaendehorizont")
# Kuenstlicher Hang: nach Osten steigt das Gelaende mit 10 Prozent
with tempfile.TemporaryDirectory() as tmp:
    aufl, groesse = 10.0, 1200
    xs = np.arange(groesse) * aufl
    z = np.tile(xs * 0.10, (groesse, 1)).astype("float32")   # Ost = hoeher
    pfad = Path(tmp) / "dem.tif"
    with rasterio.open(
        pfad, "w", driver="GTiff", height=groesse, width=groesse, count=1,
        dtype="float32", crs=cfg.CRS_UTM32,
        transform=from_origin(395000, 5655000, aufl, aufl), nodata=np.nan,
    ) as dst:
        dst.write(z, 1)

    dem = Gelaende(pfad)
    e_mitte, n_mitte = 395000 + 6000, 5655000 - 6000
    z_mitte = dem.hoehe_an(e_mitte, n_mitte)
    hg = gelaendehorizont(e_mitte, n_mitte, z_mitte + 1.2, dem,
                          3000.0, 10.0, cfg.ERDRADIUS, cfg.REFRAKTION_K)
    # 10 Prozent Steigung entspricht 5.71 Grad, abzueglich Augenhoehe und
    # Erdkruemmung liegt der Fernhorizont knapp darunter.
    pruefe("Hangwinkel nach Osten", hg[90], math.degrees(math.atan(0.10)), 0.35)
    pruefe("Abfall nach Westen", hg[270], -math.degrees(math.atan(0.10)), 0.5)

print("\n4) CityGML-Parser")
GML = """<?xml version="1.0" encoding="UTF-8"?>
<core:CityModel xmlns:core="http://www.opengis.net/citygml/1.0"
                xmlns:bldg="http://www.opengis.net/citygml/building/1.0"
                xmlns:gml="http://www.opengis.net/gml">
 <core:cityObjectMember>
  <bldg:Building gml:id="TEST1">
   <bldg:measuredHeight uom="urn:adv:uom:m">9.5</bldg:measuredHeight>
   <bldg:boundedBy><bldg:GroundSurface><bldg:lod2MultiSurface>
    <gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior>
     <gml:LinearRing><gml:posList srsDimension="3">
      400000 5650000 100 400020 5650000 100 400020 5650015 100
      400000 5650015 100 400000 5650000 100
     </gml:posList></gml:LinearRing>
    </gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface>
   </bldg:lod2MultiSurface></bldg:GroundSurface></bldg:boundedBy>
   <bldg:boundedBy><bldg:RoofSurface><bldg:lod2MultiSurface>
    <gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior>
     <gml:LinearRing><gml:posList srsDimension="3">
      400000 5650000 109.5 400020 5650000 109.5 400020 5650015 109.5
      400000 5650015 109.5 400000 5650000 109.5
     </gml:posList></gml:LinearRing>
    </gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface>
   </bldg:lod2MultiSurface></bldg:RoofSurface></bldg:boundedBy>
  </bldg:Building>
 </core:cityObjectMember>
</core:CityModel>
"""
with tempfile.TemporaryDirectory() as tmp:
    pfad = Path(tmp) / "LoD2_32_400_5650_1_NW.gml"
    pfad.write_text(GML, encoding="utf-8")
    gefunden = list(gebaeude_aus_datei(pfad))
    pruefe("Anzahl Gebaeude", len(gefunden), 1, 0)
    if gefunden:
        poly, first = gefunden[0]
        pruefe("Grundflaeche in m2", poly.area, 300.0, 0.1)
        pruefe("Firsthoehe absolut", first, 109.5, 0.01)

print("\n" + ("ALLE TESTS BESTANDEN" if not FEHLER
              else f"FEHLGESCHLAGEN: {', '.join(FEHLER)}"))
sys.exit(1 if FEHLER else 0)
