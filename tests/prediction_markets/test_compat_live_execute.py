from __future__ import annotations

import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if "prediction_markets" not in sys.modules:
    package = types.ModuleType("prediction_markets")
    package.__path__ = [str(Path(__file__).resolve().parents[2] / "prediction_markets")]
    sys.modules["prediction_markets"] = package

from prediction_markets.compat import _build_default_live_execution_transport_bindings
from prediction_markets.market_execution import MarketExecutionOrder, MarketExecutionOrderType
from prediction_markets.models import TradeSide, VenueName


def _order() -> MarketExecutionOrder:
    return MarketExecutionOrder(
        run_id="run_live_compat",
        market_id="pm_live_compat",
        venue=VenueName.polymarket,
        position_side=TradeSide.yes,
        execution_side=TradeSide.buy,
        order_type=MarketExecutionOrderType.limit,
        requested_quantity=10.0,
        requested_notional=25.0,
        limit_price=0.51,
    )


def test_default_live_execution_transport_bindings_post_to_env_backed_http_endpoints(monkeypatch) -> None:
    captured_requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            raw_body = self.rfile.read(int(self.headers.get("content-length", "0") or 0)).decode("utf-8")
            body = json.loads(raw_body) if raw_body else {}
            captured_requests.append(
                {
                    "path": self.path,
                    "authorization": self.headers.get("authorization"),
                    "body": body,
                }
            )
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "venue_order_id": f"external_{self.path.strip('/').replace('/', '_')}",
                        "venue_order_status": "cancelled" if self.path.endswith("/cancel") else "submitted",
                    }
                ).encode("utf-8")
            )

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        monkeypatch.setenv("POLYMARKET_EXECUTION_BACKEND", "live")
        monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_TOKEN", "test-token")
        monkeypatch.setenv("POLYMARKET_EXECUTION_AUTH_SCHEME", "bearer")
        monkeypatch.setenv("POLYMARKET_EXECUTION_BASE_URL", base_url)
        monkeypatch.setenv("POLYMARKET_EXECUTION_LIVE_ORDER_PATH", "/orders")
        monkeypatch.setenv("POLYMARKET_EXECUTION_CANCEL_PATH", "/orders/cancel")

        submitters, cancel_submitters = _build_default_live_execution_transport_bindings()

        submit_payload = submitters[VenueName.polymarket](_order(), {"requested_by": "tester"})
        cancel_payload = cancel_submitters[VenueName.polymarket](_order(), {"reason": "user_cancelled"})

        assert [item["path"] for item in captured_requests] == ["/orders", "/orders/cancel"]
        assert captured_requests[0]["authorization"] == "Bearer test-token"
        assert captured_requests[0]["body"]["action"] == "place_order"
        assert captured_requests[0]["body"]["order"]["run_id"] == "run_live_compat"
        assert captured_requests[1]["body"]["action"] == "cancel_order"
        assert captured_requests[1]["body"]["request"]["reason"] == "user_cancelled"

        assert submit_payload["venue_order_source"] == "external"
        assert submit_payload["venue_order_status"] == "submitted"
        assert submit_payload["venue_order_path"] == f"{base_url}/orders"
        assert cancel_payload["venue_order_status"] == "cancelled"
        assert cancel_payload["venue_order_cancel_path"] == f"{base_url}/orders/cancel"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
