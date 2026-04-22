use pm_book::TopOfBook;
use pm_executor::{build_order_intent, OrderIntent};
use pm_risk::{approve_if_spread_not_crossed, RiskDecision};
use pm_signal::{signal_from_book, SignalConfig, SignalEvent};
use pm_storage::{execution_report_row, ExecutionReportRow};
use pm_types::{ExecutionStatus, MarketEvent};

pub struct LiveEngineOutput {
    pub signal: Option<SignalEvent>,
    pub risk_decision: RiskDecision,
    pub order_intent: Option<OrderIntent>,
    pub execution_report: ExecutionReportRow,
}

pub fn engine_name() -> &'static str {
    "prediction_core_live_engine"
}

pub fn process_market_event(event: &MarketEvent, config: &SignalConfig) -> LiveEngineOutput {
    let mut book = TopOfBook::default();
    book.apply(event);

    let risk_decision = approve_if_spread_not_crossed(book.best_bid, book.best_ask);
    let signal = signal_from_book(config, event.venue.clone(), event.market_id.clone(), &book);

    if signal.is_none() {
        return LiveEngineOutput {
            signal: None,
            risk_decision,
            order_intent: None,
            execution_report: execution_report_row(
                event.market_id.clone(),
                &ExecutionStatus::Rejected,
                Some("no_signal".to_string()),
            ),
        };
    }

    if risk_decision.decision != pm_types::RiskDecisionStatus::Approved {
        return LiveEngineOutput {
            signal,
            risk_decision,
            order_intent: None,
            execution_report: execution_report_row(
                event.market_id.clone(),
                &ExecutionStatus::Rejected,
                Some("risk_rejected".to_string()),
            ),
        };
    }

    let signal = signal.expect("signal should exist after prior guard");
    let order_intent = build_order_intent(
        signal.market_id.clone(),
        signal.side.clone(),
        signal.observed_price,
    );

    LiveEngineOutput {
        signal: Some(signal),
        risk_decision,
        execution_report: execution_report_row(
            event.market_id.clone(),
            &ExecutionStatus::Accepted,
            None,
        ),
        order_intent: Some(order_intent),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use pm_types::{MarketEventType, OrderSide, Venue};
    use uuid::Uuid;

    fn base_event(best_bid: Option<f64>, best_ask: Option<f64>) -> MarketEvent {
        MarketEvent {
            event_id: Uuid::new_v4(),
            ts: Utc::now(),
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            event_type: MarketEventType::Quote,
            best_bid,
            best_ask,
            last_trade_price: None,
            bid_size: None,
            ask_size: None,
            quote_age_ms: Some(5),
        }
    }

    #[test]
    fn exposes_engine_name() {
        assert_eq!(engine_name(), "prediction_core_live_engine");
    }

    #[test]
    fn process_market_event_accepts_signal_and_builds_order() {
        let event = base_event(Some(0.49), Some(0.50));
        let output = process_market_event(
            &event,
            &SignalConfig {
                min_edge_bps: 5.0,
                default_side: OrderSide::BuyYes,
            },
        );

        assert!(output.signal.is_some());
        assert!(output.order_intent.is_some());
        assert_eq!(output.execution_report.status, "accepted");
    }

    #[test]
    fn process_market_event_rejects_when_signal_is_missing() {
        let event = base_event(Some(0.4995), Some(0.5000));
        let output = process_market_event(
            &event,
            &SignalConfig {
                min_edge_bps: 20.0,
                default_side: OrderSide::BuyYes,
            },
        );

        assert!(output.signal.is_none());
        assert!(output.order_intent.is_none());
        assert_eq!(output.execution_report.status, "rejected");
        assert_eq!(output.execution_report.message.as_deref(), Some("no_signal"));
    }

    #[test]
    fn process_market_event_rejects_when_risk_fails() {
        let event = base_event(Some(0.51), Some(0.50));
        let output = process_market_event(
            &event,
            &SignalConfig {
                min_edge_bps: 5.0,
                default_side: OrderSide::BuyYes,
            },
        );

        assert_eq!(output.risk_decision.decision, pm_types::RiskDecisionStatus::Rejected);
        assert!(output.order_intent.is_none());
        assert_eq!(output.execution_report.status, "rejected");
        assert_eq!(output.execution_report.message.as_deref(), Some("risk_rejected"));
    }
}
