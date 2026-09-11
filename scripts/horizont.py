"""Berechnung des Horizontprofils einer Bank.

Idee: Fuer jedes der 360 Azimute wird der maximale Elevationswinkel bestimmt,
unter dem Gelaende oder Gebaeude den Himmel verdecken. Zur Laufzeit genuegt
dann ein Vergleich des Sonnenhoehenwinkels gegen diesen Wert.
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import Point
from shapely.strtree import STRtree


class Gelaende:
    """Haelt das 10-m-DEM im Speicher und erlaubt schnelles Abtasten."""

    def __init__(self, pfad):
        import rasterio
        with rasterio.open(pfad) as src:
            self.z = src.read(1, masked=True).filled(np.nan).astype("float32")
            t = src.transform
            self.x0, self.dx = t.c, t.a
            self.y0, self.dy = t.f, t.e      # dy ist negativ
            self.hoehe, self.breite = self.z.shape

    def abtasten(self, e: np.ndarray, n: np.ndarray) -> np.ndarray:
        spalte = ((e - self.x0) / self.dx).astype(np.int32)
        zeile = ((n - self.y0) / self.dy).astype(np.int32)
        gueltig = ((spalte >= 0) & (spalte < self.breite)
                   & (zeile >= 0) & (zeile < self.hoehe))
        werte = np.full(e.shape, np.nan, dtype="float32")
        werte[gueltig] = self.z[zeile[gueltig], spalte[gueltig]]
        return werte

    def hoehe_an(self, e: float, n: float) -> float:
        wert = self.abtasten(np.array([e]), np.array([n]))[0]
        return float(wert)


def gelaendehorizont(e: float, n: float, obs_z: float, dem: Gelaende,
                     radius: float, schritt: float,
                     erdradius: float, k: float) -> np.ndarray:
    """Maximaler Elevationswinkel des Gelaendes je Azimut (360 Werte, Grad)."""
    az = np.arange(360, dtype="float64")
    az_rad = np.radians(az)[:, None]
    r = np.arange(schritt, radius + schritt, schritt)[None, :]

    E = e + r * np.sin(az_rad)
    N = n + r * np.cos(az_rad)

    z = dem.abtasten(E.ravel(), N.ravel()).reshape(E.shape).astype("float64")
    # Erdkruemmung abzueglich atmosphaerischer Refraktion
    z -= (1.0 - k) * r ** 2 / (2.0 * erdradius)

    with np.errstate(invalid="ignore"):
        elev = np.degrees(np.arctan2(z - obs_z, r))
    elev = np.where(np.isfinite(elev), elev, -90.0)
    return elev.max(axis=1)


def gebaeudehorizont(e: float, n: float, obs_z: float,
                     polygone, hoehen: np.ndarray, baum: STRtree,
                     radius: float) -> np.ndarray:
    """Maximaler Elevationswinkel der Gebaeude je Azimut (360 Werte, Grad).

    Exakt ueber Strahl-Kanten-Schnitte statt ueber abgetastete Umringpunkte:
    dadurch entstehen keine Luecken zwischen den Abtastpunkten, auch nicht
    bei Gebaeuden unmittelbar neben der Bank.
    """
    horizont = np.full(360, -90.0)
    umkreis = Point(e, n).buffer(radius)

    # Alle Kanten aller relevanten Gebaeude in einem Rutsch sammeln
    starts, enden, firste = [], [], []
    for idx in baum.query(umkreis):
        first = float(hoehen[idx])
        if first <= obs_z + 0.2:
            continue
        punkte = np.asarray(polygone[idx].exterior.coords)
        starts.append(punkte[:-1])
        enden.append(punkte[1:])
        firste.append(np.full(len(punkte) - 1, first))

    if not starts:
        return horizont

    P = np.vstack(starts) - np.array([e, n])          # Kantenanfang relativ
    D = np.vstack(enden) - np.vstack(starts)          # Kantenvektor
    H = np.concatenate(firste) - obs_z                # Hoehe ueber Auge

    az = np.radians(np.arange(360, dtype="float64"))
    U = np.stack([np.sin(az), np.cos(az)], axis=1)    # Strahlrichtungen (360, 2)

    # Kreuzprodukte, Form (360, kanten)
    nenner = U[:, 0:1] * D[None, :, 1] - U[:, 1:2] * D[None, :, 0]
    zaehler_t = P[None, :, 0] * D[None, :, 1] - P[None, :, 1] * D[None, :, 0]
    zaehler_s = P[None, :, 0] * U[:, 1:2] - P[None, :, 1] * U[:, 0:1]

    with np.errstate(divide="ignore", invalid="ignore"):
        t = zaehler_t / nenner        # Entfernung entlang des Strahls
        s = zaehler_s / nenner        # Position auf der Kante

    treffer = np.isfinite(t) & (t > 0.5) & (t <= radius) & (s >= 0.0) & (s <= 1.0)
    t = np.where(treffer, t, np.inf)

    with np.errstate(invalid="ignore"):
        elev = np.degrees(np.arctan2(np.broadcast_to(H, t.shape), t))
    elev = np.where(treffer, elev, -90.0)

    return elev.max(axis=1)


def profil_berechnen(e: float, n: float, boden_z: float, dem: Gelaende,
                     polygone, hoehen, baum, cfg) -> dict:
    obs_z = boden_z + cfg.AUGENHOEHE

    gelaende = gelaendehorizont(
        e, n, obs_z, dem,
        cfg.RADIUS_GELAENDE, cfg.SCHRITT_GELAENDE,
        cfg.ERDRADIUS, cfg.REFRAKTION_K,
    )
    gebaeude = gebaeudehorizont(
        e, n, obs_z, polygone, hoehen, baum, cfg.RADIUS_GEBAEUDE,
    )

    gesamt = np.maximum(gelaende, gebaeude)
    gesamt = np.clip(gesamt, 0.0, 90.0)      # unter dem Horizont ist irrelevant

    return {
        "horizont": [int(round(w * 10)) for w in gesamt],   # Zehntelgrad
        "boden_z": round(boden_z, 2),
        "augen_z": round(obs_z, 2),
        "max_gebaeude": round(float(gebaeude.max()), 2),
        "max_gelaende": round(float(gelaende.max()), 2),
    }
