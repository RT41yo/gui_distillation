from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_agent_map(app: str, maps_dir: Path) -> dict[str, Any]:
    path = maps_dir / app / "agent_map.json"

    if not path.exists():
        raise FileNotFoundError(
            f"agent_map.json not found: {path}. "
            f"Run: python -m ui_explorer.cli.build_agent_map --app {app}"
        )

    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_observed_item(
    agent_map: dict[str, Any],
    item_or_ref: dict[str, Any],
) -> dict[str, Any]:
    if "ref" not in item_or_ref:
        return dict(item_or_ref)

    ref = item_or_ref["ref"]
    full_item = dict(agent_map.get("items", {}).get(ref, {}))

    full_item.setdefault("item_id", ref)
    full_item.setdefault("role", item_or_ref.get("role", ""))
    full_item.setdefault("name", item_or_ref.get("name", ""))
    full_item.setdefault("description", item_or_ref.get("description", ""))

    return full_item


def _item_search_fields(item: dict[str, Any]) -> list[str]:
    statuses = item.get("statuses", [])
    if isinstance(statuses, str):
        statuses = [statuses]

    status = item.get("status")
    if status and status not in statuses:
        statuses = list(statuses) + [status]

    return [
        str(item.get("name", "")),
        str(item.get("role", "")),
        str(item.get("description", "")),
        str(item.get("kind", "")),
        " ".join(str(x) for x in statuses),
        " ".join(str(x) for x in item.get("parent_path_tail", [])),
    ]


def _matches_query(
    item: dict[str, Any],
    query: str,
    *,
    exact: bool = False,
) -> bool:
    query_norm = query.casefold().strip()
    fields = _item_search_fields(item)

    if exact:
        return any(
            query_norm == field.casefold().strip()
            for field in fields
            if field
        )

    return query_norm in " ".join(fields).casefold()


def _find_in_item_index(
    agent_map: dict[str, Any],
    query: str,
    *,
    exact: bool,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []

    for item_id, item in agent_map.get("item_index", {}).items():
        if not _matches_query(item, query, exact=exact):
            continue

        matches.append({
            "item_id": item_id,
            "name": item.get("name"),
            "role": item.get("role"),
            "occurrences": item.get("occurrences", 0),
            "verified_action_count": item.get("verified_action_count", 0),
            "observed_item_count": item.get("observed_item_count", 0),
            "statuses": item.get("statuses", []),
            "state_count": len(item.get("states", [])),
            "states_preview": item.get("states", [])[:10],
        })

    matches.sort(
        key=lambda item: (
            -int(item.get("verified_action_count") or 0),
            -int(item.get("observed_item_count") or 0),
            str(item.get("name") or "").casefold(),
            str(item.get("role") or "").casefold(),
        )
    )

    return matches


def _find_state_details(
    agent_map: dict[str, Any],
    query: str,
    *,
    exact: bool,
    limit: int,
) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []

    for state_id, state in agent_map.get("states", {}).items():
        search_sections = [
            ("verified_actions", state.get("verified_actions", []), False),
            ("state_capabilities", state.get("state_capabilities", []), False),
            ("scoped_observed_items", state.get("scoped_observed_items", []), True),
            ("observed_items", state.get("observed_items", []), True),
            ("delta_observed_items", state.get("delta_observed_items", []), True),
        ]

        for section, raw_items, resolve_refs in search_sections:
            for item_or_ref in raw_items:
                item = (
                    _resolve_observed_item(agent_map, item_or_ref)
                    if resolve_refs
                    else dict(item_or_ref)
                )

                if not _matches_query(item, query, exact=exact):
                    continue

                details.append({
                    "state_id": state_id,
                    "state_depth": state.get("depth"),
                    "state_label": state.get("label"),
                    "active_root": state.get("active_root"),
                    "section": section,
                    "item": item,
                })

                if len(details) >= limit:
                    return details

    return details


def _verified_action_preview(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "edge_id": item.get("edge_id"),
        "role": item.get("role"),
        "name": item.get("name"),
        "description": item.get("description"),
        "status": item.get("status"),
        "method": item.get("method"),
        "has_bbox": "bbox" in item,
        "to_state": item.get("to_state"),
    }


def _incoming_action_preview(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if item is None:
        return None

    return {
        "from_state": item.get("from_state"),
        "from_depth": item.get("from_depth"),
        "edge_id": item.get("edge_id"),
        "role": item.get("role"),
        "name": item.get("name"),
        "description": item.get("description"),
        "edge_status": item.get("edge_status"),
        "method": item.get("method"),
        "has_bbox": "bbox" in item,
        "created_order": item.get("created_order"),
    }


def _observed_item_preview(item: dict[str, Any]) -> dict[str, Any]:
    preview = {
        "item_id": item.get("item_id"),
        "role": item.get("role"),
        "name": item.get("name"),
        "description": item.get("description"),
        "status": item.get("status"),
        "states": item.get("states"),
        "parent_path_tail": item.get("parent_path_tail"),
    }

    if "visible_bbox_hint" in item:
        preview["has_visible_bbox_hint"] = True

    return preview


def _capability_preview(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": item.get("kind"),
        "ref": item.get("ref"),
        "edge_id": item.get("edge_id"),
        "role": item.get("role"),
        "name": item.get("name"),
        "description": item.get("description"),
        "status": item.get("status"),
        "edge_status": item.get("edge_status"),
        "to_state": item.get("to_state"),
        "method": item.get("method"),
        "has_bbox": item.get("has_bbox", "bbox" in item),
    }


def _resolved_preview_list(
    agent_map: dict[str, Any],
    refs: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    return [
        _observed_item_preview(_resolve_observed_item(agent_map, item))
        for item in refs[:limit]
    ]


def _state_summary(
    agent_map: dict[str, Any],
    state_id: str,
    *,
    limit: int = 20,
) -> dict[str, Any]:
    states = agent_map.get("states", {})
    state = states.get(state_id)

    if state is None:
        return {
            "ok": False,
            "error": f"state not found: {state_id}",
        }

    verified = state.get("verified_actions", [])
    incoming = state.get("incoming_actions", [])
    primary_incoming = state.get("primary_incoming_action")
    observed_refs = state.get("observed_items", [])
    scoped_refs = state.get("scoped_observed_items", [])
    delta_refs = state.get("delta_observed_items", [])
    capabilities = state.get("state_capabilities", [])

    return {
        "ok": True,
        "state_id": state_id,
        "label": state.get("label"),
        "depth": state.get("depth"),
        "active_root": state.get("active_root"),
        "primary_incoming_action": _incoming_action_preview(primary_incoming),
        "incoming_actions": [
            _incoming_action_preview(item)
            for item in incoming
        ],
        "incoming_actions_total": len(incoming),
        "verified_actions": [
            _verified_action_preview(item)
            for item in verified
        ],
        "state_capabilities_preview": [
            _capability_preview(item)
            for item in capabilities[:limit]
        ],
        "state_capabilities_total": len(capabilities),
        "state_capabilities_source": state.get("state_capabilities_source"),
        "scoped_observed_items_preview": _resolved_preview_list(
            agent_map,
            scoped_refs,
            limit=limit,
        ),
        "scoped_observed_items_total": len(scoped_refs),
        "scoped_observed_source": state.get("scoped_observed_source"),
        "scoped_observed_confidence": state.get("scoped_observed_confidence"),
        "observed_items_preview": _resolved_preview_list(
            agent_map,
            observed_refs,
            limit=limit,
        ),
        "observed_items_total": len(observed_refs),
        "delta_base_state": state.get("delta_base_state"),
        "delta_observed_items_preview": _resolved_preview_list(
            agent_map,
            delta_refs,
            limit=limit,
        ),
        "delta_observed_items_total": len(delta_refs),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect compact agent-facing UI map."
    )

    parser.add_argument("--app", required=True)
    parser.add_argument("--maps", default="data/maps")
    parser.add_argument("--query", "-q", default=None)
    parser.add_argument("--exact", action="store_true")
    parser.add_argument("--state", default=None)
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--limit", type=int, default=20)

    args = parser.parse_args()

    try:
        agent_map = _load_agent_map(args.app, Path(args.maps))
    except Exception as exc:
        print(json.dumps({
            "ok": False,
            "error": str(exc),
        }, indent=2, ensure_ascii=False))
        return 1

    if args.state:
        print(json.dumps(
            _state_summary(agent_map, args.state, limit=args.limit),
            indent=2,
            ensure_ascii=False,
        ))
        return 0

    if args.query:
        result: dict[str, Any] = {
            "ok": True,
            "app_id": agent_map.get("app_id"),
            "query": args.query,
            "exact": args.exact,
            "matches": _find_in_item_index(
                agent_map,
                args.query,
                exact=args.exact,
            )[:args.limit],
        }

        if args.details:
            result["details"] = _find_state_details(
                agent_map,
                args.query,
                exact=args.exact,
                limit=args.limit,
            )

        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    summary = {
        "ok": True,
        "app_id": agent_map.get("app_id"),
        "schema_version": agent_map.get("schema_version"),
        "root_state_id": agent_map.get("root_state_id"),
        "summary": agent_map.get("summary"),
        "items": len(agent_map.get("items", {})),
        "item_index_size": len(agent_map.get("item_index", {})),
        "verified_action_index_size": len(agent_map.get("verified_action_index", {})),
        "usage_notes": agent_map.get("usage_notes"),
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
