#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
Usage: ./scripts/test-crypto.sh <level>

Levels:
  p1       Core crypto critical batch
  p2       Crypto + integration batch
  merge    Full pre-merge gate
  minimal  Alias of p1
  safe     Alias of p2
EOF
}

run_p1() {
  npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts \
    src/lib/__tests__/prediction-markets-crypto-subproject.test.ts \
    src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts \
    src/lib/__tests__/prediction-markets-crypto-screener.test.ts \
    src/lib/__tests__/prediction-markets-crypto-routes.test.ts
}

run_p2() {
  npm exec --yes --package vitest vitest -- run --config ./vitest.config.ts \
    src/lib/__tests__/prediction-markets-crypto-subproject.test.ts \
    src/lib/__tests__/prediction-markets-crypto-taxonomy.test.ts \
    src/lib/__tests__/prediction-markets-crypto-screener.test.ts \
    src/lib/__tests__/prediction-markets-crypto-routes.test.ts \
    src/lib/__tests__/dashboard-models.test.ts \
    src/lib/__tests__/prediction-markets-dashboard-route.test.ts
}

run_merge() {
  npm run test:ops && npm run test:dashboard && npm run typecheck
}

LEVEL="${1:-}"

case "$LEVEL" in
  p1|minimal)
    run_p1
    ;;
  p2|safe)
    run_p2
    ;;
  merge)
    run_merge
    ;;
  -h|--help|help|'')
    usage
    ;;
  *)
    echo "Unknown level: $LEVEL" >&2
    echo >&2
    usage >&2
    exit 1
    ;;
esac
