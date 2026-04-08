from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field


class WorkbenchTaskStatus(str, Enum):
    pending = "pending"
    completed = "completed"


class WorkbenchTask(BaseModel):
    task_id: str
    label: str
    status: WorkbenchTaskStatus = WorkbenchTaskStatus.pending
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkbenchTaskPlan(BaseModel):
    workbench_id: str
    tasks: list[WorkbenchTask] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return target


def build_default_workbench_task_plan(
    *,
    workbench_id: str,
    include_visuals: bool = True,
    include_provenance: bool = True,
) -> WorkbenchTaskPlan:
    labels = [
        "normalize_inputs",
        "generate_profiles",
        "build_graph",
        "prepare_engine_config",
        "run_engine",
        "build_report",
    ]
    if include_visuals:
        labels.append("build_visuals")
    if include_provenance:
        labels.append("persist_provenance")
    return WorkbenchTaskPlan(
        workbench_id=workbench_id,
        tasks=[
            WorkbenchTask(task_id=f"{workbench_id}_{label}", label=label, status=WorkbenchTaskStatus.completed)
            for label in labels
        ],
    )
