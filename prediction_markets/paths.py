from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_PREDICTION_MARKETS_ROOT = Path(__file__).resolve().parent.parent / "data" / "prediction_markets"


@dataclass(frozen=True)
class PredictionMarketPaths:
    root: Path = DEFAULT_PREDICTION_MARKETS_ROOT

    @property
    def market_catalog_dir(self) -> Path:
        return self.root / "market_catalog"

    @property
    def orderbooks_dir(self) -> Path:
        return self.root / "orderbooks"

    @property
    def trades_dir(self) -> Path:
        return self.root / "trades"

    @property
    def resolution_dir(self) -> Path:
        return self.root / "resolution"

    @property
    def evidence_dir(self) -> Path:
        return self.root / "evidence"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def benchmarks_dir(self) -> Path:
        return self.root / "benchmarks"

    @property
    def paper_trades_dir(self) -> Path:
        return self.root / "paper_trades"

    @property
    def replay_dir(self) -> Path:
        return self.root / "replay"

    @property
    def registry_path(self) -> Path:
        return self.runs_dir / "index.json"

    @property
    def resolution_cache_path(self) -> Path:
        return self.resolution_dir / "policies.json"

    @property
    def evidence_index_path(self) -> Path:
        return self.evidence_dir / "index.json"

    def ensure_layout(self) -> None:
        for directory in [
            self.root,
            self.market_catalog_dir,
            self.orderbooks_dir,
            self.trades_dir,
            self.resolution_dir,
            self.evidence_dir,
            self.runs_dir,
            self.reports_dir,
            self.benchmarks_dir,
            self.paper_trades_dir,
            self.replay_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def replay_run_dir(self, run_id: str) -> Path:
        return self.replay_dir / run_id

    def run_manifest_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "manifest.json"

    def snapshot_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "snapshot.json"

    def forecast_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "forecast.json"

    def recommendation_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "recommendation.json"

    def decision_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "decision.json"

    def report_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "report.json"

    def replay_report_path(self, run_id: str) -> Path:
        return self.replay_run_dir(run_id) / "report.json"

    def benchmark_path(self, benchmark_id: str) -> Path:
        return self.benchmarks_dir / f"{benchmark_id}.json"

    def paper_trade_path(self, trade_id: str) -> Path:
        return self.paper_trades_dir / f"{trade_id}.json"

    def evidence_path(self, evidence_id: str, market_id: str | None = None) -> Path:
        if market_id:
            return self.evidence_dir / market_id / f"{evidence_id}.json"
        return self.evidence_dir / f"{evidence_id}.json"

    def market_catalog_path(self, market_id: str) -> Path:
        return self.market_catalog_dir / f"{market_id}.json"


def default_prediction_market_paths() -> PredictionMarketPaths:
    paths = PredictionMarketPaths()
    paths.ensure_layout()
    return paths
