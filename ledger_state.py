from typing import Annotated, TypedDict, List, Literal, Any, Optional, Dict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

# ==============================================================================
# UNIFIED OUTPUT FORMAT
# ==============================================================================
class LLMResult(TypedDict):
    """Standardized output from any worker or orchestration node."""
    worker_name: str
    content: str
    metadata: Dict[str, Any]
    success: bool
    error: Optional[str]
    tokens_used: int

# ==============================================================================
# SMART REDUCERS
# ==============================================================================
def merge_worker_outputs(left: List[LLMResult], right: List[LLMResult]) -> List[LLMResult]:
    """Keeps the state 'boring and small' by enforcing a rolling window."""
    if not left:
        left = []
    if not right:
        return left
    
    # Merge and keep only the last 50 entries to prevent memory leaks in infinite loops
    merged = left + right
    return merged[-50:]

def update_token_count(left: int, right: int) -> int:
    """Accumulates total tokens used across the entire run."""
    return (left or 0) + (right or 0)


def merge_dict(left: Any, right: Any) -> Any:
    if not left: return right
    if not right: return left
    res = left.copy()
    res.update(right)
    return res

# ==============================================================================
# DOUBLE-LEDGER ARCHITECTURE (Magentic-One Pattern)
# ==============================================================================

class ScoringMetrics(TypedDict):
    """Strictly typed metrics for M2.7 Auto-Improvement tracking."""
    current_score: float
    best_score: float
    last_delta: float
    eval_count: int

class EvaluationRecord(TypedDict):
    """History of evaluation trajectories."""
    step_index: int
    score: float
    action: Literal["CONTINUE", "APPLY", "REVERT", "REPLAN"]
    worker_name: str

class TaskLedger(TypedDict):
    """The Outer Loop (Macro Strategy). Stores long-term memory and alignment."""
    goal: str
    plan: List[str]
    facts: List[str]
    replanning_count: int
    action: Literal["CONTINUE", "APPLY", "REVERT", "REPLAN", "ABORT"]
    metrics: ScoringMetrics
    evaluation_history: List[EvaluationRecord]
    replan_reason: Optional[str]

class ProgressLedger(TypedDict, total=False):
    """The Inner Loop (Micro Execution). Stores transient state and loop breakers."""
    step_index: int
    is_complete: bool
    is_stuck: bool
    stall_count: int        # Critical: Infinite loop breaker
    repair_attempts: int    # For Self-Healing ErrorHandler
    failed_task_hash: str   # For Task Deduplication
    next_speaker: str
    instruction: str
    assignments: List[Dict[str, str]]  # Added for parallel execution
    last_updated_at: str    # ISO 8601 string

# ==============================================================================
# FULL SUPERVISOR STATE
# ==============================================================================
class SupervisorState(TypedDict):
    """The absolute StateGraph definition."""
    task_ledger: Annotated[TaskLedger, merge_dict]
    progress_ledger: Annotated[ProgressLedger, merge_dict]
    current_intent: Annotated[Dict[str, Any], merge_dict]
    simulation_result: Annotated[Dict[str, Any], merge_dict]
    swarm_correlation: Annotated[Dict[str, Any], merge_dict]
    simulation_run_id: str
    simulation_status: str
    
    # Annotated fields use Smart Reducers to safely merge state from parallel nodes
    messages: Annotated[List[BaseMessage], add_messages]
    workers_output: Annotated[List[LLMResult], merge_worker_outputs]
    tokens_used_total: Annotated[int, update_token_count]
