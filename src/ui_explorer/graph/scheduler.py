from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ui_explorer.graph.models import EdgeStatus, ExplorationGraph, GraphEdge


@dataclass(frozen=True)
class SchedulerPolicy:
    max_depth: int = 5


class BFSScheduler:
    """
    Strict BFS scheduler.

    Ordering:
      1. from_state.depth ASC
      2. edge.priority ASC
      3. edge.attempts ASC
      4. edge.created_order ASC
    """

    def __init__(self, policy: SchedulerPolicy | None = None) -> None:
        self.policy = policy or SchedulerPolicy()

    def next_edge(self, graph: ExplorationGraph) -> Optional[GraphEdge]:
        candidates: list[GraphEdge] = []

        for edge in graph.edges.values():
            if edge.status != EdgeStatus.PENDING:
                continue

            from_node = graph.nodes.get(edge.from_state)
            if from_node is None:
                continue

            if from_node.depth > self.policy.max_depth:
                continue

            candidates.append(edge)

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda edge: (
                graph.nodes[edge.from_state].depth,
                edge.priority,
                edge.attempts,
                edge.created_order,
            ),
        )
