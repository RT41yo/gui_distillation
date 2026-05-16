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


def _item_search_fields(item: dict[str, Any]) -> list[str]:
    return [
        str(item.get("name", "")),
        str(item.get("role", "")),
        str(item.get("description", "")),
        " ".join(str(x) for x in item.get("statuses", [])),
        " ".join(str(x) for x in item.get("parent_path_tail", [])),
    ]


def _matches_query(
    item: dict[str, Any],
    query: str,
    *,
    exact: bool = False,
) -> bool:
    query_norm = query.casefold()
    fields = _item_search_fields(item)

    if exact:
        return any(
            query_norm == field.casefold()
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
        for section in ("verified_actions", "observed_items"):
            for item in state.get(section, []):
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


def _state_summary(agent_map: dict[str, Any], state_id: str) -> dict[str, Any]:
    states = agent_map.get("states", {})
    state = states.get(state_id)

    if state is None:
        return {
            "ok": False,
            "error": f"state not found: {state_id}",
        }

    verified = state.get("verified_actions", [])
    observed = state.get("observed_items", [])

    return {
        "ok": True,
        "state_id": state_id,
        "label": state.get("label"),
        "depth": state.get("depth"),
        "active_root": state.get("active_root"),
        "verified_actions": [
            {
                "edge_id": item.get("edge_id"),
                "role": item.get("role"),
                "name": item.get("name"),
                "description": item.get("description"),
                "status": item.get("status"),
                "method": item.get("method"),
                "has_bbox": "bbox" in item,
                "to_state": item.get("to_state"),
            }
            for item in verified
        ],
        "observed_items_preview": [
            {
                "role": item.get("role"),
                "name": item.get("name"),
                "description": item.get("description"),
                "status": item.get("status"),
                "states": item.get("states"),
                "parent_path_tail": item.get("parent_path_tail"),
            }
            for item in observed[:50]
        ],
        "observed_items_total": len(observed),
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
            _state_summary(agent_map, args.state),
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
        "root_state_id": agent_map.get("root_state_id"),
        "summary": agent_map.get("summary"),
        "item_index_size": len(agent_map.get("item_index", {})),
        "usage_notes": agent_map.get("usage_notes"),
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
