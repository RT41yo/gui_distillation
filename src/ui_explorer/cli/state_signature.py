from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ui_explorer.core.a11y_parser import parse_a11y_xml
from ui_explorer.core.state import compute_state_signature


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute A11Y-only state signature.")
    parser.add_argument("xml", type=Path)
    parser.add_argument("--payload", action="store_true", help="Include full signature payload.")
    args = parser.parse_args()

    root = parse_a11y_xml(args.xml)
    sig = compute_state_signature(root)

    print(json.dumps(sig.to_dict(include_payload=args.payload), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
