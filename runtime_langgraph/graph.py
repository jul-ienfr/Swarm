from __future__ import annotations

import os
import sqlite3
from typing import Any

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph

from ledger_state import SupervisorState
from runtime_langgraph.nodes import (
    make_simulation_finalize_node,
    make_simulation_node,
    route_initial_mission,
    route_simulation_progress,
)
from runtime_langgraph.state import build_initial_state, json_safe
from simulation_adapter.factory import build_default_adapter_service
from supervisor import ErrorHandlerNode, SupervisorNode, route_supervisor_decision, route_worker_output
from swarm_core.agent_registry import get_dynamic_agents
from workers import OpenClawDebateWorker, OpenClawDelegateWorker
from workers.media_generator import MediaGenerator
from workers.video_assembler import VideoAssembler


def _build_checkpointer(checkpoints_path: str):
    os.makedirs(os.path.dirname(checkpoints_path), exist_ok=True)
    conn = sqlite3.connect(checkpoints_path, check_same_thread=False)
    return SqliteSaver(conn)


def _add_custom_nodes(workflow: StateGraph, config_path: str) -> list[str]:
    config_hardware = {
        "rig1_ip": "192.168.31.9",
        "encoder_ip": "192.168.31.116",
        "encoder_user": "julien",
    }
    workflow.add_node("studio-media", MediaGenerator(config_hardware).execute)
    workflow.add_node("video-assembler", VideoAssembler(config_hardware).execute)
    workflow.add_node("debate_room", OpenClawDebateWorker(config_path).execute)
    return ["studio-media", "video-assembler", "debate_room"]


def compile_graph(config_path: str = "config.yaml", checkpoints_path: str | None = None):
    workflow = StateGraph(SupervisorState)

    supervisor = SupervisorNode(config_path)
    error_handler = ErrorHandlerNode(config_path)
    adapter_service = build_default_adapter_service()

    workflow.add_node("intent_router", lambda state: state)
    workflow.add_node("Supervisor", supervisor.execute)
    workflow.add_node("ErrorHandler", error_handler.execute)
    workflow.add_node("simulation_runtime", make_simulation_node(adapter_service))
    workflow.add_node("simulation_finalize", make_simulation_finalize_node())

    custom_agent_names = _add_custom_nodes(workflow, config_path)

    loaded_agents: list[str] = []
    for agent_name in get_dynamic_agents():
        if agent_name not in custom_agent_names:
            worker = OpenClawDelegateWorker(agent_name, config_path)
            workflow.add_node(agent_name, worker.execute)
            loaded_agents.append(agent_name)

    interactive_workers = custom_agent_names + loaded_agents

    workflow.set_entry_point("intent_router")

    workflow.add_conditional_edges(
        "intent_router",
        route_initial_mission,
        {"simulation_runtime": "simulation_runtime", "Supervisor": "Supervisor"},
    )

    workflow.add_conditional_edges(
        "Supervisor",
        route_supervisor_decision,
        interactive_workers + ["simulation_runtime", "Supervisor", "__end__"],
    )

    for worker in interactive_workers:
        workflow.add_conditional_edges(
            worker,
            route_worker_output,
            {"Supervisor": "Supervisor", "ErrorHandler": "ErrorHandler"},
        )

    workflow.add_conditional_edges(
        "simulation_runtime",
        route_simulation_progress,
        {"simulation_runtime": "simulation_runtime", "simulation_finalize": "simulation_finalize"},
    )
    workflow.add_edge("simulation_finalize", "__end__")

    workflow.add_edge("ErrorHandler", "Supervisor")

    checkpoints_path = checkpoints_path or "/home/jul/.openclaw/workspace/langgraph-swarm/data/checkpoints.db"
    checkpointer = _build_checkpointer(checkpoints_path)

    return workflow.compile(checkpointer=checkpointer, interrupt_before=[])


def get_graph_and_config(thread_id: str = "default_mission") -> tuple[Any, dict[str, Any]]:
    graph = compile_graph()
    return graph, {"configurable": {"thread_id": thread_id}}


def build_mission_state(goal: str, thread_id: str = "default_mission", source: str = "cli") -> dict[str, Any]:
    return json_safe(build_initial_state(goal=goal, thread_id=thread_id, source=source))
