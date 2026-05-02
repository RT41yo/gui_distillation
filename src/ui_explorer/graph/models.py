from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class NodeStatus(str, Enum):
    CONFIRMED = "confirmed"


class EdgeStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SAME_STATE = "same_state"
    CONTENT_CHANGED = "content_changed"
    FOCUS_CHANGED = "focus_changed"
    SELECTION_CHANGED = "selection_changed"
    FAILED_CLICK = "failed_click"
    FAILED_NAVIGATION = "failed_navigation"
    BLOCKED_BY_MODAL = "blocked_by_modal"
    SKIPPED_POLICY = "skipped_policy"
    SKIPPED_DEPTH = "skipped_depth"
    EXTERNAL = "external"
    REQUIRES_INPUT = "requires_input"


@dataclass
class StateNode:
    state_id: str
    status: NodeStatus
    xml_path: str
    active_root: dict[str, Any]
    macro_hash: str
    content_hash: str
    macro_action_count: int
    visible_node_count: int
    depth: int = 0
    label: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "status": self.status.value,
            "xml_path": self.xml_path,
            "active_root": self.active_root,
            "macro_hash": self.macro_hash,
            "content_hash": self.content_hash,
            "macro_action_count": self.macro_action_count,
            "visible_node_count": self.visible_node_count,
            "depth": self.depth,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StateNode":
        return cls(
            state_id=data["state_id"],
            status=NodeStatus(data["status"]),
            xml_path=data["xml_path"],
            active_root=data["active_root"],
            macro_hash=data["macro_hash"],
            content_hash=data["content_hash"],
            macro_action_count=int(data["macro_action_count"]),
            visible_node_count=int(data["visible_node_count"]),
            depth=int(data.get("depth", 0)),
            label=data.get("label"),
        )


@dataclass
class GraphEdge:
    edge_id: str
    from_state: str
    action_key: str
    action: dict[str, Any]
    status: EdgeStatus = EdgeStatus.PENDING
    to_state: Optional[str] = None
    priority: int = 50
    attempts: int = 0
    reason: str = ""
    observed: Optional[dict[str, Any]] = None
    created_order: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "from_state": self.from_state,
            "action_key": self.action_key,
            "action": self.action,
            "status": self.status.value,
            "to_state": self.to_state,
            "priority": self.priority,
            "attempts": self.attempts,
            "reason": self.reason,
            "observed": self.observed,
            "created_order": self.created_order,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphEdge":
        return cls(
            edge_id=data["edge_id"],
            from_state=data["from_state"],
            action_key=data["action_key"],
            action=data["action"],
            status=EdgeStatus(data["status"]),
            to_state=data.get("to_state"),
            priority=int(data.get("priority", 50)),
            attempts=int(data.get("attempts", 0)),
            reason=data.get("reason", ""),
            observed=data.get("observed"),
            created_order=int(data.get("created_order", 0)),
        )


@dataclass
class ExplorationGraph:
    app_id: str
    root_state_id: str
    nodes: dict[str, StateNode] = field(default_factory=dict)
    edges: dict[str, GraphEdge] = field(default_factory=dict)
    completion: dict[str, Any] = field(default_factory=lambda: {
        "status": "partial",
        "pending_edges": 0,
        "reason": "initialized",
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "app_id": self.app_id,
            "root_state_id": self.root_state_id,
            "nodes": {k: v.to_dict() for k, v in sorted(self.nodes.items())},
            "edges": {
                k: v.to_dict()
                for k, v in sorted(self.edges.items(), key=lambda item: item[1].created_order)
            },
            "completion": self.completion,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExplorationGraph":
        return cls(
            app_id=data["app_id"],
            root_state_id=data["root_state_id"],
            nodes={k: StateNode.from_dict(v) for k, v in data.get("nodes", {}).items()},
            edges={k: GraphEdge.from_dict(v) for k, v in data.get("edges", {}).items()},
            completion=data.get("completion", {}),
        )


def edge_id(from_state: str, action_key: str) -> str:
    return f"{from_state}:{action_key}"


def state_dir(base_dir: Path, app_id: str, state_id: str) -> Path:
    return base_dir / app_id / "states" / state_id
