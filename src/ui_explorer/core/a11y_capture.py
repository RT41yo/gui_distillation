from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

logger = logging.getLogger(__name__)


class A11YCapture:
    """Capture AT-SPI2 accessibility tree of a running application into XML."""

    @staticmethod
    def _import_pyatspi():
        try:
            import pyatspi  # type: ignore
            return pyatspi
        except ImportError as exc:
            raise RuntimeError(
                "pyatspi is required. Install it with: "
                "sudo apt-get install python3-pyatspi"
            ) from exc

    def find_app(self, a11y_name: str, timeout_s: float = 8.0):
        pyatspi = self._import_pyatspi()
        needle = a11y_name.lower()
        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            try:
                desktop = pyatspi.Registry.getDesktop(0)
                for app in desktop:
                    if app is None:
                        continue
                    app_name = (app.name or "").lower()
                    if needle in app_name or app_name in needle:
                        logger.info("Found A11Y app: %s", app.name)
                        return app, pyatspi
            except Exception as exc:
                logger.debug("AT-SPI lookup failed; retrying: %s", exc)

            time.sleep(0.25)

        raise RuntimeError(
            f"Could not find app '{a11y_name}' in AT-SPI registry "
            f"within {timeout_s:.1f}s"
        )

    def capture_to_xml(
        self,
        a11y_name: str,
        output_path: Path,
        timeout_s: float = 8.0,
    ) -> Path:
        app, pyatspi = self.find_app(a11y_name, timeout_s=timeout_s)

        root = ET.Element("accessibility-tree")
        root.set("app_query", a11y_name)
        root.set("app_accessible_name", app.name or "")
        root.set("captured_at", str(time.time()))

        self._traverse(app, root, pyatspi)

        raw = ET.tostring(root, encoding="unicode")
        pretty = minidom.parseString(raw).toprettyxml(indent="  ")
        lines = pretty.splitlines()
        if lines and lines[0].startswith("<?xml"):
            pretty = "\n".join(lines[1:])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(pretty, encoding="utf-8")
        logger.info("A11Y XML saved: %s", output_path)
        return output_path

    def _traverse(self, obj, parent_elem: ET.Element, pyatspi) -> None:
        try:
            role = obj.getRoleName() or "unknown"
            name = obj.name or ""
            description = obj.description or ""
        except Exception:
            return

        elem = ET.SubElement(parent_elem, "element")
        elem.set("role", role)
        elem.set("name", name)
        elem.set("description", description)

        try:
            component = obj.queryComponent()
            ext = component.getExtents(pyatspi.DESKTOP_COORDS)
            elem.set("x", str(ext.x))
            elem.set("y", str(ext.y))
            elem.set("width", str(ext.width))
            elem.set("height", str(ext.height))
        except Exception:
            elem.set("x", "0")
            elem.set("y", "0")
            elem.set("width", "0")
            elem.set("height", "0")

        try:
            state_set = obj.getState()
            states: list[str] = []
            state_map = [
                (pyatspi.STATE_CHECKED, "checked"),
                (pyatspi.STATE_SELECTED, "selected"),
                (pyatspi.STATE_FOCUSED, "focused"),
                (pyatspi.STATE_SENSITIVE, "sensitive"),
                (pyatspi.STATE_EXPANDED, "expanded"),
                (pyatspi.STATE_COLLAPSED, "collapsed"),
                (pyatspi.STATE_SHOWING, "showing"),
                (pyatspi.STATE_VISIBLE, "visible"),
                (pyatspi.STATE_ENABLED, "enabled"),
            ]
            for state_const, state_name in state_map:
                if state_set.contains(state_const):
                    states.append(state_name)
            if states:
                elem.set("states", ",".join(states))
        except Exception:
            pass

        try:
            for i in range(obj.childCount):
                child = obj.getChildAtIndex(i)
                if child is not None:
                    self._traverse(child, elem, pyatspi)
        except Exception:
            pass
