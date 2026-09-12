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
                     polygone, hoehen, baum, cfg, vegetation=None) -> dict:
    """Zwei Profile: harter Horizont und zusaetzlich Bewuchs.

    Getrennt gefuehrt, weil ein Baum kein Haus ist. Durch eine Krone kommt je
    nach Art und Jahreszeit noch ein erheblicher Teil des Lichts, hinter einer
    Wand kommt nichts. Die App kann daraus drei Zustaende machen statt zwei.
    """
    obs_z = boden_z + cfg.AUGENHOEHE

    gelaende = gelaendehorizont(
        e, n, obs_z, dem,
        cfg.RADIUS_GELAENDE, cfg.SCHRITT_GELAENDE,
        cfg.ERDRADIUS, cfg.REFRAKTION_K,
    )
    gebaeude = gebaeudehorizont(
        e, n, obs_z, polygone, hoehen, baum, cfg.RADIUS_GEBAEUDE,
    )

    hart = np.clip(np.maximum(gelaende, gebaeude), 0.0, 90.0)

    ergebnis = {
        "horizont": [int(round(w * 10)) for w in hart],      # Zehntelgrad
        "boden_z": round(boden_z, 2),
        "augen_z": round(obs_z, 2),
        "max_gebaeude": round(float(gebaeude.max()), 2),
        "max_gelaende": round(float(gelaende.max()), 2),
    }

    if vegetation is None or not vegetation.vorhanden:
        return ergebnis

    ausschnitt = vegetation.fenster(e, n, cfg.RADIUS_VEGETATION)
    if ausschnitt is None:
        return ergebnis

    feld, x0, y_oben = ausschnitt
    feld = vegetation.gebaeude_ausmaskieren(
        feld, x0, y_oben, polygone, baum, e, n, cfg.RADIUS_VEGETATION)

    bewuchs = vegetationshorizont(
        e, n, obs_z, feld, x0, y_oben, vegetation.raster, dem,
        cfg.RADIUS_VEGETATION, cfg.SCHRITT_VEGETATION)

    mit_bewuchs = np.clip(np.maximum(hart, bewuchs), 0.0, 90.0)
    ergebnis["horizont_veg"] = [int(round(w * 10)) for w in mit_bewuchs]
    ergebnis["max_bewuchs"] = round(float(bewuchs.max()), 2)
    # Wie viel Himmel nimmt der Bewuchs zusaetzlich weg?
    ergebnis["bewuchs_azimute"] = int((bewuchs > hart + 0.5).sum())
    return ergebnis


class Vegetation:
    """Liest das nDOM50 kachelweise als lokalen Ausschnitt um eine Bank.

    Das nDOM enthaelt die Hoehe ueber Grund, also Vegetation UND Gebaeude.
    Die Gebaeude kommen aber schon aus dem LoD2 und werden hier ausmaskiert,
    sonst zaehlen sie doppelt - und zwar mit der ungenaueren Quelle.
    """

    def __init__(self, verzeichnis, raster: float = 1.0,
                 min_hoehe: float = 2.0, puffer: float = 1.5):
        self.raster = raster
        self.min_hoehe = min_hoehe
        self.puffer = puffer
        self.kacheln = {}
        for pfad in verzeichnis.glob("*.tif"):
            teile = pfad.stem.split("_")
            try:
                self.kacheln[(int(teile[2]), int(teile[3]))] = pfad
            except (IndexError, ValueError):
                continue

    @property
    def vorhanden(self) -> bool:
        return bool(self.kacheln)

    def fenster(self, e: float, n: float, radius: float):
        """Vegetationshoehen um (e, n). Rueckgabe (array, x0, y_oben) oder None."""
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.windows import from_bounds

        res = self.raster
        seite = int(round(2 * radius / res))
        x0, y_oben = e - radius, n + radius
        ausgabe = np.zeros((seite, seite), dtype="float32")
        getroffen = False

        o0, o1 = int((e - radius) // 1000), int((e + radius) // 1000)
        n0, n1 = int((n - radius) // 1000), int((n + radius) // 1000)

        for ost in range(o0, o1 + 1):
            for nord in range(n0, n1 + 1):
                pfad = self.kacheln.get((ost, nord))
                if pfad is None:
                    continue
                kx0, ky0 = ost * 1000.0, nord * 1000.0
                sx0, sy0 = max(x0, kx0), max(n - radius, ky0)
                sx1, sy1 = min(e + radius, kx0 + 1000), min(y_oben, ky0 + 1000)
                if sx1 <= sx0 or sy1 <= sy0:
                    continue

                spalte0 = int(round((sx0 - x0) / res))
                spalte1 = int(round((sx1 - x0) / res))
                zeile0 = int(round((y_oben - sy1) / res))
                zeile1 = int(round((y_oben - sy0) / res))
                if spalte1 <= spalte0 or zeile1 <= zeile0:
                    continue

                with rasterio.open(pfad) as src:
                    block = src.read(
                        1,
                        window=from_bounds(sx0, sy0, sx1, sy1, src.transform),
                        out_shape=(zeile1 - zeile0, spalte1 - spalte0),
                        # Maximum statt Mittelwert: ein schmaler Baum darf beim
                        # Vergroebern nicht weggemittelt werden
                        resampling=Resampling.max,
                        boundless=True,
                        fill_value=0,
                        masked=True,
                    ).filled(0).astype("float32")

                ausgabe[zeile0:zeile1, spalte0:spalte1] = np.maximum(
                    ausgabe[zeile0:zeile1, spalte0:spalte1], block)
                getroffen = True

        if not getroffen:
            return None

        ausgabe[~np.isfinite(ausgabe)] = 0.0
        ausgabe[ausgabe < self.min_hoehe] = 0.0
        ausgabe[ausgabe > 60.0] = 0.0        # Artefakte des Bildmatchings
        return ausgabe, x0, y_oben

    def gebaeude_ausmaskieren(self, feld, x0: float, y_oben: float,
                              polygone, baum, e: float, n: float,
                              radius: float):
        """Setzt die Flaechen bekannter Gebaeude im Fenster auf null."""
        from rasterio.features import rasterize
        from rasterio.transform import from_origin

        umkreis = Point(e, n).buffer(radius)
        formen = [polygone[i].buffer(self.puffer) for i in baum.query(umkreis)]
        if not formen:
            return feld

        maske = rasterize(
            formen, out_shape=feld.shape,
            transform=from_origin(x0, y_oben, self.raster, self.raster),
            fill=0, default_value=1, dtype="uint8",
        )
        feld = feld.copy()
        feld[maske == 1] = 0.0
        return feld


def vegetationshorizont(e: float, n: float, obs_z: float, feld, x0: float,
                        y_oben: float, raster: float, dem: Gelaende,
                        radius: float, schritt: float) -> np.ndarray:
    """Maximaler Elevationswinkel der Vegetation je Azimut (360 Werte, Grad)."""
    az = np.radians(np.arange(360, dtype="float64"))[:, None]
    r = np.arange(schritt, radius + schritt, schritt)[None, :]

    E = e + r * np.sin(az)
    N = n + r * np.cos(az)

    spalte = ((E - x0) / raster).astype(np.int32)
    zeile = ((y_oben - N) / raster).astype(np.int32)
    gueltig = ((spalte >= 0) & (spalte < feld.shape[1])
               & (zeile >= 0) & (zeile < feld.shape[0]))

    hoehe_ueber_grund = np.zeros(E.shape, dtype="float64")
    hoehe_ueber_grund[gueltig] = feld[zeile[gueltig], spalte[gueltig]]

    # Absolute Oberkante = Gelaendehoehe am Punkt plus Bewuchshoehe
    boden = dem.abtasten(E.ravel(), N.ravel()).reshape(E.shape).astype("float64")
    oberkante = boden + hoehe_ueber_grund

    with np.errstate(invalid="ignore"):
        elev = np.degrees(np.arctan2(oberkante - obs_z, r))
    # Nur dort, wo tatsaechlich Bewuchs steht
    elev = np.where((hoehe_ueber_grund > 0) & np.isfinite(elev), elev, -90.0)
    return elev.max(axis=1)
