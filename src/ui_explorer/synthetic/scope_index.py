from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ui_explorer.synthetic.io import load_json
from ui_explorer.synthetic.paths import AGENT_MAP_PATH, SCOPE_MAP_PATH, resolve_repo_path


@dataclass(frozen=True)
class MicroActionRef:
    state_id: str
    micro_action: dict[str, Any]


class ScopeIndex:
    def __init__(
        self,
        *,
        scope_map: dict[str, Any],
        agent_map: dict[str, Any],
        repo_root: Path,
    ) -> None:
        self.scope_map = scope_map
        self.agent_map = agent_map
        self.agent_states = agent_map.get("states", {})
        self.repo_root = repo_root
        self._by_action_key: dict[str, MicroActionRef] = {}
        self._build_action_index()

    @classmethod
    def load(
        cls,
        *,
        scope_map_path: Path | None = None,
        agent_map_path: Path | None = None,
        repo_root: Path | None = None,
    ) -> ScopeIndex:
        root = repo_root or resolve_repo_path(Path("."))
        scope_path = resolve_repo_path(scope_map_path or SCOPE_MAP_PATH)
        agent_path = resolve_repo_path(agent_map_path or AGENT_MAP_PATH)
        return cls(
            scope_map=load_json(scope_path),
            agent_map=load_json(agent_path),
            repo_root=root,
        )

    def _build_action_index(self) -> None:
        for state_id, scope_state in self.scope_map.get("states", {}).items():
            for micro_action in scope_state.get("active_root_micro_actions", []):
                action_key = micro_action["action_key"]
                self._by_action_key[action_key] = MicroActionRef(
                    state_id=state_id,
                    micro_action=micro_action,
                )

    def states_with_microactions(self) -> list[tuple[str, dict[str, Any]]]:
        items: list[tuple[str, dict[str, Any]]] = []
        for state_id, scope_state in sorted(self.scope_map.get("states", {}).items()):
            if scope_state.get("active_root_micro_actions"):
                items.append((state_id, scope_state))
        return items

    def get_scope_state(self, state_id: str) -> dict[str, Any]:
        state = self.scope_map.get("states", {}).get(state_id)
        if state is None:
            raise KeyError(f"unknown macro state id: {state_id}")
        return state

    def get_micro_action_ref(self, action_key: str) -> MicroActionRef:
        ref = self._by_action_key.get(action_key)
        if ref is None:
            raise KeyError(f"unknown micro_action_id: {action_key}")
        return ref

    def build_macro_path(self, state_id: str) -> list[str]:
        path: list[str] = []
        current_id = state_id
        seen: set[str] = set()

        while current_id and current_id not in seen:
            seen.add(current_id)
            state = self.agent_states.get(current_id)
            if state is None:
                break

            label = (state.get("label") or current_id).strip()
            if label:
                path.append(label)

            incoming = state.get("primary_incoming_action")
            if not incoming:
                break

            next_id = incoming.get("from_state")
            if not next_id or next_id == current_id:
                break
            current_id = next_id

        path.reverse()
        return path

    def build_slim_macro_context(self, state_id: str) -> dict[str, str]:
        macro_path = self.build_macro_path(state_id)
        agent_state = self.agent_states.get(state_id, {})
        label = (agent_state.get("label") or state_id).strip()
        path_text = " → ".join(macro_path) if macro_path else label
        return {"macro_path_text": path_text}

    def build_slim_active_root_line(self, scope_state: dict[str, Any]) -> str:
        active = scope_state.get("recomputed_active_root") or scope_state.get("graph_active_root") or {}
        kind = active.get("kind")
        if kind in {None, "", "main"}:
            return ""
        name = active.get("name") or active.get("role") or kind
        return f"- active_ui_layer: {kind} ({name})"

    def build_macro_context(self, state_id: str) -> dict[str, Any]:
        agent_state = {**self.agent_states.get(state_id, {}), "state_id": state_id}
        macro_path = self.build_macro_path(state_id)
        return {
            "state_id": agent_state.get("state_id"),
            "label": agent_state.get("label"),
            "depth": agent_state.get("depth"),
            "macro_path": macro_path,
            "macro_path_text": " → ".join(macro_path) if macro_path else agent_state.get("label"),
            "primary_incoming_action": agent_state.get("primary_incoming_action"),
            "incoming_actions": agent_state.get("incoming_actions", []),
            "verified_actions": agent_state.get("verified_actions", []),
            "scoped_observed_confidence": agent_state.get("scoped_observed_confidence"),
            "state_capabilities_count": len(agent_state.get("state_capabilities", [])),
        }

    def build_active_root_context(self, scope_state: dict[str, Any]) -> dict[str, Any]:
        active = scope_state.get("recomputed_active_root") or scope_state.get("graph_active_root") or {}
        local_names = [
            action.get("name")
            for action in scope_state.get("active_root_actions", [])
            if action.get("name")
        ]
        return {
            "kind": active.get("kind"),
            "role": active.get("role"),
            "name": active.get("name"),
            "reason": active.get("reason"),
            "parent_path": active.get("parent_path", []),
            "local_action_names": local_names,
            "local_action_count": len(local_names),
            "active_root_matches_graph": scope_state.get("active_root_matches_graph"),
        }

    def resolve_screenshot_path(self, scope_state: dict[str, Any]) -> str | None:
        artifacts = scope_state.get("artifacts") or {}
        screenshot = artifacts.get("screenshot")
        if not screenshot:
            return None
        path = Path(screenshot)
        if not path.is_absolute():
            path = self.repo_root / path
        return str(path) if path.exists() else str(path)

    def microactions_for_prompt(self, scope_state: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "micro_action_id": action["action_key"],
                "role": action.get("role"),
                "name": action.get("name"),
                "description": action.get("description"),
                "bbox": action.get("bbox"),
                "is_showing": action.get("is_showing"),
                "is_enabled": action.get("is_enabled"),
                "is_sensitive": action.get("is_sensitive"),
                "reason": action.get("reason"),
            }
            for action in scope_state.get("active_root_micro_actions", [])
        ]

    def expected_action_keys(self, scope_state: dict[str, Any]) -> set[str]:
        return {
            action["action_key"]
            for action in scope_state.get("active_root_micro_actions", [])
        }


def render_prompt(template: str, replacements: dict[str, str]) -> str:
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered


PROMPT_PROFILE_TEMPLATES = {
    "task": {
        "default": "generate_tasks.md",
        "slim": "generate_tasks_slim.md",
    },
    "goal": {
        "default": "generate_goals.md",
        "slim": "generate_goals_slim.md",
    },
}


def load_prompt_template(name: str) -> str:
    from ui_explorer.synthetic.paths import PROMPTS_DIR

    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8")


def load_prompt_template_for_profile(
    profile: str,
    *,
    prompt_kind: str = "task",
) -> str:
    kind_templates = PROMPT_PROFILE_TEMPLATES.get(prompt_kind)
    if kind_templates is None:
        valid = ", ".join(sorted(PROMPT_PROFILE_TEMPLATES))
        raise ValueError(f"unknown prompt kind {prompt_kind!r}; expected one of: {valid}")
    template_name = kind_templates.get(profile)
    if template_name is None:
        valid = ", ".join(sorted(kind_templates))
        raise ValueError(f"unknown prompt profile {profile!r}; expected one of: {valid}")
    return load_prompt_template(template_name)
