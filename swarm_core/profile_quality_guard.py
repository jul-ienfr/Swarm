from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import unicodedata
from typing import Any, Iterable, Mapping


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ProfileQualityThresholds:
    min_coverage: float = 0.8
    min_grounding: float = 0.6
    min_diversity: float = 0.35
    min_consistency: float = 0.7
    min_label_quality: float = 0.55


@dataclass(slots=True)
class ProfileQualityIssue:
    code: str
    message: str


@dataclass(slots=True)
class ProfileQualityReport:
    total_profiles: int
    coverage: float
    grounding: float
    diversity: float
    stance_diversity: float
    role_diversity: float
    consistency: float
    label_quality: float
    overall_score: float
    passed: bool
    issues: list[ProfileQualityIssue] = field(default_factory=list)
    checked_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_profiles": self.total_profiles,
            "coverage": self.coverage,
            "grounding": self.grounding,
            "diversity": self.diversity,
            "stance_diversity": self.stance_diversity,
            "role_diversity": self.role_diversity,
            "consistency": self.consistency,
            "label_quality": self.label_quality,
            "overall_score": self.overall_score,
            "passed": self.passed,
            "issues": [{"code": issue.code, "message": issue.message} for issue in self.issues],
            "checked_at": self.checked_at,
        }


class ProfileQualityGuard:
    """
    Minimal quality guard for persona/profile generation.

    The guard focuses on a few measurable properties so it can be used as a
    pre-flight step in the massive deliberation pipeline.
    """

    REQUIRED_FIELDS = ("summary",)

    def evaluate(
        self,
        profiles: Iterable[Mapping[str, Any]],
        *,
        thresholds: ProfileQualityThresholds | None = None,
    ) -> ProfileQualityReport:
        thresholds = thresholds or ProfileQualityThresholds()
        items = [dict(profile) for profile in profiles]
        total = len(items)
        if total == 0:
            return ProfileQualityReport(
                total_profiles=0,
                coverage=0.0,
                grounding=0.0,
                diversity=0.0,
                stance_diversity=0.0,
                role_diversity=0.0,
                consistency=0.0,
                label_quality=0.0,
                overall_score=0.0,
                passed=False,
                issues=[ProfileQualityIssue(code="empty", message="no profiles provided")],
            )

        coverage_hits = 0
        grounded_hits = 0
        valid_confidence_hits = 0
        label_quality_total = 0.0
        stances: set[str] = set()
        roles: set[str] = set()
        seen_names: dict[str, str] = {}
        issues: list[ProfileQualityIssue] = []
        contradiction_count = 0

        for profile in items:
            identifier = _first_non_empty(profile, ("name", "label", "id", "profile_id"))
            summary = _first_non_empty(profile, ("summary", "persona_summary", "thesis", "description"))
            required_ok = bool(identifier and summary)
            if required_ok:
                coverage_hits += 1
            else:
                issues.append(
                    ProfileQualityIssue(
                        code="missing_required_fields",
                        message="profile missing an identifier or summary",
                    )
                )

            grounded = bool(profile.get("sources") or profile.get("evidence") or profile.get("graph_refs") or profile.get("belief_refs"))
            if grounded:
                grounded_hits += 1

            confidence = profile.get("confidence")
            if confidence is None or (isinstance(confidence, (int, float)) and 0.0 <= float(confidence) <= 1.0):
                valid_confidence_hits += 1
            else:
                issues.append(ProfileQualityIssue(code="invalid_confidence", message=f"invalid confidence for {identifier!r}"))

            stance = str(profile.get("stance", "")).strip().lower()
            if stance:
                stances.add(stance)
            role = str(profile.get("role", "")).strip().lower() or _infer_role_from_identifier(identifier)
            if role:
                roles.add(role)

            name = str(identifier or "").strip().lower()
            if name:
                previous_stance = seen_names.get(name)
                if previous_stance is None:
                    seen_names[name] = stance
                elif previous_stance and stance and previous_stance != stance:
                    contradiction_count += 1
                    issues.append(
                        ProfileQualityIssue(
                            code="contradiction",
                            message=f"profile {identifier!r} changes stance from {previous_stance!r} to {stance!r}",
                        )
                    )

            label_quality_source = identifier or ""
            if role and _label_quality_score(label_quality_source) == 0.0:
                label_quality_source = role
            profile_label_quality = _label_quality_score(label_quality_source)
            label_quality_total += profile_label_quality
            if profile_label_quality < thresholds.min_label_quality:
                issues.append(
                    ProfileQualityIssue(
                        code="generic_label",
                        message=f"profile label {identifier!r} is too generic or uninformative",
                    )
                )

        coverage = coverage_hits / total
        grounding = grounded_hits / total
        stance_diversity = len(stances) / max(1, min(total, 6))
        role_diversity = len(roles) / max(1, min(total, 8))
        diversity_components: list[float] = []
        if stances:
            diversity_components.append(stance_diversity)
        if roles:
            diversity_components.append(role_diversity)
        diversity = sum(diversity_components) / len(diversity_components) if diversity_components else 0.0
        consistency = max(0.0, 1.0 - (contradiction_count / max(1, total)))
        consistency = min(consistency, valid_confidence_hits / total)
        label_quality = label_quality_total / total
        overall_score = round((coverage + grounding + diversity + consistency + label_quality) / 5.0, 3)

        passed = (
            coverage >= thresholds.min_coverage
            and grounding >= thresholds.min_grounding
            and diversity >= thresholds.min_diversity
            and (
                (not stances and not roles)
                or stance_diversity >= thresholds.min_diversity
                or role_diversity >= thresholds.min_diversity
            )
            and consistency >= thresholds.min_consistency
            and label_quality >= thresholds.min_label_quality
        )

        if not passed:
            if coverage < thresholds.min_coverage:
                issues.append(ProfileQualityIssue(code="coverage_low", message=f"coverage {coverage:.2f} < {thresholds.min_coverage:.2f}"))
            if grounding < thresholds.min_grounding:
                issues.append(ProfileQualityIssue(code="grounding_low", message=f"grounding {grounding:.2f} < {thresholds.min_grounding:.2f}"))
            if diversity < thresholds.min_diversity:
                issues.append(ProfileQualityIssue(code="diversity_low", message=f"diversity {diversity:.2f} < {thresholds.min_diversity:.2f}"))
            if stances and stance_diversity < thresholds.min_diversity:
                issues.append(
                    ProfileQualityIssue(
                        code="stance_diversity_low",
                        message=f"stance diversity {stance_diversity:.2f} < {thresholds.min_diversity:.2f}",
                    )
                )
            if roles and role_diversity < thresholds.min_diversity:
                issues.append(
                    ProfileQualityIssue(
                        code="role_diversity_low",
                        message=f"role diversity {role_diversity:.2f} < {thresholds.min_diversity:.2f}",
                    )
                )
            if consistency < thresholds.min_consistency:
                issues.append(ProfileQualityIssue(code="consistency_low", message=f"consistency {consistency:.2f} < {thresholds.min_consistency:.2f}"))
            if label_quality < thresholds.min_label_quality:
                issues.append(ProfileQualityIssue(code="label_quality_low", message=f"label quality {label_quality:.2f} < {thresholds.min_label_quality:.2f}"))

        return ProfileQualityReport(
            total_profiles=total,
            coverage=round(coverage, 3),
            grounding=round(grounding, 3),
            diversity=round(diversity, 3),
            stance_diversity=round(stance_diversity, 3),
            role_diversity=round(role_diversity, 3),
            consistency=round(consistency, 3),
            label_quality=round(label_quality, 3),
            overall_score=overall_score,
            passed=passed,
            issues=issues,
        )


def _first_non_empty(profile: Mapping[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = profile.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _label_quality_score(label: str) -> float:
    tokens = [token for token in _tokenize(label) if not token.isdigit()]
    if not tokens:
        return 0.0
    meaningful = [token for token in tokens if token not in _LABEL_BLACKLIST and len(token) > 2]
    if not meaningful:
        return 0.0
    if _looks_like_placeholder(label):
        return 0.0
    score = len(meaningful) / len(tokens)
    if len(meaningful) == 1 and len(meaningful[0]) <= 3:
        score *= 0.75
    return round(max(0.0, min(1.0, score)), 3)


def _infer_role_from_identifier(identifier: str) -> str:
    tokens = set(_tokenize(identifier))
    if tokens & {"strategy", "strategist", "architect", "planner", "roadmap"}:
        return "strategist"
    if tokens & {"analysis", "analyst", "research", "forecast"}:
        return "analyst"
    if tokens & {"risk", "safety", "guard", "policy", "compliance", "critic", "redteam"}:
        return "guardian"
    if tokens & {"ops", "operator", "execution", "infra", "runtime"}:
        return "operator"
    if tokens & {"market", "pricing", "revenue", "growth"}:
        return "market"
    if tokens & {"social", "community", "network"}:
        return "social"
    if tokens & {"facilitator", "moderator", "chair"}:
        return "facilitator"
    return ""


def _looks_like_placeholder(label: str) -> bool:
    normalized = _normalize_text(label)
    return bool(re.fullmatch(r"(profile|participant|agent|default|generic)(_?\d+)?", normalized))


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in normalized if not unicodedata.combining(char))
    return stripped.lower().strip()


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _normalize_text(text))


_LABEL_BLACKLIST = {
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
    "summary",
    "summaries",
    "note",
    "notes",
    "item",
    "items",
    "default",
    "same",
    "generic",
    "placeholder",
    "participant",
    "participants",
    "profile",
    "profiles",
}
