from swarm_core.deliberation_artifacts import DeliberationMode
from swarm_core.deliberation_interview import DeliberationInterviewTarget, DeliberationInterviewTargetType
from swarm_core.deliberation_persona_chat import DeliberationPersonaChatService


def test_deliberation_persona_chat_builds_session(tmp_path) -> None:
    service = DeliberationPersonaChatService(output_dir=tmp_path)
    target = DeliberationInterviewTarget(
        target_id="agent_guardian",
        target_type=DeliberationInterviewTargetType.agent,
        label="guardian",
        description="Risk-focused participant",
        metadata={"mode": DeliberationMode.committee.value},
    )
    session = service.start_or_continue(
        deliberation_id="delib_demo",
        topic="launch plan",
        objective="keep rollout safe",
        target=target,
        question="What worries you most?",
    )
    saved = service.save(session)
    html = service.export_html(session)

    assert session.turns
    assert session.round_summaries
    assert saved.exists()
    assert html.exists()
    assert "Persona Chat" in html.read_text(encoding="utf-8")
