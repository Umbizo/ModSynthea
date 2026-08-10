#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
rm -rf output/smoke
./run_synthea -p "${1:-400}" -s 4444 \
  --exporter.baseDirectory "output/smoke/" \
  --exporter.csv.export true \
  2>&1 | tee output/smoke_run.log
! grep -E "Exception|StackTrace|	at " output/smoke_run.log
