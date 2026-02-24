from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional, Union

JsonValue = Union[dict, list, str, int, float, bool, None]


@dataclass
class ParseResult:
    ok: bool
    data: Optional[JsonValue]
    mode: str  # direct | fenced | first_object | none
    error: Optional[str] = None


class RobustJSONParser:
    """
    direct -> fenced -> first_object
    + небольшой cleanup (trailing commas)
    """

    FENCED_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
    FIRST_OBJ_RE = re.compile(r"(\{.*\}|\[.*\])", re.DOTALL)

    @staticmethod
    def _cleanup(s: str) -> str:
        s = s.strip().lstrip("\ufeff")
        s = re.sub(r",\s*([}\]])", r"\1", s)  # trailing commas
        return s

    def parse(self, text: str) -> ParseResult:
        raw = text.strip()

        # 1) direct
        try:
            return ParseResult(ok=True, data=json.loads(self._cleanup(raw)), mode="direct")
        except Exception:
            pass

        # 2) fenced
        m = self.FENCED_RE.search(raw)
        if m:
            candidate = self._cleanup(m.group(1))
            try:
                return ParseResult(ok=True, data=json.loads(candidate), mode="fenced")
            except Exception as e:
                fenced_err = str(e)
        else:
            fenced_err = None

        # 3) first object/array
        m2 = self.FIRST_OBJ_RE.search(raw)
        if m2:
            candidate = self._cleanup(m2.group(1))
            try:
                return ParseResult(ok=True, data=json.loads(candidate), mode="first_object")
            except Exception as e:
                return ParseResult(ok=False, data=None, mode="first_object", error=str(e))

        return ParseResult(ok=False, data=None, mode="none", error=fenced_err or "No JSON found")
