from __future__ import annotations

import datetime
import importlib
import json
import threading
from enum import Enum
from pathlib import Path
from typing import Any

import requests
import yaml
from observability import log_structured_event

from openclaw_client import OpenClawClient
from runtime_contracts.intent import EnginePreference, SimulationIntentV1, TaskType

from .agent_registry import SwarmAgentRegistry
from .governance import GovernanceEngine


class RuntimeBackend(str, Enum):
    pydanticai = "pydanticai"
    legacy = "legacy"


def normalize_runtime_backend(runtime: str | RuntimeBackend | None) -> RuntimeBackend:
    if runtime is None:
        return RuntimeBackend.pydanticai
    if isinstance(runtime, RuntimeBackend):
        return runtime
    candidate = str(runtime).strip().lower()
    try:
        return RuntimeBackend(candidate)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in RuntimeBackend)
        raise ValueError(f"Unsupported runtime backend {runtime!r}. Expected one of: {allowed}.") from exc


def runtime_capabilities() -> dict[str, Any]:
    return {
        "supported": [backend.value for backend in RuntimeBackend],
        "default": RuntimeBackend.pydanticai.value,
        "mission_runtime": "langgraph",
    }


def runtime_health(runtime: str | RuntimeBackend | None = None) -> dict[str, Any]:
    selected = normalize_runtime_backend(runtime)
    if selected == RuntimeBackend.legacy:
        return {
            "runtime": selected.value,
            "status": "healthy",
            "configured": True,
            "imports_available": True,
            "fallback_runtime": None,
            "message": "Legacy runtime is local and available in-process.",
        }

    from runtime_pydanticai import PydanticAIRuntimeFactory

    report = PydanticAIRuntimeFactory().health_check()
    return report.model_dump(mode="json")


def run_strategy_meeting_runtime(
    *,
    topic: str,
    objective: str | None = None,
    participants: list[str] | None = None,
    max_agents: int = 6,
    rounds: int = 2,
    persist: bool = True,
    config_path: str = "config.yaml",
    runtime: str | RuntimeBackend = RuntimeBackend.pydanticai,
    allow_fallback: bool = True,
    output_dir: str | Path | None = None,
    client: OpenClawClient | Any | None = None,
):
    from .strategy_meeting import run_strategy_meeting_sync

    selected_runtime = normalize_runtime_backend(runtime)
    try:
        result = run_strategy_meeting_sync(
            topic=topic,
            objective=objective,
            participants=participants,
            max_agents=max_agents,
            rounds=rounds,
            persist=persist,
            config_path=config_path,
            runtime=selected_runtime.value,
            allow_fallback=allow_fallback,
            client=client,
        )
        fallback_used = False
        runtime_used = selected_runtime.value
        runtime_error = None
        log_structured_event(
            "swarm_core.orchestration",
            "info",
            "strategy_meeting_runtime_completed",
            runtime_requested=selected_runtime.value,
            runtime_used=runtime_used,
            fallback_used=fallback_used,
            topic=topic,
            meeting_id=result.meeting_id,
        )
    except Exception as exc:
        if selected_runtime != RuntimeBackend.pydanticai or not allow_fallback:
            log_structured_event(
                "swarm_core.orchestration",
                "error",
                "strategy_meeting_runtime_failed",
                runtime_requested=selected_runtime.value,
                runtime_used=selected_runtime.value,
                fallback_used=False,
                topic=topic,
                error=str(exc),
            )
            raise
        result = run_strategy_meeting_sync(
            topic=topic,
            objective=objective,
            participants=participants,
            max_agents=max_agents,
            rounds=rounds,
            persist=persist,
            config_path=config_path,
            runtime=RuntimeBackend.legacy.value,
            allow_fallback=True,
            client=client,
        )
        fallback_used = True
        runtime_used = RuntimeBackend.legacy.value
        runtime_error = str(exc)
        log_structured_event(
            "swarm_core.orchestration",
            "warning",
            "strategy_meeting_runtime_fallback",
            runtime_requested=selected_runtime.value,
            runtime_used=runtime_used,
            fallback_used=fallback_used,
            topic=topic,
            error=runtime_error,
        )
    result.metadata.setdefault("runtime_requested", selected_runtime.value)
    result.metadata.setdefault("runtime_used", runtime_used)
    result.metadata.setdefault("fallback_used", fallback_used)
    if runtime_error is not None:
        result.metadata.setdefault("runtime_error", runtime_error)
    if output_dir is not None and result.persisted_path:
        desired_dir = Path(output_dir)
        desired_dir.mkdir(parents=True, exist_ok=True)
        target_path = desired_dir / f"{result.meeting_id}.json"
        payload = result.model_dump_json(indent=2)
        target_path.write_text(payload, encoding="utf-8")
        result.persisted_path = str(target_path)
    return result


def run_deliberation_runtime(
    *,
    topic: str,
    objective: str | None = None,
    mode: str = "committee",
    participants: list[str] | None = None,
    documents: list[str] | None = None,
    entities: list[Any] | None = None,
    interventions: list[str] | None = None,
    max_agents: int = 6,
    population_size: int | None = None,
    rounds: int = 2,
    time_horizon: str = "7d",
    persist: bool = True,
    config_path: str = "config.yaml",
    runtime: str | RuntimeBackend = RuntimeBackend.pydanticai,
    allow_fallback: bool = True,
    engine_preference: EnginePreference = EnginePreference.agentsociety,
    ensemble_engines: list[EnginePreference | str] | None = None,
    budget_max: float = 10.0,
    timeout_seconds: int = 1800,
    benchmark_path: str | None = None,
    stability_runs: int = 1,
    output_dir: str | Path | None = None,
    backend_mode: str | None = None,
    client: OpenClawClient | Any | None = None,
):
    from .deliberation import run_deliberation_sync

    selected_runtime = normalize_runtime_backend(runtime)
    result = run_deliberation_sync(
        topic=topic,
        objective=objective,
        mode=mode,
        participants=participants,
        documents=documents,
        entities=entities,
        interventions=interventions,
        max_agents=max_agents,
        population_size=population_size,
        rounds=rounds,
        time_horizon=time_horizon,
        persist=persist,
        config_path=config_path,
        runtime=selected_runtime.value,
        allow_fallback=allow_fallback,
        engine_preference=engine_preference,
        ensemble_engines=ensemble_engines,
        budget_max=budget_max,
        timeout_seconds=timeout_seconds,
        benchmark_path=benchmark_path,
        stability_runs=stability_runs,
        output_dir=output_dir,
        backend_mode=backend_mode,
        client=client,
    )
    log_structured_event(
        "swarm_core.orchestration",
        "info",
            "deliberation_runtime_completed",
            runtime_requested=selected_runtime.value,
            runtime_used=result.runtime_used,
            fallback_used=result.fallback_used,
            engine_requested=result.engine_requested,
            engine_used=result.engine_used,
            ensemble_engines=result.ensemble_report.compared_engines if result.ensemble_report else [],
            topic=topic,
        deliberation_id=result.deliberation_id,
        mode=mode,
        status=result.status.value,
    )
    return result


def send_webhook(config: dict[str, Any], message: str) -> None:
    webhook_url = config.get("orchestrator", {}).get("webhook_url")
    if not webhook_url:
        return

    def _post() -> None:
        try:
            requests.post(webhook_url, json={"text": message}, timeout=5)
        except Exception as exc:
            print(f"[Webhook Error] {exc}")

    threading.Thread(target=_post).start()


def get_intent_from_state(state: dict[str, Any]) -> SimulationIntentV1 | None:
    raw_intent = state.get("current_intent") or state.get("task_ledger", {}).get("current_intent")
    if not raw_intent:
        return None
    if isinstance(raw_intent, SimulationIntentV1):
        return raw_intent
    try:
        return SimulationIntentV1.model_validate(raw_intent)
    except Exception:
        return None


def is_simulation_state(state: dict[str, Any]) -> bool:
    intent = get_intent_from_state(state)
    return bool(intent and intent.task_type == TaskType.scenario_simulation)


class SwarmSupervisorService:
    """Swarm-side orchestration logic extracted from the LangGraph node wrapper."""

    def __init__(
        self,
        *,
        config_path: str = "config.yaml",
        client: OpenClawClient | None = None,
        registry: SwarmAgentRegistry | None = None,
    ) -> None:
        with open(config_path, "r", encoding="utf-8") as handle:
            self.config = yaml.safe_load(handle) or {}

        orch_config = self.config.get("orchestrator", {})
        self.governance = GovernanceEngine(
            max_stall_count=orch_config.get("max_stall_count", 3),
            max_replan=orch_config.get("max_replan", 4),
            max_steps_total=orch_config.get("max_steps_total", 50),
        )
        self.client = client or OpenClawClient(config_path=config_path)
        self.registry = registry or SwarmAgentRegistry(client=self.client)
        self.name = "Supervisor"
        self.tier = "tier3_paid"
        self.model = "claude-sonnet-4-6"
        self.runtime_backend = normalize_runtime_backend(orch_config.get("runtime", RuntimeBackend.pydanticai.value))
        self.allow_runtime_fallback = bool(orch_config.get("allow_fallback", True))
        self.supervisor_planner = self._build_supervisor_planner(config_path=config_path)

    def _build_supervisor_planner(self, *, config_path: str):
        if self.runtime_backend == RuntimeBackend.legacy:
            return None
        try:
            supervisor_module = importlib.import_module("runtime_pydanticai.supervisor")
            models_module = importlib.import_module("runtime_pydanticai.models")
            planner_cls = getattr(supervisor_module, "PydanticAISupervisorPlanner")
            fallback_policy_cls = getattr(models_module, "RuntimeFallbackPolicy")
            return planner_cls(
                config_path=config_path,
                fallback_policy=fallback_policy_cls("on_error" if self.allow_runtime_fallback else "never"),
            )
        except Exception as exc:
            print(f"\n[PYDANTICAI ORCHESTRATOR WARNING] {exc}")
            return None

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        task_ledger = state.get("task_ledger", {})
        progress_ledger = state.get("progress_ledger", {})

        governance = self.governance.evaluate(task_ledger, progress_ledger)
        task_ledger = governance.task_ledger
        progress_ledger = governance.progress_ledger
        stall_count = progress_ledger.get("stall_count", 0)
        step_index = progress_ledger.get("step_index", 0)

        if governance.should_short_circuit:
            if task_ledger.get("action") == "ABORT":
                send_webhook(
                    self.config,
                    f"Mission Aborted: {task_ledger.get('replan_reason', 'Governance guardrail triggered.')}",
                )
            return {"task_ledger": task_ledger, "progress_ledger": progress_ledger}

        assignments: list[dict[str, str]]
        tokens_used = 0
        if self.runtime_backend == RuntimeBackend.legacy or self.supervisor_planner is None:
            legacy_result = self._execute_legacy_plan(state, task_ledger, progress_ledger, stall_count)
            if legacy_result is None:
                return {"progress_ledger": progress_ledger}
            assignments, tokens_used = legacy_result
            progress_ledger["orchestrator_runtime"] = RuntimeBackend.legacy.value
            progress_ledger["orchestrator_fallback_used"] = False
        else:
            try:
                supervisor_module = importlib.import_module("runtime_pydanticai.supervisor")
                supervisor_input_cls = getattr(supervisor_module, "SupervisorPlanningInput")
                plan = self.supervisor_planner.plan_assignments(
                    supervisor_input_cls(
                        goal=task_ledger.get("goal", ""),
                        plan=list(task_ledger.get("plan", []) or []),
                        recent_outputs=list(state.get("workers_output", [])[-3:]),
                        registry_catalog=self.registry.get_prompt_catalog(),
                        replan_reason=task_ledger.get("replan_reason"),
                        current_intent=state.get("current_intent") or task_ledger.get("current_intent"),
                        goal_complete_hint=bool(progress_ledger.get("is_complete")),
                        max_assignments=4,
                    )
                )
            except Exception as exc:
                print(f"\n[PYDANTICAI ORCHESTRATOR ERROR] {exc}")
                progress_ledger["orchestrator_error"] = str(exc)
                if self.allow_runtime_fallback:
                    legacy_result = self._execute_legacy_plan(state, task_ledger, progress_ledger, stall_count)
                    if legacy_result is None:
                        progress_ledger["orchestrator_runtime"] = RuntimeBackend.pydanticai.value
                        progress_ledger["orchestrator_fallback_used"] = False
                        return {"progress_ledger": progress_ledger}
                    assignments, tokens_used = legacy_result
                    progress_ledger["orchestrator_runtime"] = RuntimeBackend.legacy.value
                    progress_ledger["orchestrator_fallback_used"] = True
                else:
                    progress_ledger["stall_count"] = stall_count + 1
                    progress_ledger["is_stuck"] = True
                    progress_ledger["orchestrator_runtime"] = RuntimeBackend.pydanticai.value
                    progress_ledger["orchestrator_fallback_used"] = False
                    return {"progress_ledger": progress_ledger}
            else:
                assignments = [
                    {"speaker": assignment.speaker, "instruction": assignment.instruction}
                    for assignment in sorted(plan.assignments, key=lambda item: item.priority)
                    if assignment.speaker
                ]
                if plan.complete and not assignments:
                    assignments = [{"speaker": "COMPLETE", "instruction": plan.rationale or "Goal achieved."}]
                if not assignments and not plan.complete:
                    progress_ledger["stall_count"] = stall_count + 1
                    progress_ledger["is_stuck"] = True
                    progress_ledger["orchestrator_runtime"] = plan.runtime_used.value
                    progress_ledger["orchestrator_fallback_used"] = plan.fallback_used
                    if plan.error:
                        progress_ledger["orchestrator_error"] = plan.error
                    return {"progress_ledger": progress_ledger}

                progress_ledger["orchestrator_runtime"] = plan.runtime_used.value
                progress_ledger["orchestrator_fallback_used"] = plan.fallback_used
                if plan.error:
                    progress_ledger["orchestrator_error"] = plan.error

        current_tokens = state.get("tokens_used_total", 0)
        progress_ledger["assignments"] = assignments
        if assignments:
            progress_ledger["next_speaker"] = assignments[0]["speaker"]
            progress_ledger["instruction"] = assignments[0]["instruction"]
        progress_ledger["step_index"] = step_index + 1
        progress_ledger["last_updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"

        if task_ledger.get("replan_reason"):
            task_ledger["replan_reason"] = None

        if any(assignment.get("speaker") == "COMPLETE" for assignment in assignments):
            progress_ledger["is_complete"] = True
            task_ledger["action"] = "APPLY"
            send_webhook(self.config, f"Mission Complete: {task_ledger.get('goal', '')}")

        return {
            "progress_ledger": progress_ledger,
            "task_ledger": task_ledger,
            "tokens_used_total": current_tokens + tokens_used,
        }

    def _execute_legacy_plan(
        self,
        state: dict[str, Any],
        task_ledger: dict[str, Any],
        progress_ledger: dict[str, Any],
        stall_count: int,
    ) -> tuple[list[dict[str, str]], int] | None:
        messages = self._build_messages(state, task_ledger)
        result = self.client.chat_with_escalation(self.name, messages, self.tier, self.model)
        if not result.get("success"):
            print(f"\n[ORCHESTRATOR ERROR] {result.get('error')}")
            progress_ledger["stall_count"] = stall_count + 1
            return None

        try:
            assignments = self._parse_assignments(result.get("content", ""))
        except json.JSONDecodeError:
            print(f"\n[JSON ERROR] Raw content was: {result.get('content')}")
            progress_ledger["stall_count"] = stall_count + 1
            progress_ledger["is_stuck"] = True
            return None

        tokens_used = int(result.get("tokens_used", 0) or 0)
        return assignments, tokens_used

    def _build_messages(self, state: dict[str, Any], task_ledger: dict[str, Any]) -> list[dict[str, str]]:
        goal = task_ledger.get("goal", "")
        plan = task_ledger.get("plan", [])
        recent_outputs = state.get("workers_output", [])[-3:]
        replan_msg = ""
        if task_ledger.get("replan_reason"):
            replan_msg = (
                "\n[CRITICAL - REPLAN TRIGGERED]:\n"
                f"{task_ledger.get('replan_reason')}\n"
                "You MUST address this replan reason immediately before continuing the main plan.\n"
            )

        context = f"GOAL: {goal}\nPLAN: {plan}\n{replan_msg}\nRECENT ACTIONS:\n"
        for output in recent_outputs:
            context += f"[{output.get('worker_name', 'Unknown')}]: {output.get('content', '')[:200]}...\n"

        system_prompt = (
            "You are the Orchestrator of a Multi-Agent Swarm.\n"
            "Your job is to read the Goal, the Plan, and the Recent Outputs, "
            "then decide WHICH agent should act next, and give them a very specific INSTRUCTION.\n"
            f"{self.registry.get_prompt_catalog()}"
            "--- GLOBAL POLICIES (IMPOSE THESE ON ALL AGENTS) ---\n"
            "1. NEVER guess, invent, or hardcode configurations, command lines, pools, or wallets for any service/miner. "
            "Always instruct the agent to use existing local services (systemctl) or local scripts.\n"
            "2. If the current intent is a scenario simulation, prefer the simulation_runtime worker instead of ad hoc worker fan-out.\n"
            "----------------------------------------------------\n"
            "If the goal is achieved, output EXACTLY the word 'COMPLETE' as the next agent.\n"
            "You can delegate to multiple agents in PARALLEL by adding multiple assignments.\n"
            "--- DEBATE MODE ---\n"
            "If you face a complex architectural choice or need a critical code review, you can trigger a debate between two agents.\n"
            "To do this, use 'debate_room' as the speaker, and format the instruction exactly like this: '[AgentA vs AgentB] The topic to debate'.\n"
            "-------------------\n"
            'You MUST output JSON in this exact format: {"assignments": [{"speaker": "architect", "instruction": "Write the script..."}]}'
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ]

    @staticmethod
    def _parse_assignments(raw_content: str) -> list[dict[str, str]]:
        raw = raw_content.replace("```json", "").replace("```", "").strip()
        decision = json.loads(raw)
        assignments = decision.get("assignments", [])
        if not assignments and "next_speaker" in decision:
            assignments = [{"speaker": decision.get("next_speaker"), "instruction": decision.get("instruction")}]
        return [
            {
                "speaker": str(assignment.get("speaker", "")),
                "instruction": str(assignment.get("instruction", "")),
            }
            for assignment in assignments
            if assignment.get("speaker")
        ]


class SwarmExecutionErrorHandler:
    """Swarm-side worker failure policy extracted from the LangGraph wrapper."""

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        progress_ledger = state.get("progress_ledger", {})
        task_ledger = state.get("task_ledger", {})
        recent_outputs = state.get("workers_output", [])
        if not recent_outputs:
            return {}

        last_output = recent_outputs[-1]
        worker_name = last_output.get("worker_name", "Unknown")
        error_msg = last_output.get("error", "")

        if "401" in error_msg:
            task_ledger["action"] = "ABORT"
            task_ledger["replan_reason"] = (
                f"CRITICAL AUTH ERROR: Agent '{worker_name}' received HTTP 401 Unauthorized. "
                "This means the API key is missing, invalid, or out of credits. "
                "Check the provider configuration in OpenClaw gateway / API keys. "
                "Aborting to prevent infinite loops."
            )
            progress_ledger["is_complete"] = True
            return {"progress_ledger": progress_ledger, "task_ledger": task_ledger}

        if "empty content" in error_msg.lower() or "tool error" in error_msg.lower() or "not found" in error_msg.lower():
            task_ledger["action"] = "REPLAN"
            task_ledger["replan_reason"] = (
                f"AUTO-HEALING REQUIRED: Agent '{worker_name}' failed with error: '{error_msg}'. "
                "This usually means the agent lacks the required tool/skill. "
                "ACTION REQUIRED: Delegate immediately to 'architect' to: "
                "1. Search if an appropriate tool exists in ~/.openclaw/skills/. "
                "2. If yes, install it by editing ~/.openclaw/agents/{worker_name}/agent.json and adding the skill ID. "
                "3. Modify the skill if needed (respecting constraints). "
                "4. If no such tool exists, create it from scratch in ~/.openclaw/skills/."
            )
            return {"progress_ledger": progress_ledger, "task_ledger": task_ledger}

        progress_ledger["stall_count"] = progress_ledger.get("stall_count", 0) + 1
        progress_ledger["is_stuck"] = True
        return {"progress_ledger": progress_ledger, "task_ledger": task_ledger}
