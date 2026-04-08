from __future__ import annotations

from improvement_loop.controller import ImprovementLoopController
from improvement_loop.models import ImprovementRoundRecord, LoopDecision, LoopMode, TargetDescriptor, TargetInspection


class FakeTarget:
    def __init__(self) -> None:
        self.rounds = 0

    def describe(self) -> TargetDescriptor:
        return TargetDescriptor(
            target_id="fake",
            description="Synthetic target for controller tests.",
        )

    def inspect(self) -> TargetInspection:
        return TargetInspection(
            descriptor=self.describe(),
            current_snapshot={"version": "snap_1"},
            benchmark={"suite_version": "v1", "cases": []},
        )

    def run_round(self, mode: LoopMode) -> ImprovementRoundRecord:
        self.rounds += 1
        decision = LoopDecision.propose if self.rounds == 1 else LoopDecision.halt
        return ImprovementRoundRecord(
            target_id="fake",
            round_index=self.rounds,
            mode=mode,
            decision=decision,
            baseline_score=0.1 * self.rounds,
            candidate_score=0.2 * self.rounds,
            score_delta=0.1 * self.rounds,
            improvement_ratio=1.0,
            current_snapshot={"version": f"current_{self.rounds}"},
            candidate_snapshot={"version": f"candidate_{self.rounds}"},
            applied_snapshot={"version": f"applied_{self.rounds}"},
            proposal={"summary": "test proposal"},
            baseline_report={"score": 0.1 * self.rounds},
            candidate_report={"score": 0.2 * self.rounds},
            halted_reason="Reached synthetic halt." if decision == LoopDecision.halt else None,
        )


def test_controller_lists_targets_and_runs_bounded_loop() -> None:
    controller = ImprovementLoopController()
    controller.register_target(FakeTarget())

    descriptors = controller.list_targets()
    assert [descriptor.target_id for descriptor in descriptors] == ["fake"]

    inspection = controller.inspect_target("fake")
    assert inspection.descriptor.target_id == "fake"

    loop_run = controller.run_loop("fake", mode=LoopMode.suggest_only, max_rounds=5)
    assert loop_run.completed_rounds == 2
    assert loop_run.rounds[-1].decision == LoopDecision.halt
    assert loop_run.stopped_reason == "Reached synthetic halt."
