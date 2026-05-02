from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from ui_explorer.core.a11y_capture import A11YCapture
from ui_explorer.core.a11y_parser import parse_a11y_xml
from ui_explorer.core.state import StateSignature, compute_state_signature


@dataclass(frozen=True)
class CapturedState:
    xml_path: Path
    signature: StateSignature

    def to_dict(self) -> dict:
        return {
            "xml_path": str(self.xml_path),
            "signature": self.signature.to_dict(),
        }


class A11YWaiter:
    """Capture A11Y until state signature stabilizes."""

    def __init__(self, a11y_name: str, timeout_s: float = 5.0, interval_s: float = 0.3) -> None:
        self.a11y_name = a11y_name
        self.timeout_s = timeout_s
        self.interval_s = interval_s

    def capture_once(self, output_path: Path) -> CapturedState:
        A11YCapture().capture_to_xml(
            a11y_name=self.a11y_name,
            output_path=output_path,
            timeout_s=self.timeout_s,
        )
        root = parse_a11y_xml(output_path)
        sig = compute_state_signature(root)
        return CapturedState(xml_path=output_path, signature=sig)

    def capture_stable(self, output_dir: Path, prefix: str) -> CapturedState:
        output_dir.mkdir(parents=True, exist_ok=True)

        deadline = time.monotonic() + self.timeout_s
        previous_hash: str | None = None
        last_state: CapturedState | None = None
        attempt = 0

        while time.monotonic() < deadline:
            attempt += 1
            path = output_dir / f"{prefix}_{attempt:02d}.xml"
            state = self.capture_once(path)

            if state.signature.macro_hash == previous_hash:
                final_path = output_dir / f"{prefix}.xml"
                final_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
                return CapturedState(xml_path=final_path, signature=state.signature)

            previous_hash = state.signature.macro_hash
            last_state = state
            time.sleep(self.interval_s)

        assert last_state is not None
        final_path = output_dir / f"{prefix}.xml"
        final_path.write_text(last_state.xml_path.read_text(encoding="utf-8"), encoding="utf-8")
        return CapturedState(xml_path=final_path, signature=last_state.signature)
