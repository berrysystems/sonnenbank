"""Zentrale Konfiguration fuer die Sonnenstand-Pipeline (Oberbergischer Kreis)."""
from pathlib import Path

# ---------------------------------------------------------------- Verzeichnisse
ROOT = Path(__file__).parent
DATA = ROOT / "data"
TILES_LOD2 = DATA / "lod2"        # CityGML-Kacheln
TILES_DGM = DATA / "dgm1"         # DGM1-GeoTIFF-Kacheln
TILES_NDOM = DATA / "ndom50"      # nDOM50-GeoTIFF-Kacheln (Vegetation)
BENCHES_FILE = DATA / "benches.json"
DEM_COARSE = DATA / "dem10m.tif"  # abgeleitetes 10-m-Mosaik fuer den Fernhorizont
HORIZONS_FILE = DATA / "horizons.json"

for d in (DATA, TILES_LOD2, TILES_DGM, TILES_NDOM):
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- Koordinaten
CRS_WGS84 = "EPSG:4326"
CRS_UTM32 = "EPSG:25832"   # ETRS89 / UTM Zone 32N - Bezugssystem der NRW-Geobasisdaten

# ---------------------------------------------------------------- Downloadquellen
# Open Data, Datenlizenz Deutschland Zero 2.0 (Geobasis NRW)
URL_LOD2 = "https://www.opengeodata.nrw.de/produkte/geobasis/3dg/lod2_gml/lod2_gml/"
URL_DGM1 = "https://www.opengeodata.nrw.de/produkte/geobasis/hm/dgm1_tiff/dgm1_tiff/"
# Normalisiertes Oberflaechenmodell: Hoehe ueber Grund, 50 cm, enthaelt Vegetation
URL_NDOM50 = "https://www.opengeodata.nrw.de/produkte/geobasis/hm/ndom50_tiff/ndom50_tiff/"

# ---------------------------------------------------------------- Modellparameter
AUGENHOEHE = 1.20          # m ueber Gelaende - sitzende Person
RADIUS_GEBAEUDE = 600.0    # m - Suchradius fuer LoD2-Gebaeude
RADIUS_GELAENDE = 5000.0   # m - Suchradius fuer den Gelaendehorizont
SCHRITT_GELAENDE = 10.0    # m - Abtastschritt entlang der Gelaende-Strahlen
SCHRITT_UMRING = 1.0       # m - Verdichtung der Gebaeudeumringe
DEM_AUFLOESUNG = 10.0      # m - Rasterweite des abgeleiteten Fernhorizont-DEM
AZIMUT_SCHRITTE = 360      # 1 Grad Aufloesung

# Vegetation aus dem nDOM50
RADIUS_VEGETATION = 150.0  # m - darueber hinaus sind Baeume kaum noch relevant
SCHRITT_VEGETATION = 1.0   # m - Abtastschritt entlang der Strahlen
VEG_MIN_HOEHE = 2.0        # m - darunter ist es Gebuesch, kein Schattenspender
VEG_RASTER = 1.0           # m - Arbeitsaufloesung (aus 0.5 m per Maximum)
GEBAEUDE_PUFFER = 1.5      # m - Grundrisse etwas aufweiten beim Ausmaskieren

ERDRADIUS = 6371000.0
REFRAKTION_K = 0.13        # Standard-Refraktionskoeffizient

# ---------------------------------------------------------------- Firebase
FIRESTORE_COLLECTION = "benches"
FIRESTORE_CREDENTIALS = ROOT / "serviceAccountKey.json"
# Feldnamen im Dokument. Punktnotation fuer verschachtelte Felder erlaubt.
FELD_GEOPOINT = "geo.geopoint"      # geoflutterfire_plus legt den Punkt hier ab
FELD_LAT = "lat"                    # Fallback, falls flach gespeichert
FELD_LON = "lng"
FELD_AUSRICHTUNG = "imageBearings"  # Liste von Kompassrichtungen je Foto

# Nur diese Status werden verarbeitet
STATUS_ERLAUBT = {"active"}
# Datensaetze, bei denen die Bilderkennung keine Bank gefunden hat, ueberspringen
AI_FILTER = True
# Zusaetzliche Felder, die zur spaeteren Gegenpruefung mitgenommen werden
FELDER_UEBERNEHMEN = ["title", "hasShade", "tags", "elevation",
                      "solarScore", "needsReview", "importSource"]

# ---------------------------------------------------------------- Veroeffentlichung
FELD_HORIZONT = "horizonB64"       # kompaktes Profil im Bank-Dokument
FELD_HORIZONT_VERSION = "horizonVersion"
HORIZONT_VERSION = 1               # bei Modelländerungen hochzaehlen
BUNDLE_FILE = DATA / "horizons.min.json"
FELD_HORIZONT_VEG = "horizonVegB64"   # Profil inklusive Bewuchs
