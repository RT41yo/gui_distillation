from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

INT32_MIN = -2147483648


@dataclass(frozen=True)
class BBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def is_visible(self) -> bool:
        return self.x >= 0 and self.y >= 0 and self.width > 1 and self.height > 1

    def as_list(self) -> list[int]:
        return [self.x, self.y, self.width, self.height]


@dataclass(frozen=True)
class A11YNode:
    role: str
    name: str
    description: str
    states: tuple[str, ...]
    bbox: BBox
    parent_path: tuple[str, ...]
    depth: int
    index: int
    children: tuple["A11YNode", ...] = field(default_factory=tuple)

    @property
    def is_visible(self) -> bool:
        return self.bbox.is_visible

    @property
    def label(self) -> str:
        return f"{self.role}/{self.name}" if self.name else self.role


def _parse_int(value: Optional[str], default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _parse_states(value: Optional[str]) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(s.strip() for s in value.split(",") if s.strip())


def _node_from_element(
    elem: ET.Element,
    parent_path: tuple[str, ...],
    depth: int,
    index: int,
) -> A11YNode:
    role = (elem.get("role") or "unknown").strip().lower()
    name = (elem.get("name") or "").strip()
    description = (elem.get("description") or "").strip()
    states = _parse_states(elem.get("states"))

    bbox = BBox(
        x=_parse_int(elem.get("x"), INT32_MIN),
        y=_parse_int(elem.get("y"), INT32_MIN),
        width=_parse_int(elem.get("width"), 0),
        height=_parse_int(elem.get("height"), 0),
    )

    label = f"{role}/{name}" if name else role
    child_parent_path = parent_path + (label,)

    children: list[A11YNode] = []
    child_index = 0
    for child in elem:
        if child.tag != "element":
            continue
        children.append(
            _node_from_element(
                child,
                parent_path=child_parent_path,
                depth=depth + 1,
                index=child_index,
            )
        )
        child_index += 1

    return A11YNode(
        role=role,
        name=name,
        description=description,
        states=states,
        bbox=bbox,
        parent_path=parent_path,
        depth=depth,
        index=index,
        children=tuple(children),
    )


def parse_a11y_xml(xml_path: Path) -> A11YNode:
    root = ET.parse(xml_path).getroot()
    first = root.find("element")
    if first is None:
        raise ValueError(f"No <element> root found in {xml_path}")
    return _node_from_element(first, parent_path=(), depth=0, index=0)


def walk(node: A11YNode) -> Iterable[A11YNode]:
    yield node
    for child in node.children:
        yield from walk(child)


def visible_nodes(root: A11YNode) -> list[A11YNode]:
    return [node for node in walk(root) if node.is_visible]


def hidden_nodes(root: A11YNode) -> list[A11YNode]:
    return [node for node in walk(root) if not node.is_visible]


def role_counts(nodes: Iterable[A11YNode]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node in nodes:
        counts[node.role] = counts.get(node.role, 0) + 1
    return dict(sorted(counts.items()))
