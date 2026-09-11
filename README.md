# Sonnenstand an Sitzbänken – Oberbergischer Kreis

Berechnet für jede Bank ein 360°-Horizontprofil aus amtlichen Geobasisdaten.
Zur Laufzeit braucht die App dann nur noch den Sonnenstand und einen
Array-Zugriff: kein Kartenserver, kein GPU-Rendering, keine laufenden Kosten.

```
Firestore ──► benches.json ──► Kacheln laden ──► DEM-Mosaik ──► horizons.json ──► App
```

## Datenquellen

Alle Daten stehen unter **Datenlizenz Deutschland Zero 2.0** – Nutzung ohne
Einschränkungen, Namensnennung nicht erforderlich (aber fair).

| Was | Produkt | Link |
|---|---|---|
| Gebäude mit Dachform | 3D-Gebäudemodell LoD2 (CityGML), 1-km-Kacheln | https://www.opengeodata.nrw.de/produkte/geobasis/3dg/lod2_gml/lod2_gml/ |
| Gelände | DGM1 (GeoTIFF), 1-km-Kacheln | https://www.opengeodata.nrw.de/produkte/geobasis/hm/dgm1_tiff/dgm1_tiff/ |
| Produktinfo LoD2 | Bezirksregierung Köln | https://www.bezreg-koeln.nrw.de/geobasis-nrw/produkte-und-dienste/3d-gebaeudemodelle |
| Produktinfo DGM1 | Bezirksregierung Köln | https://www.bezreg-koeln.nrw.de/geobasis-nrw/produkte-und-dienste/hoehenmodelle/digitale-gelaendemodelle/digitales-gelaendemodell |
| Metadaten / Lizenz | Open.NRW | https://open.nrw/dataset/5d9a8abc-dfd0-4dda-b8fa-165cce4d8065 |
| Vegetation (später) | bDOM50 als LAZ-Punktwolke | https://ckan.open.nrw.de/dataset/7b5646e2-82cf-47ec-ba5f-91b2e1bb86be |

Bezugssystem durchgehend **EPSG:25832** (ETRS89 / UTM 32N), Höhen **DHHN2016 NH**.
Kachelnamen kodieren die linke untere Ecke in Kilometern, z. B.
`LoD2_32_399_5653_1_NW.gml` → Easting 399000, Northing 5653000.

## Installation

```bash
pip install -r requirements.txt
```

Für Schritt 1 zusätzlich `firebase-admin` und einen Service-Account-Key als
`serviceAccountKey.json` im Projektwurzelverzeichnis.

## Ablauf

```bash
python scripts/00_selftest.py                 # Rechenkerne prüfen, ohne Netz
python scripts/01_fetch_benches.py            # Firestore → data/benches.json
python scripts/02_download_tiles.py           # LoD2 + DGM1 laden
python scripts/03_build_dem.py                # 10-m-Mosaik für den Fernhorizont
python scripts/04_build_horizons.py           # → data/horizons.json
python scripts/05_validate.py --id BANK123 --plot
```

Schritt 2 ist der lange: für den Oberbergischen Kreis mit 5 km Puffer sind es
grob 2000 DGM1-Kacheln (~4 GB) und einige hundert LoD2-Kacheln. Einmalig.
Der Download ist wiederaufnahmefähig, vorhandene Dateien werden übersprungen.

Ohne Firestore-Zugang lässt sich Schritt 1 auch aus einem Export füttern:

```bash
python scripts/01_fetch_benches.py --aus-datei export.json
```

## Ergebnisformat

`data/horizons.json`, rund 1 KB pro Bank:

```json
{
  "BANK123": {
    "horizont": [0, 0, 12, 35, ...],   // 360 Werte, Zehntelgrad, Index = Azimut
    "boden_z": 312.4,
    "augen_z": 313.6,
    "max_gebaeude": 34.6,
    "max_gelaende": 4.2,
    "lat": 51.0267,
    "lon": 7.5636
  }
}
```

## Verwendung in der App

```js
import { istSonnig, naechsterWechsel, sonnenstunden } from './sonnenbank.js';

const zustand = istSonnig(bank.horizont, bank.lat, bank.lon);
// { sonnig: true, hoehe: 41.2, azimut: 213.4, horizont: 8.1, grund: 'Sonne' }

const wechsel = naechsterWechsel(bank.horizont, bank.lat, bank.lon);
// { zeitpunkt: Date, wirdSonnig: false }  →  "ab 16:20 im Schatten"

sonnenstunden(bank.horizont, bank.lat, bank.lon);   // 7.8
```

Der Sonnenstand in `sonnenbank.js` ist eine Portierung desselben
NOAA-Verfahrens wie in `scripts/sun.py`. Beide stimmen auf drei
Nachkommastellen überein – getestet.

## Weboberfläche

`frontend/index.html` liest `data/horizons.json` und `data/benches.json` und
zeigt je Bank den Horizont als abgerollte 360°-Silhouette mit der Tagesbahn
der Sonne darüber. Der Regler fährt durch den Tag, das Band darunter zeigt
Sonnen- und Schattenphasen.

Wegen der Browser-Sicherheitsregeln braucht `fetch` einen Server – ein Doppel-
klick auf die Datei genügt nicht:

```bash
python -m http.server 8000      # im Projektordner starten
# dann http://localhost:8000/frontend/ öffnen
```

Alternativ lassen sich die beiden JSON-Dateien auf der Startseite direkt
auswählen, dann läuft die Seite auch von der Festplatte.

Die Titel in der Liste kommen aus `title` bzw. `address` der Bank-Dokumente.
Fehlt `benches.json`, zeigt die Liste die Firestore-IDs.

## Veröffentlichen

Die schwere Vorberechnung läuft einmalig lokal, veröffentlicht wird nur das
Ergebnis. Ein Profil sind nach der Kodierung 480 Zeichen – klein genug, um es
überall mitzuführen.

```bash
python scripts/06_publish.py --bundle      # → data/horizons.min.json
python scripts/06_publish.py --firestore   # → Feld horizonB64 je Bank
```

### In die Bank-Dokumente (empfohlen für die App)

`--firestore` schreibt `horizonB64` und `horizonVersion` per `merge` in die
bestehenden Dokumente, in Stapeln zu 400. Eure App liest das Profil dann
zusammen mit der Bank, ohne zweite Abfrage. In den Firestore-Regeln sollten
beide Felder nur lesbar sein – gesetzt werden sie serverseitig.

`horizonVersion` ist die Versicherung gegen halbfertige Neuberechnungen:
ändert ihr das Modell, zählt `HORIZONT_VERSION` in `config.py` hoch, und die
App erkennt veraltete Profile.

### Als statische Seite

```bash
bash scripts/build_site.sh     # stellt public/ zusammen
```

**GitHub Pages:** `.github/workflows/pages.yml` veröffentlicht bei jedem Push
auf `main`, wenn sich `frontend/` oder `data/horizons.min.json` ändert. Der
Workflow rechnet bewusst nichts nach – der Kacheldownload sind mehrere
Gigabyte und gehört nicht in eine CI. In den Repo-Einstellungen unter Pages
als Quelle „GitHub Actions" wählen.

**Firebase Hosting:** `firebase.json` liegt bereit.

```bash
bash scripts/build_site.sh && firebase deploy --only hosting
```

Die `.gitignore` hält die Geobasisdaten und `serviceAccountKey.json` draußen,
lässt `data/horizons.min.json` aber bewusst durch – das ist die
Deploy-Grundlage.

### Neue Bänke nachrechnen

Der beschriebene Ablauf ist ein Stapellauf. Kommt später eine einzelne Bank
dazu, wäre es unsinnig, dafür alles erneut zu laden. Der Weg dahin: aus den
Rohkacheln einmalig einen verschlankten Datensatz ziehen – Gebäudegrundrisse
mit Firsthöhe als NDJSON und das 10-m-DEM als Cloud-Optimized GeoTIFF, für den
Oberbergischen Kreis zusammen deutlich unter 100 MB. Das passt in einen
Cloud-Run-Container, den ein Firestore-Trigger bei `onCreate` anstößt. Die
Rechnung selbst dauert pro Bank Millisekunden.

## Was das Modell kann und was nicht

**Berücksichtigt:** Gebäude und Bauwerke aus LoD2 im Umkreis von 600 m mit
ihrer tatsächlichen Firsthöhe, Gelände bis 5 km inklusive Erdkrümmung und
Refraktion, atmosphärische Refraktion beim Sonnenstand.

**Nicht berücksichtigt:**

- **Bäume.** Der wichtigste Punkt bei Parkbänken. LoD2 kennt keine Vegetation.
  Nachrüstbar über das bDOM50 (LAZ-Punktwolke): Differenz zum DGM1 bilden,
  Gebäudegrundrisse ausmaskieren, Rest als Vegetationshöhe in den Horizont
  einrechnen. Rechnet man das nach, verschiebt sich das Ergebnis an
  baumnahen Bänken erheblich – rechnet man es nicht, ist die Vorhersage
  dort systematisch zu optimistisch. Kennzeichnet solche Bänke in der App
  besser als „Angabe ohne Baumbestand".
- **Bewölkung.** Das Modell sagt „die Sonne stünde frei", nicht „es scheint
  die Sonne". Für Letzteres bräuchtet ihr eine Wetter-API obendrauf.
- **Zäune, Hecken, Bushaltestellenhäuschen, Sonnensegel.**
- **Diffuse Helligkeit.** Schatten heißt hier geometrisch verdeckt, nicht dunkel.

## Genauigkeit der Eingangsdaten

Die Höhengenauigkeit des LoD2 liegt bei etwa 1 m, die Lagegenauigkeit
entspricht den ALKIS-Gebäudegrundrissen. Dagegen fällt euer eigentliches
Risiko deutlich stärker ins Gewicht: **die Bankkoordinaten stammen vom
Smartphone-GPS**, das im Freien typischerweise 3–10 m und unter Baumkronen
oder zwischen Häusern auch mal 20 m danebenliegt. Genau dort, wo die
Verschattung interessant wird, ist das GPS am schlechtesten.

Zwei Gegenmaßnahmen, beide empfehlenswert:

1. **Stichprobe gegen Luftbild.** Die Bänke über einem DOP oder OSM
   kontrollieren und offensichtliche Ausreißer korrigieren.
2. **Unsicherheit mitrechnen.** Statt nur des Bankpunkts zusätzlich vier
   Punkte in 5 m Abstand rechnen. Weichen die Profile stark voneinander ab,
   ist die Aussage an dieser Bank unsicher – das lässt sich in der App
   ehrlich als „ungefähr" kennzeichnen, statt eine Präzision vorzutäuschen,
   die die Daten nicht hergeben.

## Feldvalidierung

Bevor das produktiv geht: fünf bis zehn Bänke bei Sonnenschein aufsuchen,
fotografieren, mit `05_validate.py --plot` vergleichen. Systematische Fehler
(falsches Vorzeichen beim Azimut, Zeitzonenverschiebung, vertauschte
Rechts-/Hochwerte) fallen dabei sofort auf und kosten hinterher ein
Vielfaches.
