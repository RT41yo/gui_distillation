from __future__ import annotations

import json
import shutil
from pathlib import Path

from ui_explorer.core.action_policy import ActionKind, classify_actions
from ui_explorer.core.actions import extract_actions
from ui_explorer.core.a11y_parser import A11YNode
from ui_explorer.core.state import StateSignature, compute_state_signature
from ui_explorer.graph.models import (
    EdgeStatus,
    ExplorationGraph,
    GraphEdge,
    NodeStatus,
    StateNode,
    edge_id,
    state_dir,
)


class GraphStore:
    def __init__(self, base_dir: Path = Path("data/maps")) -> None:
        self.base_dir = base_dir

    def graph_path(self, app_id: str) -> Path:
        return self.base_dir / app_id / "graph.json"

    def save(self, graph: ExplorationGraph) -> Path:
        path = self.graph_path(graph.app_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._refresh_completion(graph)
        path.write_text(json.dumps(graph.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def load(self, app_id: str) -> ExplorationGraph:
        path = self.graph_path(app_id)
        return ExplorationGraph.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def init_from_xml(self, app_id: str, xml_path: Path) -> ExplorationGraph:
        root = self._parse(xml_path)
        sig = compute_state_signature(root)

        dst_dir = state_dir(self.base_dir, app_id, sig.state_id)
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst_xml = dst_dir / "a11y.xml"
        shutil.copy2(xml_path, dst_xml)

        node = self._node_from_signature(sig=sig, xml_path=dst_xml, depth=0)

        graph = ExplorationGraph(app_id=app_id, root_state_id=sig.state_id)
        graph.nodes[node.state_id] = node

        self.seed_pending_edges(graph=graph, state_id=node.state_id, root=root)

        self.save(graph)
        return graph

    def seed_pending_edges(
        self,
        graph: ExplorationGraph,
        state_id: str,
        root: A11YNode,
    ) -> int:
        actions = extract_actions(root)
        classified = classify_actions(actions)

        created = 0
        next_order = self._next_created_order(graph)

        for item in classified:
            if item.kind != ActionKind.MACRO:
                continue

            eid = edge_id(state_id, item.action.action_key)
            if eid in graph.edges:
                continue

            graph.edges[eid] = GraphEdge(
                edge_id=eid,
                from_state=state_id,
                action_key=item.action.action_key,
                action=item.action.to_dict(),
                status=EdgeStatus.PENDING,
                priority=item.priority,
                reason=item.reason,
                created_order=next_order,
            )
            next_order += 1
            created += 1

        return created

    def _node_from_signature(self, sig: StateSignature, xml_path: Path, depth: int) -> StateNode:
        return StateNode(
            state_id=sig.state_id,
            status=NodeStatus.CONFIRMED,
            xml_path=str(xml_path),
            active_root=sig.active_root,
            macro_hash=sig.macro_hash,
            content_hash=sig.content_hash,
            macro_action_count=sig.macro_action_count,
            visible_node_count=sig.visible_node_count,
            depth=depth,
            label=sig.active_root.get("name") or sig.active_root.get("role"),
        )

    @staticmethod
    def _parse(xml_path: Path) -> A11YNode:
        from ui_explorer.core.a11y_parser import parse_a11y_xml
        return parse_a11y_xml(xml_path)

    @staticmethod
    def _next_created_order(graph: ExplorationGraph) -> int:
        if not graph.edges:
            return 0
        return max(edge.created_order for edge in graph.edges.values()) + 1

    @staticmethod
    def _refresh_completion(graph: ExplorationGraph) -> None:
        pending = sum(1 for edge in graph.edges.values() if edge.status == EdgeStatus.PENDING)
        graph.completion = {
            "status": "complete" if pending == 0 else "partial",
            "pending_edges": pending,
            "reason": "no_pending_edges" if pending == 0 else "pending_edges_exist",
        }
