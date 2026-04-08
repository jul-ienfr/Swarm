"""Backward-compatible graph entrypoint.

The actual graph compilation now lives in `runtime_langgraph`.
"""

from runtime_langgraph.graph import compile_graph, get_graph_and_config

__all__ = ["compile_graph", "get_graph_and_config"]
