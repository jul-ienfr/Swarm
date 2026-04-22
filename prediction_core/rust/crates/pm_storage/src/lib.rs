use pm_executor::OrderIntent;
use pm_ledger::LedgerEnvelope;
use pm_signal::SignalEvent;
use pm_types::{
    execution_status_str, market_event_type_str, order_side_str, ExecutionStatus, MarketEvent,
};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct MarketEventRow {
    pub event_type: &'static str,
    pub market_id: String,
    pub best_bid: Option<f64>,
    pub best_ask: Option<f64>,
    pub last_trade_price: Option<f64>,
    pub quote_age_ms: Option<i64>,
}

#[derive(Debug, Clone, Serialize)]
pub struct SignalEventRow {
    pub market_id: String,
    pub side: &'static str,
    pub fair_value: f64,
    pub observed_price: f64,
    pub edge_bps: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct OrderIntentRow {
    pub market_id: String,
    pub side: &'static str,
    pub price: f64,
    pub size: f64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExecutionReportRow {
    pub market_id: String,
    pub status: &'static str,
    pub message: Option<String>,
}

pub fn market_event_row(event: &MarketEvent) -> MarketEventRow {
    MarketEventRow {
        event_type: market_event_type_str(&event.event_type),
        market_id: event.market_id.clone(),
        best_bid: event.best_bid,
        best_ask: event.best_ask,
        last_trade_price: event.last_trade_price,
        quote_age_ms: event.quote_age_ms,
    }
}

pub fn signal_event_row(signal: &SignalEvent) -> SignalEventRow {
    SignalEventRow {
        market_id: signal.market_id.clone(),
        side: order_side_str(&signal.side),
        fair_value: signal.fair_value,
        observed_price: signal.observed_price,
        edge_bps: signal.edge_bps,
    }
}

pub fn order_intent_row(intent: &OrderIntent) -> OrderIntentRow {
    OrderIntentRow {
        market_id: intent.market_id.clone(),
        side: order_side_str(&intent.side),
        price: intent.price,
        size: intent.size,
    }
}

pub fn execution_report_row(
    market_id: impl Into<String>,
    status: &ExecutionStatus,
    message: Option<String>,
) -> ExecutionReportRow {
    ExecutionReportRow {
        market_id: market_id.into(),
        status: execution_status_str(status),
        message,
    }
}

pub fn market_event_ledger(event: &MarketEvent) -> Result<String, serde_json::Error> {
    LedgerEnvelope {
        kind: "market_event",
        payload: market_event_row(event),
    }
    .to_json()
}

pub fn signal_event_ledger(signal: &SignalEvent) -> Result<String, serde_json::Error> {
    LedgerEnvelope {
        kind: "signal_event",
        payload: signal_event_row(signal),
    }
    .to_json()
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use pm_types::{MarketEventType, OrderSide, Venue};
    use uuid::Uuid;

    #[test]
    fn market_event_row_uses_explicit_snake_case_type() {
        let event = MarketEvent {
            event_id: Uuid::new_v4(),
            ts: Utc::now(),
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            event_type: MarketEventType::BookSnapshot,
            best_bid: Some(0.49),
            best_ask: Some(0.50),
            last_trade_price: None,
            bid_size: None,
            ask_size: None,
            quote_age_ms: Some(15),
        };

        let row = market_event_row(&event);
        assert_eq!(row.event_type, "book_snapshot");
    }

    #[test]
    fn signal_event_row_uses_explicit_snake_case_side() {
        let signal = SignalEvent {
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            side: OrderSide::BuyYes,
            fair_value: 0.52,
            observed_price: 0.50,
            edge_bps: 400.0,
        };

        let row = signal_event_row(&signal);
        assert_eq!(row.side, "buy_yes");
    }

    #[test]
    fn market_event_ledger_serializes_kind_marker() {
        let event = MarketEvent {
            event_id: Uuid::new_v4(),
            ts: Utc::now(),
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            event_type: MarketEventType::Quote,
            best_bid: Some(0.49),
            best_ask: Some(0.50),
            last_trade_price: None,
            bid_size: None,
            ask_size: None,
            quote_age_ms: Some(10),
        };

        let payload = market_event_ledger(&event).expect("expected json payload");
        assert!(payload.contains("\"kind\":\"market_event\""));
        assert!(payload.contains("\"event_type\":\"quote\""));
    }
}
