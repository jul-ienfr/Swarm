from swarm_core.profile_quality_guard import ProfileQualityGuard, ProfileQualityThresholds


def test_profile_quality_guard_passes_grounded_profiles() -> None:
    guard = ProfileQualityGuard()
    report = guard.evaluate(
        [
            {
                "id": "p-1",
                "name": "strategist",
                "summary": "focuses on long-horizon options",
                "sources": ["doc-1"],
                "role": "strategist",
                "stance": "support",
                "confidence": 0.83,
            },
            {
                "id": "p-2",
                "name": "critic",
                "summary": "pushes back on assumptions",
                "graph_refs": ["n-3"],
                "role": "guardian",
                "stance": "oppose",
                "confidence": 0.78,
            },
            {
                "id": "p-3",
                "name": "operator",
                "summary": "keeps the run pragmatic",
                "evidence": ["trace-1"],
                "role": "operator",
                "stance": "neutral",
                "confidence": 0.72,
            },
        ],
        thresholds=ProfileQualityThresholds(min_coverage=1.0, min_grounding=0.66, min_diversity=0.3, min_consistency=0.7),
    )

    assert report.passed is True
    assert report.coverage == 1.0
    assert report.grounding >= 0.66
    assert report.diversity >= 0.3
    assert report.stance_diversity >= 0.3
    assert report.role_diversity >= 0.3


def test_profile_quality_guard_flags_poor_profiles() -> None:
    guard = ProfileQualityGuard()
    report = guard.evaluate(
        [
            {"id": "p-1", "name": "same", "summary": "", "confidence": 1.4},
            {"id": "p-2", "name": "same", "summary": "duplicate voice", "confidence": 0.6},
        ],
        thresholds=ProfileQualityThresholds(min_coverage=1.0, min_grounding=0.5, min_diversity=0.5, min_consistency=0.8),
    )

    assert report.passed is False
    assert report.consistency < 0.8
    assert any(issue.code in {"coverage_low", "grounding_low", "diversity_low", "consistency_low"} for issue in report.issues)


def test_profile_quality_guard_scales_diversity_for_larger_grounded_cohorts() -> None:
    guard = ProfileQualityGuard()
    report = guard.evaluate(
        [
            {
                "id": f"p-{index}",
                "name": f"{role}_{stance}_{index}",
                "summary": f"profile {index} contributes a distinct angle",
                "evidence": [f"doc-{index}"],
                "stance": stance,
                "role": role,
                "confidence": 0.7,
            }
            for index, (stance, role) in enumerate(
                [
                    ("support", "strategist"),
                    ("cautious", "analyst"),
                    ("challenge", "social"),
                    ("governance", "guardian"),
                    ("efficiency", "operator"),
                    ("expansion", "market"),
                    ("support", "facilitator"),
                    ("challenge", "analyst"),
                ],
                start=1,
            )
        ],
        thresholds=ProfileQualityThresholds(min_coverage=1.0, min_grounding=1.0, min_diversity=0.35, min_consistency=0.7),
    )

    assert report.passed is True
    assert report.diversity >= 0.35
    assert report.stance_diversity >= 0.75
    assert report.role_diversity >= 0.75


def test_profile_quality_guard_exposes_role_and_stance_diversity_failures() -> None:
    guard = ProfileQualityGuard()
    report = guard.evaluate(
        [
            {
                "id": "p-1",
                "name": "guardian_support",
                "summary": "focuses on safety constraints",
                "evidence": ["doc-1"],
                "role": "guardian",
                "stance": "governance",
                "confidence": 0.8,
            },
            {
                "id": "p-2",
                "name": "guardian_support_2",
                "summary": "focuses on compliance constraints",
                "evidence": ["doc-2"],
                "role": "guardian",
                "stance": "governance",
                "confidence": 0.82,
            },
        ],
        thresholds=ProfileQualityThresholds(min_coverage=1.0, min_grounding=1.0, min_diversity=0.6, min_consistency=0.7),
    )

    assert report.passed is False
    assert report.stance_diversity == 0.5
    assert report.role_diversity == 0.5
    assert any(issue.code in {"stance_diversity_low", "role_diversity_low"} for issue in report.issues)


def test_profile_quality_guard_counts_role_diversity_when_available() -> None:
    guard = ProfileQualityGuard()
    report = guard.evaluate(
        [
            {
                "id": "p-1",
                "name": "strategy",
                "role": "strategist",
                "summary": "Sets rollout direction.",
                "sources": ["doc-1"],
                "stance": "support",
                "confidence": 0.8,
            },
            {
                "id": "p-2",
                "name": "risk",
                "role": "guardian",
                "summary": "Checks controls and rollback.",
                "sources": ["doc-2"],
                "stance": "governance",
                "confidence": 0.78,
            },
            {
                "id": "p-3",
                "name": "ops",
                "role": "operator",
                "summary": "Keeps execution realistic.",
                "sources": ["doc-3"],
                "stance": "efficiency",
                "confidence": 0.76,
            },
        ],
        thresholds=ProfileQualityThresholds(min_coverage=1.0, min_grounding=1.0, min_diversity=0.5, min_consistency=0.7),
    )

    assert report.passed is True
    assert report.diversity >= 0.5
