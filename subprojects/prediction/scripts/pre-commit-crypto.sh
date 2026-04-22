#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

collect_staged_files() {
  if [[ -n "${HERMES_PRECOMMIT_STAGED_FILES:-}" ]]; then
    printf '%s\n' "$HERMES_PRECOMMIT_STAGED_FILES"
  else
    git diff --cached --name-only --diff-filter=ACMR
  fi
}

should_run_crypto_tests() {
  local staged_files
  staged_files="$(collect_staged_files)"

  if [[ -z "$staged_files" ]]; then
    return 1
  fi

  while IFS= read -r file; do
    case "$file" in
      subprojects/prediction/src/lib/prediction-markets/crypto/*|\
      subprojects/prediction/src/app/api/v1/prediction-markets/crypto/*|\
      subprojects/prediction/src/lib/__tests__/prediction-markets-crypto*|\
      subprojects/prediction/docs/CRYPTO.md|\
      subprojects/prediction/docs/CRYPTO-implementation-plan.md|\
      subprojects/prediction/CRYPTO_TEST_MATRIX.md|\
      subprojects/prediction/scripts/test-crypto.sh|\
      subprojects/prediction/scripts/pre-commit-crypto.sh|\
      subprojects/prediction/package.json)
        return 0
        ;;
    esac
  done <<< "$staged_files"

  return 1
}

if ! should_run_crypto_tests; then
  echo "[crypto-pre-commit] no staged crypto changes -> skip"
  exit 0
fi

echo "[crypto-pre-commit] staged crypto changes detected -> npm run test:crypto"
npm run test:crypto
