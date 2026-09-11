#!/usr/bin/env bash
# Stellt die auslieferbare Seite in public/ zusammen.
# Wird sowohl von GitHub Actions als auch vor "firebase deploy" benutzt.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f data/horizons.min.json ]; then
  echo "data/horizons.min.json fehlt. Erst: python scripts/06_publish.py --bundle" >&2
  exit 1
fi

rm -rf public
mkdir -p public
cp frontend/index.html frontend/sonnenbank.js public/
cp data/horizons.min.json public/

# Optional: oeffentliche Titel der Baenke. Nur bewusst freigegebene Felder,
# keine Nutzernamen, keine Fotos.
if [ -f data/benches.public.json ]; then
  cp data/benches.public.json public/benches.json
fi

echo "public/ fertig ($(du -sh public | cut -f1))"
