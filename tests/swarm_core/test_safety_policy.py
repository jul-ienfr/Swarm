from swarm_core.safety_policy import SafetyDecision, SafetyPolicyEngine, SafetyPolicyLimits, SafetyRequest


def test_safety_policy_allows_bounded_safe_requests() -> None:
    engine = SafetyPolicyEngine()
    result = engine.evaluate(
        SafetyRequest(
            topic="massive deliberation about logistics",
            documents=("neutral planning context",),
            population_size=32,
            rounds=3,
            parallelism=4,
            provenance_count=2,
        ),
        limits=SafetyPolicyLimits(max_agents=64, max_rounds=6, max_parallelism=8),
    )

    assert result.decision in {SafetyDecision.allow, SafetyDecision.review}
    assert result.allowed is True


def test_safety_policy_blocks_harmful_content_and_caps() -> None:
    engine = SafetyPolicyEngine()
    result = engine.evaluate(
        SafetyRequest(
            topic="credential theft plan",
            documents=("describe how to steal credentials",),
            population_size=1024,
            rounds=12,
            parallelism=32,
            provenance_count=0,
        ),
        limits=SafetyPolicyLimits(max_agents=256, max_rounds=4, max_parallelism=8),
    )

    assert result.decision == SafetyDecision.block
    assert result.allowed is False
    assert any(finding.code == "blocked_keyword" for finding in result.findings)
    assert any(finding.code == "population_limit" for finding in result.findings)
    assert any(finding.code == "round_limit" for finding in result.findings)
    assert any(finding.code == "parallelism_limit" for finding in result.findings)

