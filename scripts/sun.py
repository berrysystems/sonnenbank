"""Sonnenstand nach dem NOAA-Verfahren.

Genauigkeit rund 0.01 Grad - fuer Verschattungsfragen mehr als ausreichend.
Alle Zeiten in UTC. Rueckgabe: Azimut (0 = Nord, im Uhrzeigersinn) und
Hoehenwinkel in Grad.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import numpy as np


def _julian_day(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    y, m = dt.year, dt.month
    d = (dt.day + dt.hour / 24 + dt.minute / 1440
         + (dt.second + dt.microsecond / 1e6) / 86400)
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return (math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1))
            + d + b - 1524.5)


def sonnenstand(dt: datetime, lat: float, lon: float) -> tuple[float, float]:
    """Azimut und Hoehenwinkel der Sonne in Grad (geometrisch, ohne Refraktion)."""
    n = _julian_day(dt) - 2451545.0

    L = math.radians((280.460 + 0.9856474 * n) % 360)          # mittlere Laenge
    g = math.radians((357.528 + 0.9856003 * n) % 360)          # mittlere Anomalie
    lam = L + math.radians(1.915) * math.sin(g) + math.radians(0.020) * math.sin(2 * g)
    eps = math.radians(23.439 - 0.0000004 * n)

    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))

    gmst = (18.697374558 + 24.06570982441908 * n) % 24         # Stunden
    lmst = math.radians(((gmst + lon / 15.0) % 24) * 15.0)
    ha = lmst - ra

    phi = math.radians(lat)
    alt = math.asin(math.sin(phi) * math.sin(dec)
                    + math.cos(phi) * math.cos(dec) * math.cos(ha))
    az = math.atan2(-math.sin(ha),
                    math.tan(dec) * math.cos(phi) - math.sin(phi) * math.cos(ha))

    return math.degrees(az) % 360.0, math.degrees(alt)


def refraktion(hoehe_grad: float) -> float:
    """Atmosphaerische Refraktion in Grad (Naeherung nach Saemundsson)."""
    if hoehe_grad < -1.0:
        return 0.0
    h = hoehe_grad
    return (1.02 / math.tan(math.radians(h + 10.3 / (h + 5.11)))) / 60.0


def sonnenbahn(datum, lat: float, lon: float, schritt_min: int = 2):
    """Tagesbahn der Sonne als Arrays (zeiten, azimut, hoehe)."""
    from datetime import timedelta
    t0 = datetime(datum.year, datum.month, datum.day, tzinfo=timezone.utc)
    zeiten, az, hoehe = [], [], []
    for i in range(0, 24 * 60, schritt_min):
        t = t0 + timedelta(minutes=i)
        a, h = sonnenstand(t, lat, lon)
        zeiten.append(t)
        az.append(a)
        hoehe.append(h)
    return zeiten, np.array(az), np.array(hoehe)
