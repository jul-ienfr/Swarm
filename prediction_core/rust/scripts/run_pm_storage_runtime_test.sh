#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_dir="$repo_root"
crate_name="pm_storage"
postgres_image="${POSTGRES_IMAGE:-postgres:16}"
rust_image="${RUST_IMAGE:-rust:1.89-bookworm}"
database_name="${PM_STORAGE_TEST_DB:-pm_storage_runtime}"

default_tests=(
  "sqlx_runtime_allows_repeated_schema_apply_against_real_postgres"
  "sqlx_runtime_preserves_insertability_after_repeated_schema_apply_against_real_postgres"
  "sqlx_runtime_commits_multi_table_transaction_against_real_postgres"
  "sqlx_runtime_rejects_duplicate_market_event_insert_against_real_postgres"
)

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required" >&2
  exit 1
fi

if [[ ! -f "$workspace_dir/Cargo.toml" ]]; then
  echo "Rust workspace not found at $workspace_dir" >&2
  exit 1
fi

if [[ $# -gt 0 ]]; then
  tests=("$@")
else
  tests=("${default_tests[@]}")
fi

run_one() {
  local test_name="$1"
  local network="pm_storage_runtime_test_$(date +%s)_$RANDOM"
  local container="pm-storage-pg-$RANDOM"
  local database_url="postgres://postgres:postgres@${container}:5432/${database_name}"

  cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
    docker network rm "$network" >/dev/null 2>&1 || true
  }

  trap cleanup RETURN

  docker network create "$network" >/dev/null

  docker run -d \
    --name "$container" \
    --network "$network" \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB="$database_name" \
    "$postgres_image" >/dev/null

  until docker exec "$container" pg_isready -U postgres -d "$database_name" >/dev/null 2>&1; do
    sleep 1
  done

  cargo_args=(test -p "$crate_name" "$test_name" -- --nocapture)

  echo "[pm_storage runtime] DATABASE_URL=postgres://postgres:***@${container}:5432/${database_name}"
  echo "[pm_storage runtime] cargo ${cargo_args[*]}"

  docker run --rm \
    --network "$network" \
    -v "$repo_root":/workspace \
    -w /workspace \
    -e DATABASE_URL="$database_url" \
    "$rust_image" \
    bash -lc 'export PATH=/usr/local/cargo/bin:$PATH; cargo "$@"' bash "${cargo_args[@]}"
}

for test_name in "${tests[@]}"; do
  run_one "$test_name"
done
