"""Minimaler CityGML-LoD2-Parser fuer die NRW-Gebaeudemodelle.

Extrahiert pro Gebaeude (und Gebaeudeteil):
  - Grundriss als Shapely-Polygon in EPSG:25832
  - hoechster Punkt der Geometrie als absolute Hoehe (DHHN2016 NH)

Bewusst schema-tolerant: es wird nur ueber lokale Elementnamen gematcht,
damit CityGML 1.0 und 2.0 gleichermassen funktionieren.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from lxml import etree
from shapely.geometry import Polygon


def _localname(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _koordinaten(element) -> list[np.ndarray]:
    """Alle posList/pos-Koordinatentripel unterhalb eines Elements."""
    ringe = []
    for kind in element.iter():
        name = _localname(kind.tag)
        if name not in ("posList", "pos") or not kind.text:
            continue
        werte = np.fromstring(kind.text.strip(), sep=" ")
        dim = int(kind.get("srsDimension", 3))
        if dim != 3 or werte.size % 3:
            continue
        ringe.append(werte.reshape(-1, 3))
    return ringe


def _groesster_ring(ringe: list[np.ndarray]) -> np.ndarray | None:
    bestes, beste_flaeche = None, 0.0
    for r in ringe:
        if len(r) < 4:
            continue
        x, y = r[:, 0], r[:, 1]
        flaeche = abs(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
        if flaeche > beste_flaeche:
            bestes, beste_flaeche = r, flaeche
    return bestes if beste_flaeche > 1.0 else None


def gebaeude_aus_datei(pfad: Path):
    """Generator ueber (polygon, firsthoehe) je Gebaeude/Gebaeudeteil."""
    kontext = etree.iterparse(str(pfad), events=("end",), recover=True, huge_tree=True)
    for _, element in kontext:
        name = _localname(element.tag)
        if name not in ("Building", "BuildingPart"):
            continue

        alle = _koordinaten(element)
        if alle:
            firsthoehe = max(float(r[:, 2].max()) for r in alle)

            grund = []
            for kind in element.iter():
                if _localname(kind.tag) == "GroundSurface":
                    grund.extend(_koordinaten(kind))
            ring = _groesster_ring(grund)
            if ring is None:
                ring = _groesster_ring(alle)

            if ring is not None:
                try:
                    poly = Polygon(ring[:, :2])
                    if not poly.is_valid:
                        poly = poly.buffer(0)
                    if poly.area > 1.0 and poly.geom_type == "Polygon":
                        yield poly, firsthoehe
                except Exception:
                    pass

        # Speicher freigeben - die Kacheln sind bis zu 70 MB gross
        if name == "Building":
            element.clear()
            while element.getprevious() is not None:
                del element.getparent()[0]


def gebaeude_laden(verzeichnis: Path, bbox: tuple[float, float, float, float]):
    """Alle Gebaeude aus den Kacheln eines Verzeichnisses, gefiltert auf eine BBox."""
    emin, nmin, emax, nmax = bbox
    polygone, hoehen = [], []
    for pfad in sorted(verzeichnis.glob("*.gml")):
        for poly, first in gebaeude_aus_datei(pfad):
            e0, n0, e1, n1 = poly.bounds
            if e1 < emin or e0 > emax or n1 < nmin or n0 > nmax:
                continue
            polygone.append(poly)
            hoehen.append(first)
    return polygone, np.array(hoehen, dtype=float)
