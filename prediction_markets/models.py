from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


SchemaVersion = Literal["v1"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _stable_content_hash(payload: Any) -> str:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _source_refs(*values: Any) -> list[str]:
    refs: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        for item in candidates:
            text = str(item).strip()
            if text and text not in refs:
                refs.append(text)
    return refs


def _normalized_text(value: Any) -> str:
    return " ".join(str(value).strip().split())


def _normalize_currency_code(value: Any) -> str | None:
    if value is None:
        return None
    text = _normalized_text(value)
    if not text:
        return None
    return text.upper()


def _safe_non_negative_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _safe_non_negative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _position_notional_surface(position: Any) -> float:
    quantity = _safe_non_negative_float(abs(getattr(position, "quantity", 0.0))) or 0.0
    price = _safe_non_negative_float(getattr(position, "mark_price", None))
    if price is None:
        price = _safe_non_negative_float(getattr(position, "entry_price", 0.0)) or 0.0
    return round(quantity * price, 6)


def _capital_by_market_surface(positions: list[Any]) -> dict[str, float]:
    capital: dict[str, float] = {}
    for position in positions:
        market_id = _first_non_empty(getattr(position, "market_id", None))
        if not market_id:
            continue
        capital[market_id] = round(capital.get(market_id, 0.0) + _position_notional_surface(position), 6)
    return capital


def _transfer_latency_surface(venue: Any, positions: list[Any], metadata: dict[str, Any]) -> float:
    metadata_latency = _safe_non_negative_float(metadata.get("transfer_latency_estimate_ms"))
    if metadata_latency is not None:
        return round(metadata_latency, 2)
    venues = {str(getattr(position, "venue", "")) for position in positions if getattr(position, "venue", None) is not None}
    if venue is not None:
        venues.add(str(venue))
    venue_count = len({item for item in venues if item})
    if venue_count <= 1:
        return 0.0
    position_count = len(positions)
    base_ms = 15_000.0
    venue_component = 3_500.0 * max(0, venue_count - 1)
    position_component = 750.0 * max(0, position_count - 1)
    return round(base_ms + venue_component + position_component, 2)


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = _normalized_text(value)
        if text:
            return text
    return None


def _metadata_string(source: Any, *keys: str) -> str | None:
    metadata = getattr(source, "metadata", {}) or {}
    raw = getattr(source, "raw", {}) or {}
    for key in keys:
        for container in (metadata, raw):
            if not isinstance(container, dict):
                continue
            text = _first_non_empty(container.get(key))
            if text:
                return text
    return None


def _metadata_value(source: Any, *keys: str) -> Any:
    metadata = getattr(source, "metadata", {}) or {}
    if not isinstance(metadata, dict):
        return None
    for key in keys:
        if key not in metadata:
            continue
        value = metadata.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            if _normalized_text(value):
                return value
            continue
        if isinstance(value, dict) and not value:
            continue
        if isinstance(value, (list, tuple, set)) and not value:
            continue
        return value
    return None


def _metadata_list(source: Any, *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        value = _metadata_value(source, key)
        if value is None:
            continue
        values.extend(_source_refs(value))
    return _source_refs(values)


def _metadata_dict(source: Any, *keys: str) -> dict[str, Any]:
    value = _metadata_value(source, *keys)
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    return {}


def _metadata_float(source: Any, *keys: str) -> float | None:
    value = _metadata_value(source, *keys)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _confidence_band_surface(low: float | None, high: float | None, center: float | None = None) -> dict[str, Any]:
    band: dict[str, Any] = {}
    if low is not None:
        band["low"] = round(max(0.0, min(1.0, float(low))), 6)
    if high is not None:
        band["high"] = round(max(0.0, min(1.0, float(high))), 6)
    if center is not None:
        band["center"] = round(max(0.0, min(1.0, float(center))), 6)
    return band


def _projection_order() -> dict[str, int]:
    return {
        ExecutionProjectionOutcome.blocked.value: 0,
        ExecutionProjectionOutcome.paper.value: 1,
        ExecutionProjectionOutcome.shadow.value: 2,
        ExecutionProjectionOutcome.live.value: 3,
    }


def _projection_rank(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, Enum):
        value = value.value
    text = str(value).strip().lower()
    return _projection_order().get(text, 0)


def min_projection_mode(*values: Any) -> ExecutionProjectionOutcome:
    if not values:
        return ExecutionProjectionOutcome.blocked
    lowest_rank = 10**9
    lowest_value: Any = ExecutionProjectionOutcome.blocked
    for value in values:
        rank = _projection_rank(value)
        if rank < lowest_rank:
            lowest_rank = rank
            lowest_value = value
    if isinstance(lowest_value, Enum):
        lowest_value = lowest_value.value
    text = str(lowest_value).strip().lower()
    if text == ExecutionProjectionOutcome.blocked.value:
        return ExecutionProjectionOutcome.blocked
    return ExecutionProjectionOutcome(text)


def _coerce_projection_mode(value: Any) -> ExecutionProjectionMode:
    if isinstance(value, ExecutionProjectionMode):
        return value
    if isinstance(value, ExecutionProjectionOutcome):
        if value == ExecutionProjectionOutcome.blocked:
            return ExecutionProjectionMode.paper
        return ExecutionProjectionMode(value.value)
    text = str(value).strip().lower()
    if text == ExecutionProjectionOutcome.blocked.value:
        return ExecutionProjectionMode.paper
    return ExecutionProjectionMode(text)


def _projection_summary_text(
    *,
    requested: ExecutionProjectionMode,
    projected: ExecutionProjectionOutcome,
    verdict: ExecutionProjectionVerdict,
    blocking_reasons: list[str],
    downgrade_reasons: list[str],
) -> str:
    pieces = [f"requested={requested.value}", f"projected={projected.value}", f"verdict={verdict.value}"]
    if blocking_reasons:
        pieces.append("blocked=" + ",".join(blocking_reasons))
    if downgrade_reasons:
        pieces.append("downgraded=" + ",".join(downgrade_reasons))
    return "; ".join(pieces)


class VenueName(str, Enum):
    polymarket = "polymarket"
    kalshi = "kalshi"
    robinhood = "robinhood"
    cryptocom = "cryptocom"
    manifold = "manifold"
    metaculus = "metaculus"
    opinion_trade = "opinion_trade"
    omen = "omen"
    clue = "clue"
    aver = "aver"
    hedgehog = "hedgehog"
    augur = "augur"
    custom = "custom"


class VenueType(str, Enum):
    execution = "execution"
    reference = "reference"
    signal = "signal"
    watchlist = "watchlist"
    experimental = "experimental"
    # Compatibility aliases used in earlier scaffolds.
    execution_equivalent = "execution"
    reference_only = "reference"


class MarketStatus(str, Enum):
    open = "open"
    closed = "closed"
    resolved = "resolved"
    cancelled = "cancelled"
    paused = "paused"
    unknown = "unknown"


class ResolutionStatus(str, Enum):
    clear = "clear"
    ambiguous = "ambiguous"
    manual_review = "manual_review"
    unavailable = "unavailable"


class DecisionAction(str, Enum):
    bet = "bet"
    no_trade = "no_trade"
    wait = "wait"
    manual_review = "manual_review"


class TradeSide(str, Enum):
    yes = "yes"
    no = "no"
    buy = "buy"
    sell = "sell"


class SourceKind(str, Enum):
    official = "official"
    market = "market"
    social = "social"
    news = "news"
    manual = "manual"
    model = "model"
    other = "other"


class PacketCompatibilityMode(str, Enum):
    market_only = "market_only"
    social_bridge = "social_bridge"
    hybrid = "hybrid"


class ExecutionProjectionMode(str, Enum):
    paper = "paper"
    shadow = "shadow"
    live = "live"


class ExecutionProjectionOutcome(str, Enum):
    paper = "paper"
    shadow = "shadow"
    live = "live"
    blocked = "blocked"


class ExecutionProjectionVerdict(str, Enum):
    ready = "ready"
    degraded = "degraded"
    blocked = "blocked"


class ExecutionComplianceStatus(str, Enum):
    authorized = "authorized"
    degraded = "degraded"
    blocked = "blocked"


def _projection_rank(mode: ExecutionProjectionMode | ExecutionProjectionOutcome) -> int:
    normalized = ExecutionProjectionOutcome(mode.value)
    order = {
        ExecutionProjectionOutcome.blocked: 0,
        ExecutionProjectionOutcome.paper: 1,
        ExecutionProjectionOutcome.shadow: 2,
        ExecutionProjectionOutcome.live: 3,
    }
    return order[normalized]


class OrderBookLevel(BaseModel):
    schema_version: SchemaVersion = "v1"
    price: float
    size: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price")
    @classmethod
    def _clamp_price(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class TradeRecord(BaseModel):
    schema_version: SchemaVersion = "v1"
    trade_id: str = Field(default_factory=lambda: f"trade_{uuid4().hex[:12]}")
    price: float
    size: float = 0.0
    side: TradeSide = TradeSide.buy
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("price")
    @classmethod
    def _clamp_price(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @field_validator("timestamp", mode="after")
    @classmethod
    def _normalize_timestamp(cls, value: datetime) -> datetime:
        normalized = _utc_datetime(value)
        return normalized or _utc_now()


class MarketOrderBook(BaseModel):
    schema_version: SchemaVersion = "v1"
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)
    source: str | None = None
    timestamp: datetime = Field(default_factory=_utc_now)

    @property
    def best_bid(self) -> float | None:
        return max((level.price for level in self.bids), default=None)

    @property
    def best_ask(self) -> float | None:
        return min((level.price for level in self.asks), default=None)

    @property
    def mid_probability(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return round((self.best_bid + self.best_ask) / 2.0, 6)

    @property
    def spread_bps(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return round(max(0.0, self.best_ask - self.best_bid) * 10000.0, 2)

    @field_validator("timestamp", mode="after")
    @classmethod
    def _normalize_timestamp(cls, value: datetime) -> datetime:
        normalized = _utc_datetime(value)
        return normalized or _utc_now()


class MarketDescriptor(BaseModel):
    schema_version: SchemaVersion = "v1"
    market_id: str = Field(validation_alias=AliasChoices("market_id", "venue_market_id", "venueMarketId", "id"))
    venue: VenueName = VenueName.polymarket
    venue_type: VenueType = VenueType.execution
    title: str = ""
    question: str = ""
    slug: str | None = None
    status: MarketStatus = MarketStatus.unknown
    source_url: str | None = None
    canonical_event_id: str | None = None
    event_id: str | None = None
    venue_market_id: str | None = None
    open_time: datetime | None = Field(default=None, validation_alias=AliasChoices("open_time", "openTime", "startDate", "start_time"))
    resolution_source: str | None = None
    resolution_source_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("resolution_source_url", "resolutionSourceUrl", "resolution_source_url"),
    )
    resolution_date: datetime | None = None
    close_time: datetime | None = None
    end_date: datetime | None = Field(default=None, validation_alias=AliasChoices("end_date", "endDate", "end_time"))
    volume: float | None = None
    volume_24h: float | None = Field(default=None, validation_alias=AliasChoices("volume_24h", "volume24h", "volume24hr"))
    liquidity: float | None = None
    tags: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Compatibility / provider-neutral extras.
    description: str = ""
    category: str | None = None
    active: bool = True
    closed: bool = False
    outcomes: list[str] = Field(default_factory=list)
    token_ids: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize_state(self) -> "MarketDescriptor":
        self.venue_market_id = _first_non_empty(self.venue_market_id, self.market_id)
        self.event_id = _first_non_empty(self.event_id, self.canonical_event_id)
        self.canonical_event_id = _first_non_empty(self.canonical_event_id, self.event_id)
        self.open_time = _utc_datetime(self.open_time)
        self.resolution_date = _utc_datetime(self.resolution_date)
        self.close_time = _utc_datetime(self.close_time)
        self.end_date = _utc_datetime(self.end_date)
        if self.end_date is None and self.close_time is not None:
            self.end_date = self.close_time
        if self.close_time is None and self.end_date is not None:
            self.close_time = self.end_date
        self.resolution_source_url = _first_non_empty(self.resolution_source_url, self.resolution_source)
        self.resolution_source = _first_non_empty(self.resolution_source, self.resolution_source_url, self.source_url)
        if self.volume_24h is not None:
            self.volume_24h = max(0.0, float(self.volume_24h))
        if not self.title:
            self.title = self.question or self.slug or self.market_id
        if self.status in {MarketStatus.closed, MarketStatus.resolved, MarketStatus.cancelled}:
            self.closed = True
            self.active = False
        elif self.status == MarketStatus.unknown and self.closed:
            self.status = MarketStatus.closed
            self.active = False
        elif self.status == MarketStatus.unknown and self.active:
            self.status = MarketStatus.open
        elif self.closed:
            self.status = MarketStatus.closed
            self.active = False
        elif not self.active and self.status == MarketStatus.open:
            self.status = MarketStatus.paused
        return self

    @property
    def clarity_score(self) -> float:
        base = 0.35
        if self.resolution_source:
            base += 0.25
        if self.source_url:
            base += 0.15
        if self.liquidity is not None:
            base += min(0.2, max(0.0, self.liquidity) / 100000.0)
        if self.status in {MarketStatus.open, MarketStatus.resolved}:
            base += 0.05
        return round(min(1.0, base), 6)


class ResolutionPolicy(BaseModel):
    schema_version: SchemaVersion = "v1"
    policy_id: str = Field(default_factory=lambda: f"respol_{uuid4().hex[:12]}")
    market_id: str
    venue: VenueName
    official_source: str
    source_url: str | None = None
    official_source_url: str | None = Field(default=None, validation_alias=AliasChoices("official_source_url", "officialSourceUrl", "source_url"))
    resolution_authority: str | None = None
    source_kind: SourceKind = SourceKind.official
    resolution_rules: list[str] = Field(default_factory=list)
    rule_text: str = ""
    ambiguity_flags: list[str] = Field(default_factory=list)
    manual_review_required: bool = False
    status: ResolutionStatus = ResolutionStatus.clear
    cached_at: datetime = Field(default_factory=_utc_now, validation_alias=AliasChoices("cached_at", "timestamp"))
    last_verified_at: datetime | None = None
    next_review_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize_policy(self) -> "ResolutionPolicy":
        self.cached_at = _utc_datetime(self.cached_at) or _utc_now()
        self.last_verified_at = _utc_datetime(self.last_verified_at) or self.cached_at
        self.next_review_at = _utc_datetime(self.next_review_at) or _utc_datetime(
            _metadata_value(self, "next_review_at", "review_at", "review_time")
        )
        self.official_source_url = _first_non_empty(self.official_source_url, self.source_url, self.official_source)
        self.source_url = _first_non_empty(self.source_url, self.official_source_url)
        self.resolution_authority = _first_non_empty(self.resolution_authority, self.official_source)
        if not self.rule_text and self.resolution_rules:
            self.rule_text = "; ".join(self.resolution_rules)
        if self.ambiguity_flags:
            self.status = ResolutionStatus.ambiguous
            self.manual_review_required = True
        if not self.official_source:
            self.status = ResolutionStatus.unavailable
            self.manual_review_required = True
        self.source_refs = _source_refs(
            self.source_refs,
            self.official_source,
            self.source_url,
            self.metadata.get("source"),
            self.metadata.get("source_url"),
            self.metadata.get("sources"),
        )
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self


class EvidencePacket(BaseModel):
    schema_version: SchemaVersion = "v1"
    evidence_id: str = Field(default_factory=lambda: f"evid_{uuid4().hex[:12]}")
    market_id: str
    venue: VenueName
    source_kind: SourceKind = SourceKind.manual
    claim: str
    stance: str = "neutral"
    summary: str = ""
    source_url: str | None = None
    raw_text: str | None = None
    confidence: float = 0.5
    freshness_score: float = 0.5
    credibility_score: float = 0.5
    observed_at: datetime = Field(default_factory=_utc_now, validation_alias=AliasChoices("observed_at", "timestamp"))
    published_at: datetime | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @field_validator("confidence", "freshness_score", "credibility_score")
    @classmethod
    def _clamp_probability(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @property
    def evidence_weight(self) -> float:
        return round(self.confidence * self.freshness_score * self.credibility_score, 6)

    @model_validator(mode="after")
    def _set_content_hash(self) -> "EvidencePacket":
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self


class MarketSnapshot(BaseModel):
    schema_version: SchemaVersion = "v1"
    snapshot_id: str = Field(default_factory=lambda: f"snap_{uuid4().hex[:12]}")
    market_id: str
    venue: VenueName = VenueName.polymarket
    venue_type: VenueType = VenueType.execution
    title: str = ""
    question: str = ""
    status: MarketStatus = MarketStatus.unknown
    observed_at: datetime = Field(default_factory=_utc_now, validation_alias=AliasChoices("observed_at", "snapshot_ts", "timestamp"))
    snapshot_ts: datetime | None = None
    orderbook: MarketOrderBook | None = None
    trades: list[TradeRecord] = Field(default_factory=list)
    volume: float | None = None
    liquidity: float | None = None
    open_interest: float | None = None
    close_time: datetime | None = None
    resolution_source: str | None = None
    source_url: str | None = None
    canonical_event_id: str | None = None
    market_implied_probability: float | None = None
    fair_probability_hint: float | None = None
    mid_probability: float | None = None
    spread_bps: float | None = None
    best_bid_yes: float | None = None
    best_ask_yes: float | None = None
    best_bid_no: float | None = None
    best_ask_no: float | None = None
    depth_near_touch: float | None = None
    last_trade_price: float | None = None
    last_trade_ts: datetime | None = None
    staleness_ms: int | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Compatibility / convenience fields.
    price_yes: float | None = None
    price_no: float | None = None
    midpoint_yes: float | None = None
    orderbook_depth: float | None = None
    source_refs: list[str] = Field(default_factory=list)
    content_hash: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _derive_metrics(self) -> "MarketSnapshot":
        self.observed_at = _utc_datetime(self.observed_at) or _utc_now()
        self.snapshot_ts = _utc_datetime(self.snapshot_ts) or self.observed_at
        self.close_time = _utc_datetime(self.close_time)
        self.last_trade_ts = _utc_datetime(self.last_trade_ts)
        if not self.title:
            self.title = self.question or self.market_id
        if self.orderbook:
            mid = self.orderbook.mid_probability
            self.best_bid_yes = self.best_bid_yes if self.best_bid_yes is not None else self.orderbook.best_bid
            self.best_ask_yes = self.best_ask_yes if self.best_ask_yes is not None else self.orderbook.best_ask
            if self.market_implied_probability is None and mid is not None:
                self.market_implied_probability = mid
            if self.mid_probability is None and mid is not None:
                self.mid_probability = mid
            if self.spread_bps is None:
                self.spread_bps = self.orderbook.spread_bps
            if self.midpoint_yes is None and mid is not None:
                self.midpoint_yes = mid
            if self.price_yes is None and mid is not None:
                self.price_yes = mid
            if self.price_no is None and self.price_yes is not None:
                self.price_no = round(max(0.0, 1.0 - self.price_yes), 6)
            if self.best_bid_yes is not None:
                self.best_ask_no = self.best_ask_no if self.best_ask_no is not None else round(max(0.0, 1.0 - self.best_bid_yes), 6)
            if self.best_ask_yes is not None:
                self.best_bid_no = self.best_bid_no if self.best_bid_no is not None else round(max(0.0, 1.0 - self.best_ask_yes), 6)
            if self.depth_near_touch is None:
                bid_depth = sum(level.size for level in self.orderbook.bids if self.best_bid_yes is not None and level.price == self.best_bid_yes)
                ask_depth = sum(level.size for level in self.orderbook.asks if self.best_ask_yes is not None and level.price == self.best_ask_yes)
                near_touch_depth = bid_depth + ask_depth
                if near_touch_depth > 0:
                    self.depth_near_touch = round(float(near_touch_depth), 6)
        if self.market_implied_probability is None:
            self.market_implied_probability = self.fair_probability_hint
        if self.market_implied_probability is None and self.midpoint_yes is not None:
            self.market_implied_probability = self.midpoint_yes
        if self.market_implied_probability is not None:
            self.market_implied_probability = round(max(0.0, min(1.0, float(self.market_implied_probability))), 6)
        if self.mid_probability is None and self.market_implied_probability is not None:
            self.mid_probability = self.market_implied_probability
        if self.mid_probability is not None:
            self.mid_probability = round(max(0.0, min(1.0, float(self.mid_probability))), 6)
        if self.price_yes is None and self.market_implied_probability is not None:
            self.price_yes = self.market_implied_probability
        if self.price_no is None and self.price_yes is not None:
            self.price_no = round(max(0.0, 1.0 - self.price_yes), 6)
        if self.midpoint_yes is None and self.price_yes is not None:
            self.midpoint_yes = self.price_yes
        if self.mid_probability is None and self.best_bid_yes is not None and self.best_ask_yes is not None:
            self.mid_probability = round((self.best_bid_yes + self.best_ask_yes) / 2.0, 6)
        if self.last_trade_price is None and self.trades:
            latest_trade = max(self.trades, key=lambda trade: trade.timestamp)
            self.last_trade_price = latest_trade.price
            self.last_trade_ts = latest_trade.timestamp
        if self.orderbook_depth is None:
            self.orderbook_depth = self.liquidity
        if self.spread_bps is not None:
            self.spread_bps = round(max(0.0, float(self.spread_bps)), 2)
        if self.staleness_ms is None:
            self.staleness_ms = 0
        self.source_refs = _source_refs(
            self.source_refs,
            self.orderbook.source if self.orderbook else None,
            self.resolution_source,
            self.source_url,
            self.raw.get("source"),
            self.raw.get("sources"),
            self.metadata.get("source"),
            self.metadata.get("sources"),
        )
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self


class BridgePacketBase(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    schema_version: SchemaVersion = "v1"
    packet_version: str = "1.0.0"
    packet_kind: str = "bridge"
    compatibility_mode: PacketCompatibilityMode = PacketCompatibilityMode.market_only
    market_only_compatible: bool = True
    source_bundle_id: str | None = None
    source_packet_refs: list[str] = Field(default_factory=list)
    social_context_refs: list[str] = Field(default_factory=list)
    market_context_refs: list[str] = Field(default_factory=list)
    correlation_id: str | None = None
    question: str = ""
    topic: str = ""
    objective: str = ""
    probability_estimate: float | None = None
    confidence_band: dict[str, Any] = Field(default_factory=dict)
    scenarios: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendation: str = ""
    rationale_summary: str = ""
    artifacts: list[str] = Field(default_factory=list)
    mode_used: str = ""
    engine_used: str = ""
    runtime_used: dict[str, Any] = Field(default_factory=dict)
    forecast_ts: datetime | None = None
    next_review_at: datetime | None = None
    resolution_policy_ref: str | None = None
    resolution_policy_missing: bool = False
    comparable_market_refs: list[str] = Field(default_factory=list)
    requires_manual_review: bool = False
    created_at: datetime = Field(default_factory=_utc_now, validation_alias=AliasChoices("created_at", "timestamp"))
    metadata: dict[str, Any] = Field(default_factory=dict)
    contract_id: str = ""
    content_hash: str = ""

    @field_validator("packet_version", mode="before")
    @classmethod
    def _strip_packet_version(cls, value: Any) -> str:
        text = str(value).strip() if value is not None else "1.0.0"
        return text or "1.0.0"

    @field_validator("source_bundle_id", mode="before")
    @classmethod
    def _strip_bundle_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("source_packet_refs", "social_context_refs", "market_context_refs", mode="before")
    @classmethod
    def _normalize_refs(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        normalized: list[str] = []
        for item in candidates:
            text = str(item).strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_metadata(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        return dict(value)

    @field_validator("contract_id", mode="before")
    @classmethod
    def _strip_contract_id(cls, value: Any) -> str:
        text = str(value).strip() if value is not None else ""
        return text

    def contract_surface(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "schema_version": self.schema_version,
            "packet_version": self.packet_version,
            "packet_kind": self.packet_kind,
            "compatibility_mode": self.compatibility_mode.value,
            "market_only_compatible": self.market_only_compatible,
        }

    @model_validator(mode="after")
    def _normalize_bridge(self) -> "BridgePacketBase":
        self.packet_kind = str(self.packet_kind).strip() or "bridge"
        self.packet_version = self.packet_version.strip() or "1.0.0"
        if self.compatibility_mode == PacketCompatibilityMode.market_only:
            self.market_only_compatible = True
        self.correlation_id = _first_non_empty(
            self.correlation_id,
            _metadata_string(self, "correlation_id"),
            _normalized_text(getattr(self, "run_id", "") or "") or None,
            _normalized_text(self.source_bundle_id or "") or None,
            _normalized_text(getattr(self, "forecast_id", "") or "") or None,
            _normalized_text(getattr(self, "recommendation_id", "") or "") or None,
            _normalized_text(getattr(self, "decision_id", "") or "") or None,
        )
        self.question = _first_non_empty(self.question, _metadata_string(self, "question")) or ""
        self.topic = _first_non_empty(self.topic, _metadata_string(self, "topic")) or ""
        self.objective = _first_non_empty(self.objective, _metadata_string(self, "objective")) or ""
        if self.probability_estimate is None:
            self.probability_estimate = _metadata_float(
                self,
                "probability_estimate",
                "forecast_probability",
                "fair_probability",
                "market_implied_probability",
            )
        if not self.confidence_band:
            self.confidence_band = _metadata_dict(self, "confidence_band")
        if self.probability_estimate is None and isinstance(self.confidence_band, dict):
            for key in ("center", "mid", "probability", "fair_probability"):
                candidate = self.confidence_band.get(key)
                if candidate is None:
                    continue
                try:
                    self.probability_estimate = float(candidate)
                    break
                except (TypeError, ValueError):
                    continue
        if not self.scenarios:
            self.scenarios = _metadata_list(self, "scenarios")
        if not self.risks:
            self.risks = _metadata_list(self, "risks", "why_not_now", "blocked_reasons")
        if not self.recommendation:
            self.recommendation = _first_non_empty(
                _metadata_string(self, "recommendation"),
                _metadata_string(self, "recommendation_summary"),
                getattr(getattr(self, "action", None), "value", None),
                getattr(getattr(self, "recommendation_action", None), "value", None),
            ) or ""
        if not self.rationale_summary:
            self.rationale_summary = _first_non_empty(
                _metadata_string(self, "rationale_summary"),
                _metadata_string(self, "summary"),
                _metadata_string(self, "human_summary"),
                _metadata_string(self, "rationale"),
            ) or ""
        if not self.artifacts:
            self.artifacts = _metadata_list(self, "artifacts", "artifact_refs", "evidence_refs", "source_packet_refs")
        if not self.mode_used:
            self.mode_used = _first_non_empty(
                _metadata_string(self, "mode_used"),
                getattr(getattr(self, "compatibility_mode", None), "value", None),
                self.packet_kind,
            ) or ""
        if not self.engine_used:
            self.engine_used = _first_non_empty(
                _metadata_string(self, "engine_used"),
                _metadata_string(self, "model_used"),
                getattr(self, "model_used", None),
            ) or ""
        if not self.runtime_used:
            self.runtime_used = _metadata_dict(self, "runtime_used", "execution_runtime", "runtime")
        if self.forecast_ts is None:
            self.forecast_ts = _utc_datetime(_metadata_value(self, "forecast_ts", "forecast_time", "created_at")) or self.created_at
        if self.resolution_policy_ref is None:
            self.resolution_policy_ref = _first_non_empty(
                _metadata_string(self, "resolution_policy_ref"),
                _metadata_string(self, "resolution_policy_id"),
                getattr(self, "resolution_policy_id", None),
            )
        self.next_review_at = _utc_datetime(self.next_review_at) or _utc_datetime(
            _metadata_value(self, "next_review_at", "review_at", "review_time")
        )
        action_value = _first_non_empty(
            getattr(getattr(self, "decision_action", None), "value", None),
            getattr(getattr(self, "recommendation_action", None), "value", None),
            getattr(getattr(self, "action", None), "value", None),
        )
        resolution_policy_missing = not bool(self.resolution_policy_ref)
        if resolution_policy_missing:
            self.metadata.setdefault("resolution_policy_missing", True)
        self.resolution_policy_missing = bool(
            self.resolution_policy_missing
            or bool(_metadata_value(self, "resolution_policy_missing"))
            or resolution_policy_missing
        )
        if not self.contract_id:
            self.contract_id = f"{self.schema_version}:{self.packet_kind}:{self.packet_version}:{self.compatibility_mode.value}"
        self.metadata.setdefault("contract_id", self.contract_id)
        if self.resolution_policy_missing:
            self.metadata.setdefault("resolution_policy_missing", True)
            self.requires_manual_review = True
        review_needed = bool(
            self.requires_manual_review
            or self.resolution_policy_missing
            or action_value in {"wait", "no_trade", "manual_review"}
            or (self.packet_kind == "execution_readiness" and not bool(getattr(self, "risk_checks_passed", True)))
        )
        if self.next_review_at is None and review_needed:
            self.next_review_at = self.forecast_ts or self.created_at
        if self.next_review_at is not None:
            self.next_review_at = _utc_datetime(self.next_review_at) or self.created_at
        if not self.comparable_market_refs:
            self.comparable_market_refs = _metadata_list(self, "comparable_market_refs")
            if not self.comparable_market_refs:
                self.comparable_market_refs = _source_refs(self.market_context_refs)
        else:
            self.comparable_market_refs = _source_refs(self.comparable_market_refs)
        self.requires_manual_review = bool(
            self.requires_manual_review
            or bool(_metadata_value(self, "requires_manual_review"))
            or bool(_metadata_value(self, "manual_review_required"))
            or bool(getattr(self, "manual_review_required", False))
        )
        self._refresh_content_hash()
        return self

    def _refresh_content_hash(self) -> None:
        self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "BridgePacketBase":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class ForecastPacket(BridgePacketBase):
    schema_version: SchemaVersion = "v1"
    forecast_id: str = Field(default_factory=lambda: f"fcst_{uuid4().hex[:12]}")
    packet_version: str = "1.0.0"
    packet_kind: Literal["forecast"] = "forecast"
    compatibility_mode: PacketCompatibilityMode = PacketCompatibilityMode.market_only
    market_only_compatible: bool = True
    source_bundle_id: str | None = None
    source_packet_refs: list[str] = Field(default_factory=list)
    social_context_refs: list[str] = Field(default_factory=list)
    market_context_refs: list[str] = Field(default_factory=list)
    run_id: str
    market_id: str
    venue: VenueName
    market_implied_probability: float
    fair_probability: float
    confidence_low: float
    confidence_high: float
    edge_bps: float
    edge_after_fees_bps: float
    recommendation_action: DecisionAction = DecisionAction.wait
    manual_review_required: bool = False
    rationale: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    resolution_policy_id: str | None = None
    snapshot_id: str | None = None
    model_used: str = "rule_based"
    social_bridge_used: bool = False
    social_bridge_probability: float | None = None
    social_bridge_delta_bps: float | None = None
    social_bridge_mode: str | None = None
    calibration_notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now, validation_alias=AliasChoices("created_at", "timestamp"))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize(self) -> "ForecastPacket":
        self.market_implied_probability = max(0.0, min(1.0, float(self.market_implied_probability)))
        self.fair_probability = max(0.0, min(1.0, float(self.fair_probability)))
        self.confidence_low = max(0.0, min(1.0, float(self.confidence_low)))
        self.confidence_high = max(self.confidence_low, min(1.0, float(self.confidence_high)))
        self.probability_estimate = self.fair_probability
        self.confidence_band = _confidence_band_surface(self.confidence_low, self.confidence_high, self.fair_probability)
        self.recommendation = _first_non_empty(self.recommendation, self.recommendation_action.value) or ""
        self.rationale_summary = _first_non_empty(self.rationale_summary, self.rationale) or ""
        self.artifacts = _source_refs(self.artifacts, self.evidence_refs)
        self.mode_used = _first_non_empty(self.mode_used, self.compatibility_mode.value) or ""
        self.engine_used = _first_non_empty(self.engine_used, self.model_used) or ""
        self.runtime_used = self.runtime_used or {"model_used": self.model_used, "packet_kind": self.packet_kind}
        self.forecast_ts = self.forecast_ts or self.created_at
        self.resolution_policy_ref = _first_non_empty(self.resolution_policy_ref, self.resolution_policy_id)
        self.comparable_market_refs = _source_refs(self.comparable_market_refs) or _source_refs(self.market_context_refs)
        self.requires_manual_review = bool(self.requires_manual_review or self.manual_review_required)
        self.social_bridge_used = bool(self.social_bridge_used or _metadata_value(self, "social_bridge_used"))
        bridge_probability = _metadata_float(self, "social_bridge_probability")
        bridge_delta_bps = _metadata_float(self, "social_bridge_delta_bps")
        if bridge_probability is not None:
            self.social_bridge_probability = bridge_probability
        if bridge_delta_bps is not None:
            self.social_bridge_delta_bps = bridge_delta_bps
        self.social_bridge_mode = _first_non_empty(self.social_bridge_mode, _metadata_string(self, "social_bridge_mode"))
        self._refresh_content_hash()
        return self

    @property
    def probability_yes(self) -> float:
        return self.fair_probability

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ForecastPacket":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class MarketRecommendationPacket(BridgePacketBase):
    schema_version: SchemaVersion = "v1"
    recommendation_id: str = Field(default_factory=lambda: f"mrec_{uuid4().hex[:12]}")
    packet_version: str = "1.0.0"
    packet_kind: Literal["recommendation"] = "recommendation"
    compatibility_mode: PacketCompatibilityMode = PacketCompatibilityMode.market_only
    market_only_compatible: bool = True
    source_bundle_id: str | None = None
    source_packet_refs: list[str] = Field(default_factory=list)
    social_context_refs: list[str] = Field(default_factory=list)
    market_context_refs: list[str] = Field(default_factory=list)
    run_id: str
    forecast_id: str
    market_id: str
    venue: VenueName
    action: DecisionAction
    side: TradeSide | None = None
    decision_id: str | None = None
    price_reference: float | None = None
    edge_bps: float | None = None
    why_now: list[str] = Field(default_factory=list)
    why_not_now: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    watch_conditions: list[str] = Field(default_factory=list)
    human_summary: str = ""
    confidence: float = 0.0
    artifact_refs: list[str] = Field(default_factory=list)
    social_bridge_used: bool = False
    social_bridge_probability: float | None = None
    social_bridge_delta_bps: float | None = None
    social_bridge_mode: str | None = None
    created_at: datetime = Field(default_factory=_utc_now, validation_alias=AliasChoices("created_at", "timestamp"))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @model_validator(mode="after")
    def _normalize(self) -> "MarketRecommendationPacket":
        self.probability_estimate = _metadata_float(self, "probability_estimate") or self.probability_estimate
        self.confidence_band = self.confidence_band or _metadata_dict(self, "confidence_band")
        if not self.scenarios:
            self.scenarios = _metadata_list(self, "scenarios")
        self.risks = _source_refs(self.risks, self.why_not_now, _metadata_list(self, "risks"))
        self.recommendation = _first_non_empty(self.recommendation, getattr(self.action, "value", None)) or ""
        self.rationale_summary = _first_non_empty(self.rationale_summary, self.human_summary, self.metadata.get("rationale_summary")) or ""
        self.artifacts = _source_refs(self.artifacts, self.artifact_refs)
        self.mode_used = _first_non_empty(self.mode_used, self.compatibility_mode.value) or ""
        self.engine_used = _first_non_empty(self.engine_used, _metadata_string(self, "engine_used")) or ""
        self.runtime_used = self.runtime_used or _metadata_dict(self, "runtime_used", "execution_runtime", "runtime")
        self.forecast_ts = self.forecast_ts or _utc_datetime(_metadata_value(self, "forecast_ts")) or self.created_at
        self.resolution_policy_ref = _first_non_empty(self.resolution_policy_ref, _metadata_string(self, "resolution_policy_ref"), _metadata_string(self, "resolution_policy_id"))
        self.comparable_market_refs = _source_refs(self.comparable_market_refs) or _source_refs(self.market_context_refs)
        manual_review_flag = bool(_metadata_value(self, "requires_manual_review")) or bool(
            _metadata_value(self, "manual_review_required")
        )
        self.requires_manual_review = bool(self.requires_manual_review or manual_review_flag)
        self.social_bridge_used = bool(self.social_bridge_used or _metadata_value(self, "social_bridge_used"))
        bridge_probability = _metadata_float(self, "social_bridge_probability")
        bridge_delta_bps = _metadata_float(self, "social_bridge_delta_bps")
        if bridge_probability is not None:
            self.social_bridge_probability = bridge_probability
        if bridge_delta_bps is not None:
            self.social_bridge_delta_bps = bridge_delta_bps
        self.social_bridge_mode = _first_non_empty(self.social_bridge_mode, _metadata_string(self, "social_bridge_mode"))
        self._refresh_content_hash()
        return self

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "MarketRecommendationPacket":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class DecisionPacket(BridgePacketBase):
    schema_version: SchemaVersion = "v1"
    decision_id: str = Field(default_factory=lambda: f"dec_{uuid4().hex[:12]}")
    packet_version: str = "1.0.0"
    packet_kind: Literal["decision"] = "decision"
    compatibility_mode: PacketCompatibilityMode = PacketCompatibilityMode.market_only
    market_only_compatible: bool = True
    source_bundle_id: str | None = None
    source_packet_refs: list[str] = Field(default_factory=list)
    social_context_refs: list[str] = Field(default_factory=list)
    market_context_refs: list[str] = Field(default_factory=list)
    run_id: str
    market_id: str
    venue: VenueName
    action: DecisionAction
    confidence: float = 0.0
    probability_estimate: float | None = None
    summary: str = ""
    rationale: str = ""
    forecast_id: str | None = None
    recommendation_id: str | None = None
    why_now: list[str] = Field(default_factory=list)
    why_not_now: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    watch_conditions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    social_bridge_used: bool = False
    social_bridge_probability: float | None = None
    social_bridge_delta_bps: float | None = None
    social_bridge_mode: str | None = None
    created_at: datetime = Field(default_factory=_utc_now, validation_alias=AliasChoices("created_at", "timestamp"))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @model_validator(mode="after")
    def _normalize(self) -> "DecisionPacket":
        self.probability_estimate = self.probability_estimate if self.probability_estimate is not None else _metadata_float(self, "probability_estimate")
        if self.probability_estimate is None:
            band = self.confidence_band or _metadata_dict(self, "confidence_band")
            if band:
                for key in ("center", "mid", "probability", "fair_probability"):
                    if key in band and band[key] is not None:
                        try:
                            self.probability_estimate = float(band[key])
                            break
                        except (TypeError, ValueError):
                            continue
        self.confidence_band = self.confidence_band or _metadata_dict(self, "confidence_band")
        if not self.scenarios:
            self.scenarios = _metadata_list(self, "scenarios")
        self.risks = _source_refs(self.risks, self.why_not_now, _metadata_list(self, "risks"))
        self.recommendation = _first_non_empty(self.recommendation, getattr(self.action, "value", None), _metadata_string(self, "recommendation")) or ""
        self.rationale_summary = _first_non_empty(self.rationale_summary, self.summary, self.rationale, _metadata_string(self, "rationale_summary")) or ""
        self.artifacts = _source_refs(self.artifacts, self.evidence_refs)
        self.mode_used = _first_non_empty(self.mode_used, self.compatibility_mode.value) or ""
        self.engine_used = _first_non_empty(self.engine_used, _metadata_string(self, "engine_used")) or ""
        self.runtime_used = self.runtime_used or _metadata_dict(self, "runtime_used", "execution_runtime", "runtime")
        self.forecast_ts = self.forecast_ts or _utc_datetime(_metadata_value(self, "forecast_ts")) or self.created_at
        self.resolution_policy_ref = _first_non_empty(self.resolution_policy_ref, _metadata_string(self, "resolution_policy_ref"), _metadata_string(self, "resolution_policy_id"))
        self.comparable_market_refs = _source_refs(self.comparable_market_refs) or _source_refs(self.market_context_refs)
        self.requires_manual_review = bool(
            self.requires_manual_review
            or bool(_metadata_value(self, "requires_manual_review"))
            or bool(_metadata_value(self, "manual_review_required"))
        )
        self.social_bridge_used = bool(self.social_bridge_used or _metadata_value(self, "social_bridge_used"))
        bridge_probability = _metadata_float(self, "social_bridge_probability")
        bridge_delta_bps = _metadata_float(self, "social_bridge_delta_bps")
        if bridge_probability is not None:
            self.social_bridge_probability = bridge_probability
        if bridge_delta_bps is not None:
            self.social_bridge_delta_bps = bridge_delta_bps
        self.social_bridge_mode = _first_non_empty(self.social_bridge_mode, _metadata_string(self, "social_bridge_mode"))
        self._refresh_content_hash()
        return self

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "DecisionPacket":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


AdvisorStageStatus = Literal["ready", "degraded", "blocked", "skipped"]


class AdvisorArchitectureStage(BaseModel):
    schema_version: SchemaVersion = "v1"
    stage_id: str
    stage_kind: str
    role: str
    status: AdvisorStageStatus = "ready"
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    contract_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stage_id", "stage_kind", "role", "summary", mode="before")
    @classmethod
    def _normalize_text_fields(cls, value: Any) -> str:
        return _normalized_text(value) if value is not None else ""

    @field_validator("input_refs", "output_refs", "contract_ids", mode="before")
    @classmethod
    def _normalize_ref_lists(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            candidates = [value]
        else:
            candidates = list(value)
        normalized: list[str] = []
        for item in candidates:
            if item is None:
                continue
            text = str(item).strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_stage_metadata(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        return dict(value)


class AdvisorArchitectureSurface(BaseModel):
    schema_version: SchemaVersion = "v1"
    architecture_id: str = ""
    mode: Literal["advisor"] = "advisor"
    architecture_kind: Literal["reference_agentic"] = "reference_agentic"
    runtime: str = "swarm"
    backend_mode: str = "auto"
    run_id: str
    venue: VenueName
    market_id: str
    social_bridge_state: str = "unavailable"
    research_bridge_state: str = "unavailable"
    packet_contracts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    packet_refs: dict[str, Any] = Field(default_factory=dict)
    stage_order: list[str] = Field(default_factory=list)
    stages: list[AdvisorArchitectureStage] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("architecture_id", "runtime", "backend_mode", "social_bridge_state", "research_bridge_state", "summary", mode="before")
    @classmethod
    def _normalize_surface_text_fields(cls, value: Any) -> str:
        return _normalized_text(value) if value is not None else ""

    @field_validator("packet_contracts", mode="before")
    @classmethod
    def _normalize_packet_contracts(cls, value: Any) -> dict[str, dict[str, Any]]:
        if value is None:
            return {}
        contracts = dict(value)
        normalized: dict[str, dict[str, Any]] = {}
        for key, contract in contracts.items():
            name = _normalized_text(key)
            if not name:
                continue
            if contract is None:
                normalized[name] = {}
            elif hasattr(contract, "model_dump"):
                normalized[name] = contract.model_dump(mode="json")
            else:
                normalized[name] = dict(contract)
        return normalized

    @field_validator("packet_refs", mode="before")
    @classmethod
    def _normalize_packet_refs(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        return dict(value)

    @field_validator("stage_order", mode="before")
    @classmethod
    def _normalize_stage_order(cls, value: Any) -> list[str]:
        return _source_refs(value)

    @field_validator("metadata", mode="before")
    @classmethod
    def _normalize_surface_metadata(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        return dict(value)

    @model_validator(mode="after")
    def _normalize_architecture(self) -> "AdvisorArchitectureSurface":
        if not self.architecture_id:
            self.architecture_id = f"{self.run_id}:advisor_architecture"
        if not self.stage_order:
            self.stage_order = [stage.stage_kind for stage in self.stages if stage.stage_kind]
        else:
            self.stage_order = _source_refs(self.stage_order)
        if not self.summary:
            self.summary = (
                f"Reference advisor architecture with {len(self.stages)} stages, "
                f"social_bridge={self.social_bridge_state}, research_bridge={self.research_bridge_state}."
            )
        return self

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "AdvisorArchitectureSurface":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class ForecastComparisonSurface(BaseModel):
    schema_version: SchemaVersion = "v1"
    comparison_id: str = Field(default_factory=lambda: f"fcmp_{uuid4().hex[:12]}")
    run_id: str
    market_id: str
    venue: VenueName
    social_core_used: bool = False
    base_forecast_id: str | None = None
    social_forecast_id: str | None = None
    base_probability_estimate: float = 0.0
    social_probability_estimate: float = 0.0
    base_edge_after_fees_bps: float = 0.0
    social_edge_after_fees_bps: float = 0.0
    probability_delta: float = 0.0
    edge_after_fees_delta_bps: float = 0.0
    base_recommendation_action: DecisionAction = DecisionAction.wait
    social_recommendation_action: DecisionAction = DecisionAction.wait
    base_requires_manual_review: bool = False
    social_requires_manual_review: bool = False
    social_bridge_probability: float | None = None
    social_bridge_delta_bps: float | None = None
    social_bridge_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _normalize(self) -> "ForecastComparisonSurface":
        self.base_probability_estimate = max(0.0, min(1.0, float(self.base_probability_estimate)))
        self.social_probability_estimate = max(0.0, min(1.0, float(self.social_probability_estimate)))
        self.probability_delta = round(float(self.social_probability_estimate) - float(self.base_probability_estimate), 6)
        self.edge_after_fees_delta_bps = round(float(self.social_edge_after_fees_bps) - float(self.base_edge_after_fees_bps), 6)
        self.social_bridge_refs = _source_refs(self.social_bridge_refs)
        metadata_probability = _metadata_float(self, "social_bridge_probability")
        metadata_delta_bps = _metadata_float(self, "social_bridge_delta_bps")
        if metadata_probability is not None:
            self.social_bridge_probability = metadata_probability
        if metadata_delta_bps is not None:
            self.social_bridge_delta_bps = metadata_delta_bps
        return self


class CrossVenueMatch(BaseModel):
    schema_version: SchemaVersion = "v1"
    match_id: str = Field(default_factory=lambda: f"match_{uuid4().hex[:12]}")
    canonical_event_id: str
    left_market_id: str
    right_market_id: str
    left_venue: VenueName
    right_venue: VenueName
    question_left: str = ""
    question_right: str = ""
    question_key: str = ""
    left_resolution_source: str | None = None
    right_resolution_source: str | None = None
    left_currency: str | None = None
    right_currency: str | None = None
    left_payout_currency: str | None = None
    right_payout_currency: str | None = None
    resolution_compatibility_score: float = 0.0
    payout_compatibility_score: float = 0.0
    currency_compatibility_score: float = 0.0
    similarity: float = 0.0
    compatible_resolution: bool = False
    manual_review_required: bool = True
    comparable_group_id: str | None = None
    comparable_market_refs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    rationale: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("similarity")
    @classmethod
    def _clamp_similarity(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @field_validator(
        "resolution_compatibility_score",
        "payout_compatibility_score",
        "currency_compatibility_score",
    )
    @classmethod
    def _clamp_score(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @model_validator(mode="after")
    def _normalize_match(self) -> "CrossVenueMatch":
        self.question_left = _normalized_text(self.question_left)
        self.question_right = _normalized_text(self.question_right)
        self.question_key = _normalized_text(self.question_key)
        self.comparable_market_refs = _source_refs(self.comparable_market_refs)
        self.notes = _source_refs(self.notes)
        self.left_resolution_source = _first_non_empty(self.left_resolution_source)
        self.right_resolution_source = _first_non_empty(self.right_resolution_source)
        self.left_currency = _first_non_empty(self.left_currency)
        self.right_currency = _first_non_empty(self.right_currency)
        self.left_payout_currency = _first_non_empty(self.left_payout_currency)
        self.right_payout_currency = _first_non_empty(self.right_payout_currency)
        if self.resolution_compatibility_score == 0.0 and self.compatible_resolution:
            self.resolution_compatibility_score = 1.0
        return self


class VenueCapabilitiesModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: SchemaVersion = "v1"
    venue: VenueName
    venue_type: VenueType | None = None
    supports_discovery: bool = Field(default=False, validation_alias=AliasChoices("supports_discovery", "discovery"))
    supports_metadata: bool = Field(default=False, validation_alias=AliasChoices("supports_metadata", "metadata"))
    supports_orderbook: bool = Field(default=False, validation_alias=AliasChoices("supports_orderbook", "orderbook"))
    supports_trades: bool = Field(default=False, validation_alias=AliasChoices("supports_trades", "trades"))
    supports_positions: bool = Field(default=False, validation_alias=AliasChoices("supports_positions", "positions"))
    supports_execution: bool = Field(default=False, validation_alias=AliasChoices("supports_execution", "execution"))
    supports_streaming: bool = Field(default=False, validation_alias=AliasChoices("supports_streaming", "streaming"))
    supports_websocket: bool = False
    supports_paper_mode: bool = False
    supports_interviews: bool = Field(default=False, validation_alias=AliasChoices("supports_interviews", "interviews"))
    supports_replay: bool = True
    supports_events: bool = False
    supports_market_feed: bool = False
    supports_user_feed: bool = False
    supports_rtds: bool = False
    read_only: bool = True
    rate_limit_notes: list[str] = Field(default_factory=list)
    automation_constraints: list[str] = Field(default_factory=list)
    metadata_map: dict[str, Any] = Field(default_factory=dict)

    @property
    def discovery(self) -> bool:
        return self.supports_discovery

    @property
    def metadata(self) -> bool:
        return self.supports_metadata

    @property
    def orderbook(self) -> bool:
        return self.supports_orderbook

    @property
    def trades(self) -> bool:
        return self.supports_trades

    @property
    def positions(self) -> bool:
        return self.supports_positions

    @property
    def execution(self) -> bool:
        return self.supports_execution

    @property
    def streaming(self) -> bool:
        return self.supports_streaming

    @property
    def interviews(self) -> bool:
        return self.supports_interviews

    @field_validator("metadata_map", mode="before")
    @classmethod
    def _normalize_metadata_map(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        return dict(value)

    @field_validator("rate_limit_notes", "automation_constraints", mode="before")
    @classmethod
    def _normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return _source_refs([value])
        return _source_refs(value)

    @model_validator(mode="after")
    def _normalize_capabilities(self) -> "VenueCapabilitiesModel":
        metadata = dict(self.metadata_map or {})
        if self.venue_type is None:
            raw_venue_type = metadata.get("venue_type") or metadata.get("default_venue_type")
            if raw_venue_type:
                try:
                    self.venue_type = VenueType(str(raw_venue_type).strip().lower())
                except ValueError:
                    self.venue_type = None

        self.read_only = bool(metadata.get("read_only", self.read_only))
        self.supports_events = bool(metadata.get("supports_events", self.supports_events))
        self.supports_market_feed = bool(
            metadata.get(
                "supports_market_feed",
                self.supports_market_feed or self.supports_orderbook or self.supports_trades,
            )
        )
        self.supports_user_feed = bool(metadata.get("supports_user_feed", self.supports_user_feed))
        self.supports_rtds = bool(metadata.get("supports_rtds", self.supports_rtds))
        self.supports_websocket = bool(
            metadata.get(
                "supports_websocket",
                self.supports_websocket or self.supports_user_feed or self.supports_market_feed or self.supports_rtds,
            )
        )
        self.supports_paper_mode = bool(
            metadata.get(
                "supports_paper_mode",
                metadata.get("paper_capable", self.supports_paper_mode),
            )
        )
        self.supports_streaming = bool(
            self.supports_streaming
            or self.supports_websocket
            or self.supports_market_feed
            or self.supports_user_feed
            or self.supports_rtds
        )
        if not self.rate_limit_notes:
            self.rate_limit_notes = _source_refs(metadata.get("rate_limit_notes"))
        if not self.automation_constraints:
            self.automation_constraints = _source_refs(metadata.get("automation_constraints"))

        metadata.setdefault("venue_type", self.venue_type.value if self.venue_type else None)
        metadata.setdefault("supports_discovery", self.supports_discovery)
        metadata.setdefault("supports_metadata", self.supports_metadata)
        metadata.setdefault("supports_orderbook", self.supports_orderbook)
        metadata.setdefault("supports_trades", self.supports_trades)
        metadata.setdefault("supports_positions", self.supports_positions)
        metadata.setdefault("supports_execution", self.supports_execution)
        metadata.setdefault("supports_streaming", self.supports_streaming)
        metadata.setdefault("supports_websocket", self.supports_websocket)
        metadata.setdefault("supports_paper_mode", self.supports_paper_mode)
        metadata.setdefault("supports_interviews", self.supports_interviews)
        metadata.setdefault("supports_replay", self.supports_replay)
        metadata.setdefault("supports_events", self.supports_events)
        metadata.setdefault("supports_market_feed", self.supports_market_feed)
        metadata.setdefault("supports_user_feed", self.supports_user_feed)
        metadata.setdefault("supports_rtds", self.supports_rtds)
        metadata.setdefault("rate_limit_notes", list(self.rate_limit_notes))
        metadata.setdefault("automation_constraints", list(self.automation_constraints))
        metadata.setdefault("read_only", self.read_only)
        # Keep legacy keys alive for existing adapters and helper lookups.
        metadata.setdefault("discovery", self.supports_discovery)
        metadata.setdefault("metadata", self.supports_metadata)
        metadata.setdefault("orderbook", self.supports_orderbook)
        metadata.setdefault("trades", self.supports_trades)
        metadata.setdefault("positions", self.supports_positions)
        metadata.setdefault("execution", self.supports_execution)
        metadata.setdefault("streaming", self.supports_streaming)
        metadata.setdefault("interviews", self.supports_interviews)
        self.metadata_map = metadata
        return self


class VenueHealthReport(BaseModel):
    schema_version: SchemaVersion = "v1"
    venue: VenueName
    backend_mode: str = "surrogate"
    healthy: bool = True
    message: str = "healthy"
    checked_at: datetime = Field(default_factory=_utc_now)
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("backend_mode", mode="before")
    @classmethod
    def _normalize_backend_mode(cls, value: Any) -> str:
        text = _normalized_text(value)
        return text.lower() if text else "surrogate"

    @field_validator("message", mode="before")
    @classmethod
    def _normalize_message(cls, value: Any) -> str:
        text = _normalized_text(value)
        return text or "healthy"

    @field_validator("details", mode="before")
    @classmethod
    def _normalize_details(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        return dict(value)

    @field_validator("checked_at", mode="after")
    @classmethod
    def _normalize_checked_at(cls, value: datetime) -> datetime:
        normalized = _utc_datetime(value)
        return normalized or _utc_now()


class MarketUniverseConfig(BaseModel):
    schema_version: SchemaVersion = "v1"
    venue: VenueName = VenueName.polymarket
    active_only: bool = True
    min_liquidity: float = 0.0
    min_clarity_score: float = 0.0
    limit: int = 25
    statuses: list[MarketStatus] = Field(default_factory=lambda: [MarketStatus.open])
    query: str | None = None
    include_watchlist: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketUniverseResult(BaseModel):
    schema_version: SchemaVersion = "v1"
    run_id: str = Field(default_factory=lambda: f"universe_{uuid4().hex[:12]}")
    venue: VenueName
    config: MarketUniverseConfig
    markets: list[MarketDescriptor] = Field(default_factory=list)
    filtered_out: list[MarketDescriptor] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LedgerPosition(BaseModel):
    schema_version: SchemaVersion = "v1"
    market_id: str
    venue: VenueName
    side: TradeSide
    quantity: float
    entry_price: float
    mark_price: float | None = None
    unrealized_pnl: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapitalLedgerSnapshot(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: SchemaVersion = "v1"
    snapshot_id: str = Field(default_factory=lambda: f"ledger_{uuid4().hex[:12]}")
    venue: VenueName = VenueName.polymarket
    cash: float = 0.0
    reserved_cash: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    equity: float = 0.0
    currency: str = "USD"
    collateral_currency: str | None = None
    positions: list[LedgerPosition] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=_utc_now)
    captured_at: datetime | None = None
    cash_available: float | None = Field(default=None, validation_alias=AliasChoices("cash_available", "cash_available_usd"))
    cash_locked: float | None = Field(default=None, validation_alias=AliasChoices("cash_locked", "cash_locked_usd"))
    withdrawable_amount: float | None = Field(
        default=None,
        validation_alias=AliasChoices("withdrawable_amount", "withdrawable_amount_usd"),
    )
    open_exposure_usd: float | None = None
    transfer_latency_estimate_ms: float | None = None
    capital_by_market_usd: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def cash_available_usd(self) -> float:
        return float(self.cash_available or 0.0)

    @property
    def cash_locked_usd(self) -> float:
        return float(self.cash_locked or 0.0)

    @property
    def withdrawable_amount_usd(self) -> float:
        return float(self.withdrawable_amount or 0.0)

    @model_validator(mode="before")
    @classmethod
    def _coerce_canonical_inputs(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        captured_at = data.get("captured_at")
        if captured_at is not None and data.get("updated_at") is None:
            data["updated_at"] = captured_at
        cash_locked = _safe_non_negative_float(
            data.get("cash_locked", data.get("cash_locked_usd", data.get("reserved_cash")))
        )
        cash_available = _safe_non_negative_float(data.get("cash_available", data.get("cash_available_usd")))
        if data.get("reserved_cash") is None and cash_locked is not None:
            data["reserved_cash"] = cash_locked
        if data.get("cash") is None and cash_available is not None:
            data["cash"] = round(cash_available + (cash_locked or 0.0), 6)
        return data

    @field_validator(
        "cash",
        "reserved_cash",
        "cash_available",
        "cash_locked",
        "withdrawable_amount",
        "open_exposure_usd",
        "transfer_latency_estimate_ms",
        mode="before",
    )
    @classmethod
    def _normalize_numeric_surface(cls, value: Any) -> float | None:
        if value is None:
            return None
        return max(0.0, float(value))

    @field_validator("realized_pnl", "unrealized_pnl", "equity", mode="before")
    @classmethod
    def _normalize_signed_numeric_surface(cls, value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    @field_validator("currency", "collateral_currency", mode="before")
    @classmethod
    def _normalize_currency(cls, value: Any) -> str | None:
        return _normalize_currency_code(value)

    @field_validator("capital_by_market_usd", mode="before")
    @classmethod
    def _normalize_capital_by_market(cls, value: Any) -> dict[str, float]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, float] = {}
        for key, raw in value.items():
            market_id = _normalized_text(key)
            if not market_id:
                continue
            amount = _safe_non_negative_float(raw)
            if amount is None:
                continue
            normalized[market_id] = round(amount, 6)
        return normalized

    @field_validator("updated_at", "captured_at", mode="after")
    @classmethod
    def _normalize_snapshot_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _utc_datetime(value) or _utc_now()

    @model_validator(mode="after")
    def _derive_equity(self) -> "CapitalLedgerSnapshot":
        return self.refresh_surface()

    def refresh_surface(self) -> "CapitalLedgerSnapshot":
        self.currency = _normalize_currency_code(self.currency) or "USD"
        self.collateral_currency = _normalize_currency_code(self.collateral_currency) or self.currency
        self.updated_at = _utc_datetime(self.updated_at) or _utc_now()
        self.captured_at = _utc_datetime(self.captured_at) or self.updated_at
        self.cash = round(max(0.0, float(self.cash or 0.0)), 6)
        self.reserved_cash = round(max(0.0, float(self.reserved_cash or 0.0)), 6)
        self.realized_pnl = round(float(self.realized_pnl or 0.0), 6)
        self.unrealized_pnl = round(float(self.unrealized_pnl or 0.0), 6)
        if self.equity == 0.0:
            self.equity = round(self.cash - self.reserved_cash + self.realized_pnl + self.unrealized_pnl, 6)
        else:
            self.equity = round(float(self.equity), 6)

        derived_cash_available = round(max(0.0, self.cash - self.reserved_cash), 6)
        derived_cash_locked = round(max(0.0, self.reserved_cash), 6)
        derived_withdrawable_amount = derived_cash_available
        derived_capital_by_market = self.capital_by_market_usd or _capital_by_market_surface(self.positions)
        derived_open_exposure = round(sum(_position_notional_surface(position) for position in self.positions), 6)
        derived_transfer_latency = (
            round(float(self.transfer_latency_estimate_ms), 2)
            if self.transfer_latency_estimate_ms is not None
            else _transfer_latency_surface(self.venue, self.positions, self.metadata or {})
        )

        self.cash_available = round(
            derived_cash_available if self.cash_available is None else max(0.0, float(self.cash_available)),
            6,
        )
        self.cash_locked = round(
            derived_cash_locked if self.cash_locked is None else max(0.0, float(self.cash_locked)),
            6,
        )
        self.withdrawable_amount = round(
            derived_withdrawable_amount if self.withdrawable_amount is None else max(0.0, float(self.withdrawable_amount)),
            6,
        )
        self.capital_by_market_usd = {
            market_id: round(max(0.0, float(amount)), 6)
            for market_id, amount in derived_capital_by_market.items()
        }
        self.open_exposure_usd = round(
            derived_open_exposure if self.open_exposure_usd is None else max(0.0, float(self.open_exposure_usd)),
            6,
        )
        self.transfer_latency_estimate_ms = round(max(0.0, float(derived_transfer_latency)), 2)

        self.metadata["captured_at"] = self.captured_at.isoformat()
        self.metadata["cash_available"] = self.cash_available
        self.metadata["cash_locked"] = self.cash_locked
        self.metadata["cash_available_usd"] = self.cash_available
        self.metadata["cash_locked_usd"] = self.cash_locked
        self.metadata["withdrawable_amount"] = self.withdrawable_amount
        self.metadata["withdrawable_amount_usd"] = self.withdrawable_amount
        self.metadata["collateral_currency"] = self.collateral_currency
        self.metadata["open_exposure_usd"] = self.open_exposure_usd
        self.metadata["transfer_latency_estimate_ms"] = self.transfer_latency_estimate_ms
        self.metadata["capital_by_market_usd"] = dict(self.capital_by_market_usd)
        return self


class TradeIntent(BaseModel):
    schema_version: SchemaVersion = "v1"
    intent_id: str = Field(default_factory=lambda: f"intent_{uuid4().hex[:12]}")
    run_id: str
    venue: VenueName
    market_id: str
    side: TradeSide | None = None
    size_usd: float = 0.0
    limit_price: float | None = None
    max_slippage_bps: float = 150.0
    max_unhedged_leg_ms: int = 0
    time_in_force: str = "ioc"
    forecast_ref: str | None = None
    recommendation_ref: str | None = None
    risk_checks_passed: bool = False
    manual_review_required: bool = False
    no_trade_reasons: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("size_usd", "max_slippage_bps", mode="before")
    @classmethod
    def _non_negative_float(cls, value: Any) -> float:
        if value is None:
            return 0.0
        return max(0.0, float(value))

    @field_validator("max_unhedged_leg_ms", mode="before")
    @classmethod
    def _non_negative_int(cls, value: Any) -> int:
        if value is None:
            return 0
        return max(0, int(value))

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "TradeIntent":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_execution_readiness(
        cls,
        readiness: "ExecutionReadiness",
        *,
        intent_id: str | None = None,
        max_unhedged_leg_ms: int = 0,
        time_in_force: str = "ioc",
        metadata: dict[str, Any] | None = None,
    ) -> "TradeIntent":
        return readiness.materialize_trade_intent(
            intent_id=intent_id,
            max_unhedged_leg_ms=max_unhedged_leg_ms,
            time_in_force=time_in_force,
            metadata=metadata,
        )


class ExecutionReadiness(BridgePacketBase):
    schema_version: SchemaVersion = "v1"
    readiness_id: str = Field(default_factory=lambda: f"ready_{uuid4().hex[:12]}")
    packet_version: str = "1.0.0"
    packet_kind: Literal["execution_readiness"] = "execution_readiness"
    compatibility_mode: PacketCompatibilityMode = PacketCompatibilityMode.market_only
    market_only_compatible: bool = True
    source_bundle_id: str | None = None
    source_packet_refs: list[str] = Field(default_factory=list)
    social_context_refs: list[str] = Field(default_factory=list)
    market_context_refs: list[str] = Field(default_factory=list)
    run_id: str
    market_id: str
    venue: VenueName
    decision_id: str | None = None
    forecast_id: str | None = None
    recommendation_id: str | None = None
    trade_intent_id: str | None = None
    decision_action: DecisionAction = DecisionAction.wait
    side: TradeSide | None = None
    size_usd: float = 0.0
    limit_price: float | None = None
    max_slippage_bps: float = 150.0
    confidence: float = 0.0
    edge_after_fees_bps: float = 0.0
    risk_checks_passed: bool = False
    manual_review_required: bool = False
    ready_to_execute: bool = False
    ready_to_paper: bool = False
    ready_to_live: bool = False
    can_materialize_trade_intent: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    no_trade_reasons: list[str] = Field(default_factory=list)
    route: str = "blocked"
    execution_notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now, validation_alias=AliasChoices("created_at", "timestamp"))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence", "edge_after_fees_bps", "max_slippage_bps", "size_usd", mode="before")
    @classmethod
    def _non_negative_float(cls, value: Any) -> float:
        if value is None:
            return 0.0
        return max(0.0, float(value))

    @model_validator(mode="after")
    def _normalize_readiness(self) -> "ExecutionReadiness":
        if self.decision_action != DecisionAction.bet:
            self.side = None
        self.blocked_reasons = _source_refs(self.blocked_reasons, self.no_trade_reasons)
        if self.manual_review_required:
            self.blocked_reasons = _source_refs(self.blocked_reasons, ["manual_review_required"])
        if not self.risk_checks_passed:
            self.blocked_reasons = _source_refs(self.blocked_reasons, ["risk_checks_failed"])
        if self.decision_action in {DecisionAction.no_trade, DecisionAction.wait}:
            self.blocked_reasons = _source_refs(self.blocked_reasons, [f"decision_action={self.decision_action.value}"])
        if self.decision_action == DecisionAction.manual_review:
            self.blocked_reasons = _source_refs(self.blocked_reasons, ["manual_review"])
        self.can_materialize_trade_intent = (
            self.decision_action == DecisionAction.bet
            and self.side is not None
            and self.limit_price is not None
            and self.size_usd > 0.0
            and self.risk_checks_passed
            and not self.manual_review_required
            and not self.blocked_reasons
        )
        self.ready_to_execute = self.can_materialize_trade_intent
        self.ready_to_paper = self.can_materialize_trade_intent
        self.ready_to_live = self.can_materialize_trade_intent and bool(self.metadata.get("live_gate_passed"))
        if self.route != "blocked" and not self.can_materialize_trade_intent:
            self.route = "blocked"
        if self.route == "blocked" and self.can_materialize_trade_intent:
            self.route = "paper" if not self.ready_to_live else "live_candidate"
        if self.route not in {"blocked", "paper", "live_candidate"}:
            self.route = "paper" if self.can_materialize_trade_intent else "blocked"
        self._refresh_content_hash()
        return self

    def materialize_trade_intent(
        self,
        *,
        intent_id: str | None = None,
        max_unhedged_leg_ms: int = 0,
        time_in_force: str = "ioc",
        metadata: dict[str, Any] | None = None,
    ) -> "TradeIntent":
        if not self.can_materialize_trade_intent:
            raise ValueError(
                "execution readiness is not materializable into a trade intent: "
                + ", ".join(self.blocked_reasons or ["insufficient readiness"])
            )
        merged_metadata = {
            **dict(self.metadata),
            **(metadata or {}),
            "execution_readiness_id": self.readiness_id,
            "execution_route": self.route,
        }
        return TradeIntent(
            intent_id=intent_id or f"intent_{uuid4().hex[:12]}",
            run_id=self.run_id,
            venue=self.venue,
            market_id=self.market_id,
            side=self.side,
            size_usd=self.size_usd,
            limit_price=self.limit_price,
            max_slippage_bps=self.max_slippage_bps,
            max_unhedged_leg_ms=max_unhedged_leg_ms,
            time_in_force=time_in_force,
            forecast_ref=self.forecast_id,
            recommendation_ref=self.recommendation_id,
            risk_checks_passed=self.risk_checks_passed,
            manual_review_required=self.manual_review_required,
            no_trade_reasons=list(self.no_trade_reasons),
            metadata=merged_metadata,
        )

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ExecutionReadiness":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class ExecutionComplianceSnapshot(BaseModel):
    schema_version: SchemaVersion = "v1"
    compliance_id: str = Field(default_factory=lambda: f"ecmp_{uuid4().hex[:12]}")
    packet_version: str = "1.0.0"
    packet_kind: Literal["execution_compliance"] = "execution_compliance"
    run_id: str
    market_id: str
    venue: VenueName
    requested_mode: ExecutionProjectionMode = ExecutionProjectionMode.paper
    highest_authorized_mode: ExecutionProjectionOutcome = ExecutionProjectionOutcome.paper
    status: ExecutionComplianceStatus = ExecutionComplianceStatus.degraded
    allowed: bool = True
    manual_review_required: bool = False
    jurisdiction_allowed: bool = True
    account_type_allowed: bool = True
    automation_allowed: bool = True
    rate_limit_ok: bool = True
    tos_accepted: bool = False
    summary: str = ""
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize_compliance(self) -> "ExecutionComplianceSnapshot":
        if self.status == ExecutionComplianceStatus.blocked:
            self.allowed = False
        elif not self.allowed and self.status != ExecutionComplianceStatus.blocked:
            self.status = ExecutionComplianceStatus.degraded
        if self.manual_review_required and self.status == ExecutionComplianceStatus.authorized:
            self.status = ExecutionComplianceStatus.degraded
        self.reasons = _source_refs(self.reasons)
        self.warnings = _source_refs(self.warnings)
        if not self.summary:
            self.summary = "Compliance snapshot derived from execution guardrails."
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self

    def allows_mode(self, mode: ExecutionProjectionMode) -> bool:
        order = {
            ExecutionProjectionOutcome.blocked: 0,
            ExecutionProjectionOutcome.paper: 1,
            ExecutionProjectionOutcome.shadow: 2,
            ExecutionProjectionOutcome.live: 3,
        }
        highest = order[self.highest_authorized_mode]
        return order[ExecutionProjectionOutcome(mode.value)] <= highest

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ExecutionComplianceSnapshot":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class ExecutionProjectionBasis(BaseModel):
    schema_version: SchemaVersion = "v1"
    readiness_status: Literal["available", "unavailable"] = "unavailable"
    uses_execution_readiness: bool = True
    uses_compliance: bool = True
    uses_capital: bool = False
    uses_reconciliation: bool = False
    uses_venue_health: bool = False
    capital_status: Literal["available", "unavailable"] = "unavailable"
    reconciliation_status: Literal["available", "unavailable"] = "unavailable"
    venue_health_status: Literal["available", "unavailable"] = "unavailable"
    compliance_status: Literal["available", "unavailable"] = "unavailable"


class ExecutionProjectionModeReport(BaseModel):
    schema_version: SchemaVersion = "v1"
    requested_mode: ExecutionProjectionMode
    verdict: ExecutionProjectionVerdict = ExecutionProjectionVerdict.blocked
    effective_mode: ExecutionProjectionOutcome = ExecutionProjectionOutcome.blocked
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""

    @model_validator(mode="after")
    def _normalize_mode_report(self) -> "ExecutionProjectionModeReport":
        self.blockers = _source_refs(self.blockers)
        self.warnings = _source_refs(self.warnings)
        if not self.summary:
            self.summary = f"{self.requested_mode.value} -> {self.effective_mode.value}"
        return self


class ExecutionProjection(BaseModel):
    schema_version: SchemaVersion = "v1"
    projection_id: str = Field(default_factory=lambda: f"proj_{uuid4().hex[:12]}")
    packet_version: str = "1.0.0"
    packet_kind: Literal["execution_projection"] = "execution_projection"
    run_id: str
    venue: VenueName
    market_id: str
    requested_mode: ExecutionProjectionMode
    projected_mode: ExecutionProjectionOutcome = ExecutionProjectionOutcome.blocked
    projection_verdict: ExecutionProjectionVerdict = ExecutionProjectionVerdict.blocked
    highest_safe_mode: ExecutionProjectionMode | None = None
    highest_safe_requested_mode: ExecutionProjectionMode | None = None
    highest_authorized_mode: ExecutionProjectionOutcome = ExecutionProjectionOutcome.blocked
    recommended_effective_mode: ExecutionProjectionOutcome | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    downgrade_reasons: list[str] = Field(default_factory=list)
    manual_review_required: bool = False
    readiness_ref: str | None = None
    compliance_ref: str | None = None
    capital_ref: str | None = None
    reconciliation_ref: str | None = None
    health_ref: str | None = None
    expires_at: datetime
    summary: str = ""
    basis: ExecutionProjectionBasis = Field(default_factory=ExecutionProjectionBasis)
    modes: dict[ExecutionProjectionMode, ExecutionProjectionModeReport] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""

    @model_validator(mode="after")
    def _normalize_projection(self) -> "ExecutionProjection":
        self.blocking_reasons = _source_refs(self.blocking_reasons)
        self.downgrade_reasons = _source_refs(self.downgrade_reasons)
        self.expires_at = _utc_datetime(self.expires_at) or self.expires_at
        if self.highest_safe_requested_mode is None and self.highest_safe_mode is not None:
            self.highest_safe_requested_mode = self.highest_safe_mode
        if self.highest_safe_mode is None and self.highest_safe_requested_mode is not None:
            self.highest_safe_mode = self.highest_safe_requested_mode
        if self.highest_safe_requested_mode is not None and self.highest_safe_mode is not None:
            if self.highest_safe_requested_mode != self.highest_safe_mode:
                raise ValueError("highest_safe_mode must match highest_safe_requested_mode")
        if self.projected_mode != ExecutionProjectionOutcome.blocked:
            if self.highest_safe_mode is not None and _projection_rank(self.projected_mode) > _projection_rank(ExecutionProjectionOutcome(self.highest_safe_mode.value)):
                raise ValueError("projected_mode exceeds highest_safe_mode")
            if _projection_rank(self.projected_mode) > _projection_rank(self.highest_authorized_mode):
                raise ValueError("projected_mode exceeds highest_authorized_mode")
        if self.recommended_effective_mode is None and self.projected_mode != ExecutionProjectionOutcome.blocked:
            self.recommended_effective_mode = self.projected_mode
        if not self.summary:
            self.summary = (
                f"requested {self.requested_mode.value} -> projected {self.projected_mode.value}; "
                f"highest safe requested mode={self.highest_safe_mode.value if self.highest_safe_mode else 'blocked'}"
            )
        if not self.content_hash:
            self.content_hash = _stable_content_hash(self.model_dump(mode="json", exclude={"content_hash"}))
        return self

    def is_expired(self, as_of: datetime | None = None) -> bool:
        check = _utc_datetime(as_of) or _utc_now()
        expires_at = _utc_datetime(self.expires_at) or self.expires_at
        return check >= expires_at

    def is_stale(self, as_of: datetime | None = None, *, stale_after_seconds: float | None = None) -> bool:
        stale_after = stale_after_seconds
        if stale_after is None:
            stale_after = float(self.metadata.get("stale_after_seconds", 0.0) or 0.0)
        if stale_after <= 0.0:
            return False
        anchor_raw = self.metadata.get("anchor_at")
        if not anchor_raw:
            return False
        if isinstance(anchor_raw, datetime):
            anchor = _utc_datetime(anchor_raw)
        else:
            anchor = _utc_datetime(str(anchor_raw))
        if anchor is None:
            return False
        check = _utc_datetime(as_of) or _utc_now()
        return (check - anchor).total_seconds() >= stale_after

    def surface(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def persist(self, path: str | Path) -> Path:
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(self.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        return resolved

    @classmethod
    def load(cls, path: str | Path) -> "ExecutionProjection":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


class RunManifest(BaseModel):
    schema_version: SchemaVersion = "v1"
    run_id: str = Field(default_factory=lambda: f"run_{uuid4().hex[:12]}")
    venue: VenueName
    venue_type: VenueType = VenueType.execution
    market_id: str
    mode: str = "advise"
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    inputs: dict[str, Any] = Field(default_factory=dict)
    snapshot_ref: str | None = None
    resolution_policy_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    forecast_ref: str | None = None
    recommendation_ref: str | None = None
    decision_ref: str | None = None
    execution_readiness_ref: str | None = None
    execution_compliance_ref: str | None = None
    execution_projection_ref: str | None = None
    capital_ref: str | None = None
    reconciliation_ref: str | None = None
    health_ref: str | None = None
    artifact_refs: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = _utc_now()


class ReplayReport(BaseModel):
    schema_version: SchemaVersion = "v1"
    run_id: str
    replay_id: str = Field(default_factory=lambda: f"replay_{uuid4().hex[:12]}")
    same_forecast: bool = False
    same_recommendation: bool = False
    same_decision: bool = False
    same_execution_readiness: bool = False
    differences: list[str] = Field(default_factory=list)
    original: dict[str, Any] = Field(default_factory=dict)
    replay: dict[str, Any] = Field(default_factory=dict)
    original_execution_readiness: ExecutionReadiness | None = None
    replay_execution_readiness: ExecutionReadiness | None = None
    original_execution_projection: ExecutionProjection | None = None
    replay_execution_projection: ExecutionProjection | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaperTradeRecord(BaseModel):
    schema_version: SchemaVersion = "v1"
    trade_id: str = Field(default_factory=lambda: f"paper_{uuid4().hex[:12]}")
    run_id: str
    venue: VenueName = VenueName.polymarket
    market_id: str
    action: DecisionAction
    side: TradeSide | None = None
    size: float = 0.0
    entry_price: float | None = None
    status: str = "proposed"
    created_at: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# Backward-compatible aliases for earlier scaffolds.
MarketRecommendationAction = DecisionAction
MarketRunManifest = RunManifest
VenueCapabilities = VenueCapabilitiesModel
VenueHealthSnapshot = VenueHealthReport
