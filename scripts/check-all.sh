#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "Python: pip install runtime and dev requirements"
python -m pip install -q -r backend/requirements.txt -r requirements-dev.txt

if [[ ! -d frontend/node_modules ]]; then
  echo "npm install --prefix frontend"
  npm --prefix frontend install
fi

echo "npm run check"
npm run check
