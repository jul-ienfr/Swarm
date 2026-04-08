from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from statistics import mean
from typing import Any, Iterable
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class ProfileStance(str, Enum):
    support = "support"
    cautious = "cautious"
    challenge = "challenge"
    expansion = "expansion"
    governance = "governance"
    efficiency = "efficiency"


class ProfileRole(str, Enum):
    participant = "participant"
    strategist = "strategist"
    analyst = "analyst"
    guardian = "guardian"
    operator = "operator"
    market = "market"
    social = "social"
    facilitator = "facilitator"


class ProfileGenerationRequest(BaseModel):
    topic: str
    objective: str = ""
    participants: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    entities: list[Any] = Field(default_factory=list)
    interventions: list[str] = Field(default_factory=list)
    target_profiles: int = 0
    max_profiles: int = 32
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("target_profiles", "max_profiles")
    @classmethod
    def _validate_non_negative(cls, value: int) -> int:
        return max(0, int(value))


class PersonaProfile(BaseModel):
    profile_id: str = Field(default_factory=lambda: f"profile_{uuid4().hex[:12]}")
    label: str
    role: ProfileRole = ProfileRole.participant
    stance: ProfileStance = ProfileStance.support
    confidence: float = 0.5
    trust: float = 0.5
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    memory_window: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("confidence", "trust")
    @classmethod
    def _clamp_unit_interval(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value)))


class ProfileGenerationReport(BaseModel):
    request_id: str = Field(default_factory=lambda: f"profile_request_{uuid4().hex[:12]}")
    topic: str
    objective: str = ""
    profiles: list[PersonaProfile] = Field(default_factory=list)
    profile_count: int = 0
    cohort_counts: dict[str, int] = Field(default_factory=dict)
    top_keywords: list[str] = Field(default_factory=list)
    summary: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class ProfileGenerationPipelineConfig:
    max_profiles_hard_cap: int = 1000
    default_profile_floor: int = 3


@dataclass(frozen=True, slots=True)
class _ProfileBlueprint:
    label_seed: str
    role: ProfileRole
    stance: ProfileStance


class ProfileGenerationPipeline:
    """
    Bounded, deterministic profile pipeline.

    Goals:
    - normalize participants/documents/entities into profile-ready personas
    - support both small and large deliberations without external dependencies
    - keep the output stable enough to plug into future multi-agent deliberation
    """

    def __init__(self, *, config: ProfileGenerationPipelineConfig | None = None) -> None:
        self.config = config or ProfileGenerationPipelineConfig()

    def run(self, request: ProfileGenerationRequest) -> ProfileGenerationReport:
        requested_participants = [item.strip() for item in request.participants if item and item.strip()]
        keywords = self._extract_keywords(
            topic=request.topic,
            objective=request.objective,
            documents=request.documents,
            entities=request.entities,
            interventions=request.interventions,
        )
        participants = self._resolve_participants(request, keywords)
        target_count = self._resolve_target_count(request, participants)
        blueprints = self._build_blueprints(request=request, keywords=keywords, target_count=target_count)
        evidence_pool = self._build_evidence_pool(
            [request.topic, request.objective, *request.documents],
            request.entities,
            request.interventions,
            keywords,
        )

        profiles: list[PersonaProfile] = []
        for index in range(target_count):
            blueprint = blueprints[index]
            preserve_requested_label = index < len(requested_participants)
            label = participants[index] if preserve_requested_label and index < len(participants) else self._synthetic_label(
                request,
                keywords,
                index,
                blueprint=blueprint,
            )
            profiles.append(
                self._build_profile(
                    request=request,
                    label=label,
                    index=index,
                    keywords=keywords,
                    evidence_pool=evidence_pool,
                    blueprint=blueprint,
                )
            )

        cohort_counts = Counter(profile.stance.value for profile in profiles)
        role_counts = Counter(profile.role.value for profile in profiles)
        report = ProfileGenerationReport(
            topic=request.topic,
            objective=request.objective,
            profiles=profiles,
            profile_count=len(profiles),
            cohort_counts=dict(cohort_counts),
            top_keywords=keywords[:8],
            summary=self._build_report_summary(request, profiles, keywords),
            metadata={
                "target_profiles": target_count,
                "requested_participants": len(request.participants),
                "derived_participants": participants,
                "documents_count": len(request.documents),
                "entities_count": len(request.entities),
                "interventions_count": len(request.interventions),
                "keyword_count": len(keywords),
                "role_counts": dict(role_counts),
                "stance_counts": dict(cohort_counts),
                "blueprint_seeds": [blueprint.label_seed for blueprint in blueprints[: min(len(blueprints), 12)]],
            },
        )
        return report

    def _resolve_participants(self, request: ProfileGenerationRequest, keywords: list[str]) -> list[str]:
        requested = [item.strip() for item in request.participants if item and item.strip()]
        if requested:
            return list(dict.fromkeys(requested))
        derived = self._derive_participants(request=request, keywords=keywords)
        if derived:
            return derived
        return ["architect", "analyst", "guardian"]

    def _resolve_target_count(self, request: ProfileGenerationRequest, participants: list[str]) -> int:
        requested = request.target_profiles or len(participants) or self.config.default_profile_floor
        ceiling = min(request.max_profiles or requested, self.config.max_profiles_hard_cap)
        return max(1, min(ceiling, max(len(participants), requested)))

    def _build_profile(
        self,
        *,
        request: ProfileGenerationRequest,
        label: str,
        index: int,
        keywords: list[str],
        evidence_pool: list[str],
        blueprint: _ProfileBlueprint,
    ) -> PersonaProfile:
        if _label_matches_blueprint(label, blueprint):
            role = blueprint.role
            stance = blueprint.stance
        else:
            role = self._infer_role(label, keywords, default=blueprint.role)
            stance = self._infer_stance(label, request, keywords, default=blueprint.stance)
        confidence = self._score_confidence(label, index, request, evidence_pool)
        trust = self._score_trust(label, index, request, evidence_pool)
        memory_window = self._build_memory_window(request, label, evidence_pool)
        focus_keywords = self._focus_keywords(label, keywords, limit=5)
        summary = self._build_summary(label, request.topic, stance, role, focus_keywords)
        return PersonaProfile(
            label=label,
            role=role,
            stance=stance,
            confidence=confidence,
            trust=trust,
            summary=summary,
            evidence=evidence_pool[:5],
            memory_window=memory_window,
            keywords=focus_keywords,
            metadata={
                "index": index,
                "topic_hash": _stable_hash(request.topic),
                "source": "profile_generation_pipeline",
                "blueprint_role": blueprint.role.value,
                "blueprint_stance": blueprint.stance.value,
                "blueprint_seed": blueprint.label_seed,
            },
        )

    def _infer_role(self, label: str, keywords: list[str], *, default: ProfileRole = ProfileRole.participant) -> ProfileRole:
        label_tokens = set(_tokenize(label))
        if label_tokens & {"strategy", "strategist", "architect", "planner", "plan", "roadmap", "rollout", "launch", "coordination"}:
            return ProfileRole.strategist
        if label_tokens & {"research", "analysis", "analyst", "signal", "forecast", "evidence", "calibration"}:
            return ProfileRole.analyst
        if label_tokens & {"risk", "safety", "guard", "guardian", "policy", "compliance", "control", "rollback", "governance"}:
            return ProfileRole.guardian
        if label_tokens & {"ops", "operator", "execution", "latency", "infra", "runtime"}:
            return ProfileRole.operator
        if label_tokens & {"market", "pricing", "demand", "revenue", "growth", "adoption"}:
            return ProfileRole.market
        if label_tokens & {"social", "community", "audience", "network", "engagement"}:
            return ProfileRole.social
        if label_tokens & {"facilitator", "moderator", "chair", "facilitation"}:
            return ProfileRole.facilitator
        if default != ProfileRole.participant:
            return default
        tokens = set(label_tokens | set(keywords[:8]))
        if tokens & {"strategy", "strategist", "architect", "planner", "plan", "roadmap", "rollout", "launch", "coordination"}:
            return ProfileRole.strategist
        if tokens & {"research", "analysis", "analyst", "signal", "forecast", "evidence", "calibration"}:
            return ProfileRole.analyst
        if tokens & {"risk", "safety", "guard", "policy", "compliance", "control", "rollback", "governance"}:
            return ProfileRole.guardian
        if tokens & {"ops", "operator", "execution", "latency", "infra", "runtime"}:
            return ProfileRole.operator
        if tokens & {"market", "pricing", "demand", "revenue", "growth", "adoption"}:
            return ProfileRole.market
        if tokens & {"social", "community", "audience", "network", "engagement"}:
            return ProfileRole.social
        if tokens & {"facilitator", "moderator", "chair", "facilitation"}:
            return ProfileRole.facilitator
        return default

    def _infer_stance(
        self,
        label: str,
        request: ProfileGenerationRequest,
        keywords: list[str],
        *,
        default: ProfileStance = ProfileStance.support,
    ) -> ProfileStance:
        label_tokens = set(_tokenize(label))
        if label_tokens & {"challenge", "skeptic", "devil", "critique", "redteam"}:
            return ProfileStance.challenge
        if label_tokens & {"risk", "safety", "guard", "guardian", "compliance", "regulation", "control", "rollback", "governance"}:
            return ProfileStance.governance
        if label_tokens & {"cost", "efficiency", "throughput", "latency", "scale", "ops", "execution"}:
            return ProfileStance.efficiency
        if label_tokens & {"growth", "expand", "adoption", "market", "revenue", "launch", "expansion"}:
            return ProfileStance.expansion
        if label_tokens & {"caution", "stability", "safe", "risk", "reliability"}:
            return ProfileStance.cautious
        if default != ProfileStance.support:
            return default
        tokens = set(label_tokens | set(_tokenize(request.objective)) | set(keywords[:6]))
        if tokens & {"rollback", "guardrails", "stability", "reliability"}:
            return ProfileStance.cautious
        return default

    def _score_confidence(
        self,
        label: str,
        index: int,
        request: ProfileGenerationRequest,
        evidence_pool: list[str],
    ) -> float:
        explicitness = 1.0 if label in request.participants else 0.6
        evidence_density = min(1.0, len(evidence_pool) / 8.0)
        topical_signal = 0.15 if _tokenize(request.topic) else 0.0
        base = 0.35 + (0.1 * explicitness) + (0.3 * evidence_density) + topical_signal - min(0.1, index * 0.01)
        return round(max(0.0, min(1.0, base)), 3)

    def _score_trust(
        self,
        label: str,
        index: int,
        request: ProfileGenerationRequest,
        evidence_pool: list[str],
    ) -> float:
        trust_seed = 0.4 + min(0.4, len(request.documents) * 0.03) + min(0.1, len(request.interventions) * 0.02)
        trust_seed += min(0.1, len(evidence_pool) * 0.01)
        trust_seed -= min(0.1, index * 0.01)
        if any(token in _tokenize(label) for token in ("guard", "risk", "policy")):
            trust_seed += 0.05
        return round(max(0.0, min(1.0, trust_seed)), 3)

    def _build_memory_window(
        self,
        request: ProfileGenerationRequest,
        label: str,
        evidence_pool: list[str],
    ) -> list[str]:
        window: list[str] = []
        window.extend(item for item in request.documents[:2] if item)
        window.extend(item for item in request.interventions[:2] if item)
        if evidence_pool:
            window.extend(evidence_pool[:2])
        if not window:
            window.append(f"{label} has no retained memory yet.")
        return window[:5]

    def _build_evidence_pool(
        self,
        documents: list[str],
        entities: list[Any],
        interventions: list[str],
        keywords: list[str],
    ) -> list[str]:
        pool: list[str] = []
        pool.extend(doc for doc in documents if doc)
        pool.extend(intervention for intervention in interventions if intervention)
        for entity in entities:
            pool.append(json.dumps(entity, sort_keys=True, default=str))
        pool.extend(keywords)
        return _dedupe(pool)

    def _build_summary(
        self,
        label: str,
        topic: str,
        stance: ProfileStance,
        role: ProfileRole,
        keywords: list[str],
    ) -> str:
        keyword_text = ", ".join(keywords[:4]) if keywords else "no strong keywords"
        return (
            f"{label} is a {role.value} persona for '{topic}' with a {stance.value} stance. "
            f"Primary focus: {keyword_text}."
        )

    def _build_report_summary(
        self,
        request: ProfileGenerationRequest,
        profiles: list[PersonaProfile],
        keywords: list[str],
    ) -> str:
        if not profiles:
            return f"No profiles generated for '{request.topic}'."
        stance_counts = Counter(profile.stance.value for profile in profiles)
        dominant_stance, dominant_count = stance_counts.most_common(1)[0]
        keyword_text = ", ".join(keywords[:4]) if keywords else "no strong keywords"
        return (
            f"Generated {len(profiles)} profile(s) for '{request.topic}'. "
            f"Dominant stance: {dominant_stance} ({dominant_count}). "
            f"Key signals: {keyword_text}."
        )

    def _synthetic_label(
        self,
        request: ProfileGenerationRequest,
        keywords: list[str],
        index: int,
        *,
        blueprint: _ProfileBlueprint | None = None,
    ) -> str:
        seeds = self._semantic_label_seeds(request=request, keywords=keywords)
        stem = blueprint.label_seed if blueprint is not None else (seeds[index % len(seeds)] if seeds else "strategy")
        suffix = f"{index + 1:03d}"
        label_parts: list[str] = [stem]
        if blueprint is not None and blueprint.stance.value not in label_parts:
            label_parts.append(blueprint.stance.value)
        return "_".join([*label_parts, suffix])

    def _extract_keywords(
        self,
        *,
        topic: str,
        objective: str,
        documents: list[str],
        entities: list[Any],
        interventions: list[str],
    ) -> list[str]:
        tokens: list[str] = []
        for text in [topic, objective, *documents, *interventions]:
            tokens.extend(_tokenize(text))
        for entity in entities:
            tokens.extend(_tokenize(json.dumps(entity, sort_keys=True, default=str)))
        filtered = [
            token
            for token in tokens
            if len(token) > 2 and token not in _STOPWORDS and token not in _LABEL_BLACKLIST
        ]
        return [item for item, _count in Counter(filtered).most_common(24)]

    def _derive_participants(self, *, request: ProfileGenerationRequest, keywords: list[str]) -> list[str]:
        target = max(self.config.default_profile_floor, min(6, len(self._semantic_label_seeds(request=request, keywords=keywords)) or 6))
        blueprints = self._build_blueprints(request=request, keywords=keywords, target_count=target)
        participants: list[str] = []
        for blueprint in blueprints:
            seed = blueprint.label_seed
            label = seed if blueprint.stance == ProfileStance.support else f"{seed}_{blueprint.stance.value}"
            if label and not _is_generic_label(label):
                participants.append(label)
        if participants:
            return participants[: min(8, max(len(participants), self.config.default_profile_floor))]
        return []

    def _focus_keywords(self, label: str, keywords: list[str], limit: int = 5) -> list[str]:
        label_tokens = set(_tokenize(label))
        focused = [keyword for keyword in keywords if keyword in label_tokens or keyword in _tokenize(label)]
        if not focused:
            focused = keywords[:limit]
        return focused[:limit]

    def _semantic_label_seeds(self, *, request: ProfileGenerationRequest, keywords: list[str]) -> list[str]:
        tokens = set(_tokenize(request.topic) + _tokenize(request.objective) + keywords)
        seeds: list[str] = []
        for seed, _role, _stance, aliases in _PROFILE_ARCHETYPES:
            if tokens & aliases:
                seeds.append(seed)
        for keyword in keywords:
            if not _is_generic_label(keyword) and keyword not in seeds:
                seeds.append(keyword)
        if not seeds:
            seeds = ["strategy", "analysis", "risk"]
        return _dedupe(seeds)

    def _build_blueprints(
        self,
        *,
        request: ProfileGenerationRequest,
        keywords: list[str],
        target_count: int,
    ) -> list[_ProfileBlueprint]:
        selected_seeds = self._semantic_label_seeds(request=request, keywords=keywords)
        selected_blueprints: list[_ProfileBlueprint] = []
        for seed in selected_seeds:
            blueprint = _ARCHETYPE_BY_SEED.get(seed)
            if blueprint is not None:
                selected_blueprints.append(blueprint)
        ordered = _dedupe_blueprints([*selected_blueprints, *_DEFAULT_BLUEPRINT_ROTATION])
        if not ordered:
            ordered = list(_DEFAULT_BLUEPRINT_ROTATION)
        planned = [ordered[index % len(ordered)] for index in range(target_count)]
        if target_count >= 4 and not any(blueprint.stance == ProfileStance.challenge for blueprint in planned):
            planned[-1] = _ARCHETYPE_BY_SEED["social"]
        return planned


def _tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.findall(r"[a-z0-9]+", stripped.lower())


def _dedupe(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _stable_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "will",
    "into",
    "your",
    "their",
    "about",
    "what",
    "when",
    "where",
    "which",
    "would",
    "there",
    "they",
    "them",
    "could",
    "should",
    "while",
    "also",
    "more",
    "than",
    "only",
    "into",
    "over",
    "under",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "by",
    "as",
    "is",
    "are",
    "be",
    "was",
    "were",
    "les",
    "des",
    "de",
    "du",
    "la",
    "le",
    "un",
    "une",
    "et",
    "ou",
    "dans",
    "sur",
    "pour",
    "avec",
    "sans",
    "par",
    "aux",
    "au",
    "ces",
    "ses",
    "leur",
    "leurs",
    "que",
    "qui",
    "quoi",
    "dont",
    "est",
    "sont",
    "etre",
    "etre",
    "pas",
    "plus",
    "moins",
    "comme",
    "brief",
    "question",
    "objectif",
    "objective",
    "topic",
    "source",
    "sources",
    "plan",
    "reunion",
    "review",
    "systeme",
    "system",
    "local",
    "current",
    "multi",
    "agents",
    "agent",
    "fichier",
    "document",
    "documents",
    "pattern",
    "patterns",
    "exhaustive",
    "integration",
    "integrer",
    "faut",
    "surtout",
    "peut",
    "doit",
    "faire",
    "mieux",
    "encore",
}

_LABEL_BLACKLIST = {
    *_STOPWORDS,
    "default",
    "same",
    "generic",
    "placeholder",
    "participant",
    "participants",
    "agent",
    "agents",
    "profile",
    "profiles",
    "summary",
    "summaries",
    "note",
    "notes",
    "item",
    "items",
}

_PROFILE_ARCHETYPES: list[tuple[str, ProfileRole, ProfileStance, set[str]]] = [
    ("strategy", ProfileRole.strategist, ProfileStance.support, {"strategy", "strategic", "architect", "planner", "plan", "roadmap", "rollout", "launch", "coordination"}),
    ("analysis", ProfileRole.analyst, ProfileStance.cautious, {"analysis", "analyst", "research", "signal", "forecast", "evidence", "calibration", "benchmark"}),
    ("risk", ProfileRole.guardian, ProfileStance.governance, {"risk", "safety", "guard", "policy", "compliance", "control", "rollback", "reliability"}),
    ("ops", ProfileRole.operator, ProfileStance.efficiency, {"ops", "operator", "execution", "latency", "throughput", "infra", "runtime"}),
    ("market", ProfileRole.market, ProfileStance.expansion, {"market", "pricing", "demand", "revenue", "growth", "adoption", "alpha", "edge"}),
    ("social", ProfileRole.social, ProfileStance.challenge, {"social", "community", "audience", "network", "engagement", "dissent", "challenge", "skeptic"}),
    ("governance", ProfileRole.facilitator, ProfileStance.governance, {"governance", "audit", "provenance", "accountability", "oversight"}),
]

_DEFAULT_BLUEPRINT_ROTATION: list[_ProfileBlueprint] = [
    _ProfileBlueprint(label_seed=seed, role=role, stance=stance)
    for seed, role, stance, _aliases in _PROFILE_ARCHETYPES
]

_ARCHETYPE_BY_SEED: dict[str, _ProfileBlueprint] = {
    seed: _ProfileBlueprint(label_seed=seed, role=role, stance=stance)
    for seed, role, stance, _aliases in _PROFILE_ARCHETYPES
}


def _dedupe_blueprints(items: Iterable[_ProfileBlueprint]) -> list[_ProfileBlueprint]:
    unique: dict[tuple[str, str, str], _ProfileBlueprint] = {}
    for item in items:
        unique[(item.label_seed, item.role.value, item.stance.value)] = item
    return list(unique.values())


def _is_generic_label(label: str) -> bool:
    tokens = [token for token in _tokenize(label) if not token.isdigit()]
    if not tokens:
        return True
    meaningful = [token for token in tokens if token not in _LABEL_BLACKLIST and len(token) > 2]
    return not meaningful


def _label_matches_blueprint(label: str, blueprint: _ProfileBlueprint) -> bool:
    normalized = _tokenize(label)
    return bool(normalized) and blueprint.label_seed in normalized
