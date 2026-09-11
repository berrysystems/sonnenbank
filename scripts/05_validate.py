#!/usr/bin/env python3
"""Schritt 5: Ein Horizontprofil pruefen.

Gibt fuer eine Bank die heutigen Sonnen- und Schattenphasen aus und
zeichnet optional ein Polardiagramm mit der Sonnenbahn darueber.

    python scripts/05_validate.py --id BANK123
    python scripts/05_validate.py --id BANK123 --datum 2026-06-21 --plot
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import config as cfg  # noqa: E402

import numpy as np  # noqa: E402

from sun import refraktion, sonnenstand  # noqa: E402

LOKAL = ZoneInfo("Europe/Berlin")


def ist_sonnig(profil: list[int], azimut: float, hoehe: float) -> bool:
    return hoehe > profil[int(round(azimut)) % 360] / 10.0


def phasen(profil, lat, lon, tag: date, schritt_min: int = 1):
    """Liste von (start, ende, sonnig) in lokaler Zeit."""
    t = datetime(tag.year, tag.month, tag.day, tzinfo=LOKAL)
    ende = t + timedelta(days=1)
    ergebnis, aktuell, start = [], None, t

    while t < ende:
        az, h = sonnenstand(t.astimezone(timezone.utc), lat, lon)
        h += refraktion(h)
        zustand = h > 0 and ist_sonnig(profil, az, h)
        if aktuell is None:
            aktuell = zustand
        elif zustand != aktuell:
            ergebnis.append((start, t, aktuell))
            start, aktuell = t, zustand
        t += timedelta(minutes=schritt_min)

    ergebnis.append((start, ende, aktuell))
    return ergebnis


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--datum", type=date.fromisoformat, default=date.today())
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()

    profile = json.loads(cfg.HORIZONS_FILE.read_text(encoding="utf-8"))
    if args.id not in profile:
        sys.exit(f"Bank {args.id} nicht in {cfg.HORIZONS_FILE}")
    eintrag = profile[args.id]
    horizont = eintrag["horizont"]
    lat, lon = eintrag["lat"], eintrag["lon"]

    print(f"Bank {args.id}  {lat:.5f} {lon:.5f}")
    print(f"Gelaende {eintrag['boden_z']} m, Augenhoehe {eintrag['augen_z']} m")
    print(f"Hoechste Verdeckung: Gebaeude {eintrag['max_gebaeude']} Grad, "
          f"Gelaende {eintrag['max_gelaende']} Grad")

    grad = np.array(horizont) / 10.0
    for name, von, bis in [("Nord", 315, 45), ("Ost", 45, 135),
                           ("Sued", 135, 225), ("West", 225, 315)]:
        idx = np.arange(von, von + ((bis - von) % 360)) % 360
        print(f"  {name:5s} mittlere Horizonthoehe {grad[idx].mean():5.1f} Grad, "
              f"max {grad[idx].max():5.1f} Grad")

    print(f"\nTagesverlauf {args.datum}:")
    gesamt = timedelta()
    for start, ende, sonnig in phasen(horizont, lat, lon, args.datum):
        dauer = ende - start
        if dauer < timedelta(minutes=2):
            continue
        zustand = "Sonne " if sonnig else "Schatten"
        print(f"  {start:%H:%M} - {ende:%H:%M}  {zustand} "
              f"({dauer.total_seconds() / 3600:.1f} h)")
        if sonnig:
            gesamt += dauer
    print(f"  Summe Sonne: {gesamt.total_seconds() / 3600:.1f} h")

    if args.plot:
        plot(horizont, lat, lon, args.datum, args.id)


def plot(horizont, lat, lon, tag, bank_id):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    az = np.radians(np.arange(360))
    hoehe = np.array(horizont) / 10.0

    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(111, projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.fill_between(az, 90, 90 - hoehe, alpha=0.45, color="#3b4252",
                    label="Verdeckung")

    for datum, farbe, name in [(date(tag.year, 6, 21), "#d08770", "21. Juni"),
                               (tag, "#bf616a", str(tag)),
                               (date(tag.year, 12, 21), "#5e81ac", "21. Dez.")]:
        t = datetime(datum.year, datum.month, datum.day, tzinfo=LOKAL)
        bahn_az, bahn_h = [], []
        for i in range(0, 24 * 60, 5):
            a, h = sonnenstand((t + timedelta(minutes=i)).astimezone(timezone.utc),
                               lat, lon)
            if h > 0:
                bahn_az.append(np.radians(a))
                bahn_h.append(90 - h)
        ax.plot(bahn_az, bahn_h, color=farbe, lw=1.6, label=name)

    ax.set_rlim(90, 0)
    ax.set_rticks([0, 30, 60, 90])
    ax.set_yticklabels(["90", "60", "30", "0"])
    ax.set_title(f"Horizont und Sonnenbahn - Bank {bank_id}", pad=18)
    ax.legend(loc="lower right", bbox_to_anchor=(1.15, -0.08), fontsize=8)

    ziel = cfg.DATA / f"horizont_{bank_id}.png"
    fig.savefig(ziel, dpi=130, bbox_inches="tight")
    print(f"\nDiagramm: {ziel}")


if __name__ == "__main__":
    main()
