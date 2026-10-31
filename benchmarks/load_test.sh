#!/usr/bin/env sh
# Throughput under concurrency with ApacheBench, run from a container on the compose network
# so the measurement excludes host port-forwarding overhead (large on Docker Desktop for Windows).
#   docker compose up -d --wait && sh benchmarks/load_test.sh [concurrency] [requests]
set -e
C=${1:-16}
N=${2:-3000}
NET=${NET:-predictive-maintenance_default}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$HERE/results"
OUT="$HERE/results/load_ab_c${C}.txt"
BODY='{"Type":"M","Air temperature":298.1,"Process temperature":308.6,"Rotational speed":1551,"Torque":42.8,"Tool wear":10}'
WORKERS=$(docker compose exec -T api sh -c 'echo $PM_WORKERS' 2>/dev/null || echo "?")

MSYS_NO_PATHCONV=1 docker run --rm --network "$NET" httpd:2.4-alpine sh -c "
  printf '%s' '$BODY' > /tmp/body.json
  echo '# /api/predict?explain=false | concurrency=$C | requests=$N | api workers=$WORKERS | $(date -u +%Y-%m-%dT%H:%MZ)'
  ab -q -n $N -c $C -p /tmp/body.json -T application/json 'http://api:8000/api/predict?explain=false' \
    | grep -E 'Complete requests|Failed requests|Non-2xx|Requests per second|Time per request.*\(mean\)|  50%|  95%|  99%'
" | tee "$OUT"
echo "Saved $OUT"
