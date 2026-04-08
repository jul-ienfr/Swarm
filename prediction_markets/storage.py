from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PREDICTION_MARKETS_DATA_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "prediction_markets"
)


def ensure_storage_layout(base_dir: str | Path | None = None) -> Path:
    root = Path(base_dir or DEFAULT_PREDICTION_MARKETS_DATA_DIR)
    for relative in [
        "market_catalog",
        "orderbooks",
        "trades",
        "resolution",
        "evidence",
        "runs",
        "paper_trades",
        "replay",
    ]:
        (root / relative).mkdir(parents=True, exist_ok=True)
    return root


def run_dir(run_id: str, *, base_dir: str | Path | None = None) -> Path:
    root = ensure_storage_layout(base_dir)
    path = root / "runs" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(path: str | Path, payload: Any) -> Path:
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)

    def _normalize(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return {str(key): _normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_normalize(item) for item in value]
        return value

    content = _normalize(payload)
    serialized = json.dumps(content, indent=2, sort_keys=True, default=str)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(resolved.parent), encoding="utf-8") as handle:
        handle.write(serialized)
        temp_path = Path(handle.name)
    temp_path.replace(resolved)
    return resolved


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def utc_isoformat(value: Any | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def file_signature(path: str | Path) -> dict[str, Any]:
    resolved = Path(path)
    signature: dict[str, Any] = {"path": str(resolved), "exists": resolved.exists()}
    if not resolved.exists():
        return signature

    stat = resolved.stat()
    digest = _sha256_file(resolved)
    signature.update(
        {
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "timestamp": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "sha256": digest,
            "content_hash": digest,
        }
    )
    return signature


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
