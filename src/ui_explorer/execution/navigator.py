from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from ui_explorer.core.active_root import resolve_active_root
from ui_explorer.core.actions import UIAction, extract_actions
from ui_explorer.core.a11y_parser import parse_a11y_xml
from ui_explorer.execution.executor import ActionExecutor
from ui_explorer.execution.wait import A11YWaiter, CapturedState
from ui_explorer.graph.models import ExplorationGraph, GraphEdge
from ui_explorer.graph.store import GraphStore


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class NavigationResult:
    ok: bool
    target_state: str
    actual_state: str | None
    attempts: int
    reason: str
    xml_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "target_state": self.target_state,
            "actual_state": self.actual_state,
            "attempts": self.attempts,
            "reason": self.reason,
            "xml_path": self.xml_path,
        }


class Navigator:
    """
    Navigation helpers.

    Supports:
    - reset_to_root via Escape for transient overlays;
    - generic dialog dismissal;
    - generic option-based root normalization for persistent state drift;
    - replay-path navigation for depth > 0.

    The normalizer intentionally avoids app-specific values such as
    "Decimal" or "Programming". It derives candidate reset actions from the
    confirmed graph and verifies success only by comparing state_id with
    graph.root_state_id.
    """

    OPTION_ROLES = frozenset({
        "menu item",
        "radio button",
        "check box",
    })

    DISMISS_ACTION_NAMES = frozenset({
        "cancel",
        "close",
        "dismiss",
        "ok",
        "discard",
        "yes",
    })

    ROOT_OPENER_ROLES = frozenset({
        "combo box",
        "toggle button",
        "push button",
    })

    OVERLAY_KINDS = frozenset({
        "menu",
        "window_overlay",
    })

    def __init__(
        self,
        *,
        a11y_name: str,
        display: str,
        graph_store: GraphStore,
        window_name: str | None = None,
    ) -> None:
        self.a11y_name = a11y_name
        self.display = display
        self.graph_store = graph_store
        self.window_name = window_name or a11y_name

        os.environ["DISPLAY"] = display

        self.waiter = A11YWaiter(
            a11y_name=a11y_name,
            timeout_s=15.0,
            interval_s=0.3,
        )
        self.executor = ActionExecutor(
            display=display,
            window_name=self.window_name,
        )

    def _activate_window(self) -> None:
        """
        Best-effort activation.

        Some menu / popover states ignore Escape or clicks if the application
        window is not focused. Activation failure is not fatal because capture
        may still work.
        """
        try:
            self.executor.activate_window()
            time.sleep(0.12)
        except Exception:
            pass

    @staticmethod
    def _active_actions_from_xml(xml_path: Path) -> list[UIAction]:
        root = parse_a11y_xml(xml_path)
        active = resolve_active_root(root)
        return extract_actions(active.node)

    @staticmethod
    def _option_specs(actions: list[UIAction]) -> list[tuple[str, str]]:
        """
        Return stable option specs as (role, name), preserving order.

        We use name/role instead of bboxes across attempts because opening the
        same control from another persistent state may slightly change layout.
        """
        specs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for action in actions:
            name = action.name.strip()
            if not name:
                continue

            if action.role not in Navigator.OPTION_ROLES:
                continue

            spec = (action.role, name)
            if spec in seen:
                continue

            seen.add(spec)
            specs.append(spec)

        return specs

    @staticmethod
    def _find_action_by_spec(
        actions: list[UIAction],
        spec: tuple[str, str],
    ) -> UIAction | None:
        role, name = spec

        for action in actions:
            if action.role != role:
                continue
            if action.name.strip() != name:
                continue
            return action

        return None

    @staticmethod
    def _find_action_matching_edge(
        actions: list[UIAction],
        edge: GraphEdge,
    ) -> UIAction | None:
        """
        Find the same logical action in the current live state.

        Prefer action_key because it is stable across equivalent states.
        Fallback to role + name + description.
        """
        edge_action = edge.action or {}

        edge_key = (edge_action.get("action_key") or "").strip()
        edge_role = (edge_action.get("role") or "").strip()
        edge_name = (edge_action.get("name") or "").strip()
        edge_description = (edge_action.get("description") or "").strip()

        if edge_key:
            for action in actions:
                if action.action_key == edge_key:
                    return action

        for action in actions:
            if action.role != edge_role:
                continue
            if action.name.strip() != edge_name:
                continue
            if edge_description and action.description.strip() != edge_description:
                continue
            return action

        return None

    def _find_live_action_matching_edge(
        self,
        *,
        state: CapturedState,
        edge: GraphEdge,
    ) -> UIAction | None:
        """
        Find a graph edge's logical action in a captured live state.

        This avoids clicking stale bboxes saved in root/depth-1 states when
        replaying or normalizing from another persistent state.
        """
        try:
            actions = self._active_actions_from_xml(state.xml_path)
        except Exception:
            return None

        return self._find_action_matching_edge(actions, edge)

    @staticmethod
    def _candidate_root_openers(graph: ExplorationGraph) -> list[GraphEdge]:
        """
        Find confirmed root actions that open option-like overlays.

        This is graph-derived and app-agnostic:
        root --combo/toggle/button--> menu/window_overlay
        """
        candidates: list[GraphEdge] = []

        for edge in graph.edges.values():
            if edge.from_state != graph.root_state_id:
                continue
            if edge.status.value != "confirmed":
                continue
            if not edge.to_state:
                continue

            action_role = (edge.action.get("role") or "").strip()
            if action_role not in Navigator.ROOT_OPENER_ROLES:
                continue

            to_node = graph.nodes.get(edge.to_state)
            if to_node is None:
                continue

            active_kind = (to_node.active_root.get("kind") or "").strip()
            if active_kind not in Navigator.OVERLAY_KINDS:
                continue

            candidates.append(edge)

        candidates.sort(
            key=lambda edge: (
                edge.priority,
                edge.created_order,
                edge.edge_id,
            )
        )

        return candidates

    def _click_action_bbox(self, action: UIAction | dict) -> bool:
        if isinstance(action, UIAction):
            bbox = tuple(action.bbox)
        else:
            bbox = tuple(action["bbox"])

        self._activate_window()
        execution = self.executor.click_bbox(bbox)
        return bool(execution.ok)

    def _try_root_opener_options(
        self,
        *,
        graph: ExplorationGraph,
        opener: GraphEdge,
        current_state: CapturedState,
        output_dir: Path,
        opener_index: int,
        max_options: int = 12,
    ) -> tuple[NavigationResult, CapturedState | None]:
        """
        Try one root opener as a generic normalizer.

        Strategy:
        - find the same opener action in the current live state;
        - click its current bbox;
        - inspect opened overlay options;
        - for each option spec:
            reopen the same opener from the latest live state;
            click that option;
            check whether root_state_id is restored.

        No app-specific option names are used.
        """

        output_dir.mkdir(parents=True, exist_ok=True)

        live_opener = self._find_live_action_matching_edge(
            state=current_state,
            edge=opener,
        )

        if live_opener is None:
            return (
                NavigationResult(
                    ok=False,
                    target_state=graph.root_state_id,
                    actual_state=current_state.signature.state_id,
                    attempts=1,
                    reason=f"normalizer live opener not found: {opener.edge_id}",
                    xml_path=str(current_state.xml_path),
                ),
                current_state,
            )

        if not self._click_action_bbox(live_opener):
            return (
                NavigationResult(
                    ok=False,
                    target_state=graph.root_state_id,
                    actual_state=current_state.signature.state_id,
                    attempts=1,
                    reason=f"normalizer live opener click failed: {opener.edge_id}",
                    xml_path=str(current_state.xml_path),
                ),
                current_state,
            )

        opened_state = self.waiter.capture_stable(
            output_dir=output_dir,
            prefix=f"normalizer_{opener_index:02d}_open_initial",
        )

        if opened_state.signature.state_id == graph.root_state_id:
            return (
                NavigationResult(
                    ok=True,
                    target_state=graph.root_state_id,
                    actual_state=opened_state.signature.state_id,
                    attempts=1,
                    reason=f"root reached by opener toggle: {opener.edge_id}",
                    xml_path=str(opened_state.xml_path),
                ),
                opened_state,
            )

        try:
            opened_actions = self._active_actions_from_xml(opened_state.xml_path)
        except Exception as exc:
            return (
                NavigationResult(
                    ok=False,
                    target_state=graph.root_state_id,
                    actual_state=opened_state.signature.state_id,
                    attempts=1,
                    reason=f"normalizer opened-state parse failed: {exc}",
                    xml_path=str(opened_state.xml_path),
                ),
                opened_state,
            )

        option_specs = self._option_specs(opened_actions)
        if not option_specs:
            return (
                NavigationResult(
                    ok=False,
                    target_state=graph.root_state_id,
                    actual_state=opened_state.signature.state_id,
                    attempts=1,
                    reason=f"normalizer found no option actions: {opener.edge_id}",
                    xml_path=str(opened_state.xml_path),
                ),
                opened_state,
            )

        option_specs = option_specs[:max_options]
        latest_state = opened_state
        attempts = 1

        for option_index, option_spec in enumerate(option_specs, start=1):
            live_opener = self._find_live_action_matching_edge(
                state=latest_state,
                edge=opener,
            )

            if live_opener is None:
                latest_state = latest_state
                continue

            if not self._click_action_bbox(live_opener):
                latest_state = latest_state
                continue

            attempts += 1

            reopened_state = self.waiter.capture_stable(
                output_dir=output_dir,
                prefix=(
                    f"normalizer_{opener_index:02d}_"
                    f"option_{option_index:02d}_open"
                ),
            )

            if reopened_state.signature.state_id == graph.root_state_id:
                return (
                    NavigationResult(
                        ok=True,
                        target_state=graph.root_state_id,
                        actual_state=reopened_state.signature.state_id,
                        attempts=attempts,
                        reason=(
                            "root reached while reopening normalizer: "
                            f"{opener.edge_id}"
                        ),
                        xml_path=str(reopened_state.xml_path),
                    ),
                    reopened_state,
                )

            try:
                reopened_actions = self._active_actions_from_xml(
                    reopened_state.xml_path
                )
            except Exception:
                latest_state = reopened_state
                continue

            option_action = self._find_action_by_spec(
                reopened_actions,
                option_spec,
            )

            if option_action is None:
                latest_state = reopened_state
                continue

            if not self._click_action_bbox(option_action):
                latest_state = reopened_state
                continue

            attempts += 1

            selected_state = self.waiter.capture_stable(
                output_dir=output_dir,
                prefix=(
                    f"normalizer_{opener_index:02d}_"
                    f"option_{option_index:02d}_select"
                ),
            )

            latest_state = selected_state

            if selected_state.signature.state_id == graph.root_state_id:
                role, name = option_spec
                return (
                    NavigationResult(
                        ok=True,
                        target_state=graph.root_state_id,
                        actual_state=selected_state.signature.state_id,
                        attempts=attempts,
                        reason=(
                            "root reached via generic option normalization: "
                            f"opener={opener.action.get('name')!r}, "
                            f"option={role}/{name!r}"
                        ),
                        xml_path=str(selected_state.xml_path),
                    ),
                    selected_state,
                )

        return (
            NavigationResult(
                ok=False,
                target_state=graph.root_state_id,
                actual_state=latest_state.signature.state_id,
                attempts=attempts,
                reason=f"normalizer exhausted options for opener: {opener.edge_id}",
                xml_path=str(latest_state.xml_path),
            ),
            latest_state,
        )

    def _normalize_root_by_graph_options(
        self,
        *,
        graph: ExplorationGraph,
        current_state: CapturedState,
        output_dir: Path,
    ) -> tuple[NavigationResult, CapturedState | None]:
        """
        Generic persistent-state normalizer.

        It does not know application-specific target values. It only knows:
        - root_state_id;
        - confirmed root overlay openers from graph;
        - visible option actions in opened overlays.

        Success condition is strict:
            observed state_id == graph.root_state_id
        """

        output_dir.mkdir(parents=True, exist_ok=True)

        openers = self._candidate_root_openers(graph)
        if not openers:
            return (
                NavigationResult(
                    ok=False,
                    target_state=graph.root_state_id,
                    actual_state=current_state.signature.state_id,
                    attempts=0,
                    reason="generic normalizer unavailable: no root overlay openers",
                    xml_path=str(current_state.xml_path),
                ),
                current_state,
            )

        latest_state = current_state
        reasons: list[str] = []

        for opener_index, opener in enumerate(openers, start=1):
            result, state = self._try_root_opener_options(
                graph=graph,
                opener=opener,
                current_state=latest_state,
                output_dir=output_dir / f"opener_{opener_index:02d}",
                opener_index=opener_index,
            )

            if result.ok:
                return result, state

            reasons.append(result.reason)

            if state is not None:
                latest_state = state

        return (
            NavigationResult(
                ok=False,
                target_state=graph.root_state_id,
                actual_state=latest_state.signature.state_id,
                attempts=0,
                reason="generic normalizer failed: " + " | ".join(reasons[-3:]),
                xml_path=str(latest_state.xml_path),
            ),
            latest_state,
        )

    def reset_to_root(
        self,
        root_state_id: str,
        output_dir: Path,
        max_escapes: int = 5,
        delay_s: float = 0.25,
    ) -> tuple[NavigationResult, CapturedState | None]:
        try:
            import pyautogui
        except Exception as exc:
            return (
                NavigationResult(
                    ok=False,
                    target_state=root_state_id,
                    actual_state=None,
                    attempts=0,
                    reason=f"pyautogui import failed: {exc}",
                ),
                None,
            )

        output_dir.mkdir(parents=True, exist_ok=True)

        last_state: CapturedState | None = None

        self._activate_window()

        # We may already be at root.
        state = self.waiter.capture_once(output_dir / "reset_00.xml")

        if state.signature.state_id == root_state_id:
            return (
                NavigationResult(
                    ok=True,
                    target_state=root_state_id,
                    actual_state=state.signature.state_id,
                    attempts=0,
                    reason="already at root",
                    xml_path=str(state.xml_path),
                ),
                state,
            )

        last_state = state

        for attempt in range(1, max_escapes + 1):
            self._activate_window()

            pyautogui.press("escape")
            time.sleep(delay_s)

            # Some GTK menu/popover states need one extra Escape after focus
            # has returned to the application window.
            if attempt >= 2:
                pyautogui.press("escape")
                time.sleep(delay_s)

            state = self.waiter.capture_once(
                output_dir / f"reset_{attempt:02d}.xml"
            )
            last_state = state

            if state.signature.state_id == root_state_id:
                return (
                    NavigationResult(
                        ok=True,
                        target_state=root_state_id,
                        actual_state=state.signature.state_id,
                        attempts=attempt,
                        reason="root reached via focused Escape",
                        xml_path=str(state.xml_path),
                    ),
                    state,
                )

        return (
            NavigationResult(
                ok=False,
                target_state=root_state_id,
                actual_state=(
                    last_state.signature.state_id
                    if last_state
                    else None
                ),
                attempts=max_escapes,
                reason="root not reached after Escape attempts",
                xml_path=(
                    str(last_state.xml_path)
                    if last_state
                    else None
                ),
            ),
            last_state,
        )

    def _try_dismiss_dialog(
        self,
        *,
        current_state: CapturedState,
        output_dir: Path,
    ) -> CapturedState | None:
        """
        Generic modal/dialog/alert dismissal.

        This is mostly app-agnostic. It tries common safe dialog actions:
        Cancel / Close / Dismiss / OK, plus LibreOffice recovery flow:
        Discard -> Question alert -> Yes.
        """

        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            actions = self._active_actions_from_xml(current_state.xml_path)
        except Exception:
            return None

        candidates: list[UIAction] = []

        for action in actions:
            name = action.name.strip().lower()
            if not name:
                continue

            if name not in self.DISMISS_ACTION_NAMES:
                continue

            if action.role not in {
                "push button",
                "toggle button",
                "menu item",
            }:
                continue

            candidates.append(action)

        if not candidates:
            try:
                import pyautogui
            except Exception:
                return None

            self._activate_window()

            # Fallback for startup dialogs such as LibreOffice Tip of the Day.
            for index, key in enumerate(["escape", "escape"], start=1):
                pyautogui.press(key)
                time.sleep(0.35)

                state = self.waiter.capture_stable(
                    output_dir=output_dir,
                    prefix=f"dismiss_dialog_key_{index:02d}",
                )

                active = state.signature.active_root
                if active.get("kind") not in {"dialog", "alert"}:
                    return state

            return None

        def _dismiss_priority(action: UIAction) -> tuple[int, int, str]:
            name = action.name.strip().lower()

            if name in {"cancel", "close", "dismiss"}:
                return (0, action.depth, action.name)

            if name == "discard":
                return (1, action.depth, action.name)

            if name in {"yes", "ok"}:
                return (2, action.depth, action.name)

            return (9, action.depth, action.name)

        candidates.sort(key=_dismiss_priority)

        for index, action in enumerate(candidates, start=1):
            if not self._click_action_bbox(action):
                continue

            return self.waiter.capture_stable(
                output_dir=output_dir,
                prefix=f"dismiss_dialog_{index:02d}",
            )

        return None

    def _dismiss_priority(action: UIAction) -> tuple[int, int, str]:
        name = action.name.strip().lower()

        if name in {"cancel", "close", "dismiss"}:
            return (0, action.depth, action.name)

        if name == "discard":
            return (1, action.depth, action.name)

        if name in {"yes", "ok"}:
            return (2, action.depth, action.name)

        return (9, action.depth, action.name)

        for index, action in enumerate(candidates, start=1):
            if not self._click_action_bbox(action):
                continue

            return self.waiter.capture_stable(
                output_dir=output_dir,
                prefix=f"dismiss_dialog_{index:02d}",
            )

        return None

    def navigate_to_state(
        self,
        *,
        graph: ExplorationGraph,
        target_state_id: str,
        output_dir: Path,
    ) -> tuple[NavigationResult, CapturedState | None]:
        """
        Reset app to root and replay confirmed path to target_state_id.
        """

        output_dir.mkdir(parents=True, exist_ok=True)

        # Fast path before reset:
        # if current live state is already the requested target, use it.
        current_state = self.waiter.capture_once(output_dir / "before_navigation.xml")
        current_id = current_state.signature.state_id

        log.debug(
            "navigate_to_state initial: target=%s root=%s current=%s",
            target_state_id,
            graph.root_state_id,
            current_id,
        )

        if current_id == target_state_id:
            return (
                NavigationResult(
                    ok=True,
                    target_state=target_state_id,
                    actual_state=current_id,
                    attempts=0,
                    reason=(
                        "target state already active before reset: "
                        f"target={target_state_id}"
                    ),
                    xml_path=str(current_state.xml_path),
                ),
                current_state,
            )

        reset_result, current_state = self.reset_to_root(
            root_state_id=graph.root_state_id,
            output_dir=output_dir / "reset",
        )

        current_id = (
            current_state.signature.state_id
            if current_state is not None
            else None
        )

        log.debug(
            "navigate_to_state after reset: target=%s root=%s current=%s reset_ok=%s",
            target_state_id,
            graph.root_state_id,
            current_id,
            reset_result.ok,
        )

        if current_id == target_state_id:
            return (
                NavigationResult(
                    ok=True,
                    target_state=target_state_id,
                    actual_state=current_id,
                    attempts=reset_result.attempts,
                    reason=(
                        "target state already active after reset attempts: "
                        f"target={target_state_id}"
                    ),
                    xml_path=(
                        str(current_state.xml_path)
                        if current_state is not None
                        else None
                    ),
                ),
                current_state,
            )

        if not reset_result.ok and current_state is not None:
            for dismiss_index in range(1, 4):
                dismissed_state = self._try_dismiss_dialog(
                    current_state=current_state,
                    output_dir=output_dir / f"dismiss_dialog_{dismiss_index:02d}",
                )

                if dismissed_state is None:
                    break

                current_state = dismissed_state
                current_id = current_state.signature.state_id

                log.debug(
                    "navigate_to_state after dialog dismiss %s: target=%s root=%s current=%s",
                    dismiss_index,
                    target_state_id,
                    graph.root_state_id,
                    current_id,
                )

                if current_id == target_state_id:
                    return (
                        NavigationResult(
                            ok=True,
                            target_state=target_state_id,
                            actual_state=current_id,
                            attempts=reset_result.attempts + dismiss_index,
                            reason=(
                                "target state reached after generic dialog dismiss: "
                                f"target={target_state_id}"
                            ),
                            xml_path=str(current_state.xml_path),
                        ),
                        current_state,
                    )

                if current_id == graph.root_state_id:
                    reset_result = NavigationResult(
                        ok=True,
                        target_state=graph.root_state_id,
                        actual_state=current_id,
                        attempts=reset_result.attempts + dismiss_index,
                        reason="root reached after generic dialog dismiss",
                        xml_path=str(current_state.xml_path),
                    )
                    break

                if current_state.signature.active_root.get("kind") not in {"dialog", "alert"}:
                    break

        if not reset_result.ok and current_state is not None:
            normalize_result, normalized_state = self._normalize_root_by_graph_options(
                graph=graph,
                current_state=current_state,
                output_dir=output_dir / "normalize",
            )

            if normalize_result.ok:
                reset_result = normalize_result
                current_state = normalized_state
                current_id = (
                    current_state.signature.state_id
                    if current_state is not None
                    else None
                )

        if not reset_result.ok or current_state is None:
            current_id = (
                current_state.signature.state_id
                if current_state is not None
                else reset_result.actual_state
            )

            return (
                NavigationResult(
                    ok=False,
                    target_state=target_state_id,
                    actual_state=current_id,
                    attempts=reset_result.attempts,
                    reason=(
                        "navigation failed before replay: "
                        f"reset_target={graph.root_state_id}; "
                        f"requested_target={target_state_id}; "
                        f"reset_reason={reset_result.reason}"
                    ),
                    xml_path=(
                        str(current_state.xml_path)
                        if current_state is not None
                        else reset_result.xml_path
                    ),
                ),
                current_state,
            )

        if target_state_id == graph.root_state_id:
            return (
                NavigationResult(
                    ok=True,
                    target_state=target_state_id,
                    actual_state=current_state.signature.state_id,
                    attempts=reset_result.attempts,
                    reason=reset_result.reason,
                    xml_path=str(current_state.xml_path),
                ),
                current_state,
            )

        path = self.graph_store.find_confirmed_path(
            graph=graph,
            target_state_id=target_state_id,
        )

        if path is None:
            return (
                NavigationResult(
                    ok=False,
                    target_state=target_state_id,
                    actual_state=current_state.signature.state_id,
                    attempts=0,
                    reason="confirmed path not found",
                    xml_path=str(current_state.xml_path),
                ),
                current_state,
            )

        for step_index, edge in enumerate(path, start=1):
            self._activate_window()

            live_action = self._find_live_action_matching_edge(
                state=current_state,
                edge=edge,
            )

            if live_action is None:
                return (
                    NavigationResult(
                        ok=False,
                        target_state=target_state_id,
                        actual_state=current_state.signature.state_id,
                        attempts=step_index,
                        reason=f"replay live action not found at edge {edge.edge_id}",
                        xml_path=str(current_state.xml_path),
                    ),
                    current_state,
                )

            execution = self.executor.click_bbox(tuple(live_action.bbox))

            if not execution.ok:
                return (
                    NavigationResult(
                        ok=False,
                        target_state=target_state_id,
                        actual_state=current_state.signature.state_id,
                        attempts=step_index,
                        reason=(
                            f"replay click failed at edge {edge.edge_id}: "
                            f"{execution.error}"
                        ),
                        xml_path=str(current_state.xml_path),
                    ),
                    current_state,
                )

            current_state = self.waiter.capture_stable(
                output_dir=output_dir,
                prefix=f"replay_{step_index:02d}",
            )

            expected_state = edge.to_state

            if (
                expected_state
                and current_state.signature.state_id != expected_state
            ):
                return (
                    NavigationResult(
                        ok=False,
                        target_state=target_state_id,
                        actual_state=current_state.signature.state_id,
                        attempts=step_index,
                        reason=(
                            "replay state mismatch: "
                            f"expected={expected_state} "
                            f"actual={current_state.signature.state_id}"
                        ),
                        xml_path=str(current_state.xml_path),
                    ),
                    current_state,
                )

        return (
            NavigationResult(
                ok=True,
                target_state=target_state_id,
                actual_state=current_state.signature.state_id,
                attempts=len(path),
                reason="target state reached",
                xml_path=str(current_state.xml_path),
            ),
            current_state,
        )
