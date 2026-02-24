from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from src.skills.teacher_schemas import DeltaResponse, InventoryResponse
from src.teachers.json_parser import RobustJSONParser
from src.teachers.openai_client import OpenAITeacherClient, SettingsLoader

JsonDict = Dict[str, Any]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class StepRun:
    step: str
    inventory_ok: bool
    delta_ok: bool
    inventory_parse_mode: str
    delta_parse_mode: str
    latency_inventory_s: float
    latency_delta_s: float
    errors: List[str]


class TeacherDebugRunner:
    """
    Offline pass over existing steps:
      - inventory(before.png) -> inventory.json
      - delta(before.png, after.png, action.json) -> delta.json

    Enhancements:
      - Always saves raw teacher text on failures (and optionally on success)
      - Saves parser mode/error for debugging
      - Saves extracted JSON candidate if available
    """

    def __init__(
        self,
        steps_root: Path,
        settings_path: str = "config/settings.yaml",
        teacher_config_path: str = "config/teachers/openai_gpt.yaml",
    ) -> None:
        self.steps_root = steps_root
        self.settings = SettingsLoader.load(settings_path)

        # Step file names (from settings)
        self.before_name = str(SettingsLoader.get(self.settings, "data.step_files.before", "before.png"))
        self.after_name = str(SettingsLoader.get(self.settings, "data.step_files.after", "after.png"))
        self.metadata_name = str(SettingsLoader.get(self.settings, "data.step_files.metadata", "metadata.json"))

        # settings.yaml does not define "action" key, but automation produces action.json → fallback
        self.action_name = str(SettingsLoader.get(self.settings, "data.step_files.action", "action.json"))

        # Where to save teacher outputs for this debug run:
        self.inventory_out_name = str(SettingsLoader.get(self.settings, "data.step_files.inventory", "inventory.json"))
        self.delta_out_name = str(SettingsLoader.get(self.settings, "data.step_files.delta", "delta.json"))

        # Raw/debug filenames
        self.inventory_raw_name = self.inventory_out_name.replace(".json", "_raw.json")
        self.delta_raw_name = self.delta_out_name.replace(".json", "_raw.json")

        # Whether to keep raw even on success (useful while debugging prompts)
        self.keep_raw_on_success = bool(
            SettingsLoader.get(self.settings, "development.keep_teacher_raw_on_success", False)
        )

        # Prompts directory
        prompts_dir = Path(str(SettingsLoader.get(self.settings, "paths.prompts_dir", "config/prompts")))
        self.prompt_inventory = read_text(prompts_dir / "inventory_v1.md")
        self.prompt_delta = read_text(prompts_dir / "delta_v1.md")

        self.client = OpenAITeacherClient(
            settings_path=settings_path,
            teacher_config_path=teacher_config_path,
            dotenv_path=".env",
            api_key_env="OPENAI_API_KEY",
        )
        self.parser = RobustJSONParser()

    def _iter_step_dirs(self) -> List[Path]:
        return sorted([p for p in self.steps_root.iterdir() if p.is_dir() and p.name.startswith("step_")])

    def _save_raw_payload(
        self,
        step_dir: Path,
        filename: str,
        *,
        error: Optional[str],
        raw_text: Optional[str],
        parse_mode: Optional[str],
        parse_error: Optional[str],
        parsed_data_preview: Optional[Any],
        prompt_name: str,
        model: Optional[str],
        latency_s: Optional[float],
    ) -> None:
        payload: JsonDict = {
            "error": error,
            "prompt": prompt_name,
            "model": model,
            "latency_s": latency_s,
            "parse_mode": parse_mode,
            "parse_error": parse_error,
            "raw_text": raw_text,
        }

        # Preview parsed payload (helps when JSON parsed but schema failed)
        if parsed_data_preview is not None:
            payload["parsed_data_preview"] = parsed_data_preview

        write_json(step_dir / filename, payload)

    def run(self, max_steps: Optional[int] = None) -> JsonDict:
        step_dirs = self._iter_step_dirs()
        if max_steps is not None:
            step_dirs = step_dirs[:max_steps]

        per_step: List[StepRun] = []

        for sd in step_dirs:
            errs: List[str] = []

            before = sd / self.before_name
            after = sd / self.after_name
            action = sd / self.action_name

            if not before.exists():
                per_step.append(
                    StepRun(sd.name, False, False, "none", "none", 0.0, 0.0, [f"missing {before.name}"])
                )
                continue

            # --- INVENTORY ---
            inv_ok = False
            inv_mode = "none"
            inv_latency = 0.0
            inv_raw_text: Optional[str] = None
            inv_model: Optional[str] = None
            inv_parse_error: Optional[str] = None
            inv_parsed_preview: Optional[Any] = None

            try:
                r = self.client.infer(self.prompt_inventory, image_paths=[before], prefer_json=True)
                inv_latency = r.latency_s
                inv_raw_text = r.text
                inv_model = r.model

                parsed = self.parser.parse(r.text)
                inv_mode = parsed.mode
                inv_parse_error = parsed.error

                if parsed.ok and isinstance(parsed.data, dict):
                    # preview only top-level keys to avoid huge logs
                    inv_parsed_preview = list(parsed.data.keys())
                else:
                    inv_parsed_preview = None

                if not parsed.ok or not isinstance(parsed.data, dict):
                    raise RuntimeError(f"inventory parse failed: {parsed.error}")

                inv_obj = InventoryResponse.model_validate(parsed.data)
                write_json(sd / self.inventory_out_name, inv_obj.model_dump())
                inv_ok = True

                if self.keep_raw_on_success:
                    self._save_raw_payload(
                        sd,
                        self.inventory_raw_name,
                        error=None,
                        raw_text=inv_raw_text,
                        parse_mode=inv_mode,
                        parse_error=inv_parse_error,
                        parsed_data_preview=inv_parsed_preview,
                        prompt_name="inventory_v1",
                        model=inv_model,
                        latency_s=inv_latency,
                    )

            except (ValidationError, Exception) as e:
                err_str = str(e)
                errs.append(f"inventory: {err_str}")

                # Save raw teacher text + parse diagnostics
                self._save_raw_payload(
                    sd,
                    self.inventory_raw_name,
                    error=err_str,
                    raw_text=inv_raw_text,
                    parse_mode=inv_mode,
                    parse_error=inv_parse_error,
                    parsed_data_preview=inv_parsed_preview,
                    prompt_name="inventory_v1",
                    model=inv_model,
                    latency_s=inv_latency if inv_latency > 0 else None,
                )

            # --- DELTA ---
            del_ok = False
            del_mode = "none"
            del_latency = 0.0
            del_raw_text: Optional[str] = None
            del_model: Optional[str] = None
            del_parse_error: Optional[str] = None
            del_parsed_preview: Optional[Any] = None

            if not after.exists():
                errs.append(f"delta skipped: missing {after.name}")
                # Save minimal raw record for traceability
                self._save_raw_payload(
                    sd,
                    self.delta_raw_name,
                    error=f"delta skipped: missing {after.name}",
                    raw_text=None,
                    parse_mode=None,
                    parse_error=None,
                    parsed_data_preview=None,
                    prompt_name="delta_v1",
                    model=None,
                    latency_s=None,
                )
            elif not action.exists():
                errs.append(f"delta skipped: missing {action.name}")
                self._save_raw_payload(
                    sd,
                    self.delta_raw_name,
                    error=f"delta skipped: missing {action.name}",
                    raw_text=None,
                    parse_mode=None,
                    parse_error=None,
                    parsed_data_preview=None,
                    prompt_name="delta_v1",
                    model=None,
                    latency_s=None,
                )
            else:
                try:
                    action_data = json.loads(action.read_text(encoding="utf-8"))
                    delta_prompt = (
                        self.prompt_delta
                        + "\n\nACTION_JSON:\n"
                        + json.dumps(action_data, ensure_ascii=False)
                    )

                    r2 = self.client.infer(delta_prompt, image_paths=[before, after], prefer_json=True)
                    del_latency = r2.latency_s
                    del_raw_text = r2.text
                    del_model = r2.model

                    parsed2 = self.parser.parse(r2.text)
                    del_mode = parsed2.mode
                    del_parse_error = parsed2.error

                    if parsed2.ok and isinstance(parsed2.data, dict):
                        del_parsed_preview = list(parsed2.data.keys())
                    else:
                        del_parsed_preview = None

                    if not parsed2.ok or not isinstance(parsed2.data, dict):
                        raise RuntimeError(f"delta parse failed: {parsed2.error}")

                    del_obj = DeltaResponse.model_validate(parsed2.data)
                    write_json(sd / self.delta_out_name, del_obj.model_dump())
                    del_ok = True

                    if self.keep_raw_on_success:
                        self._save_raw_payload(
                            sd,
                            self.delta_raw_name,
                            error=None,
                            raw_text=del_raw_text,
                            parse_mode=del_mode,
                            parse_error=del_parse_error,
                            parsed_data_preview=del_parsed_preview,
                            prompt_name="delta_v1",
                            model=del_model,
                            latency_s=del_latency,
                        )

                except (ValidationError, Exception) as e:
                    err_str = str(e)
                    errs.append(f"delta: {err_str}")
                    self._save_raw_payload(
                        sd,
                        self.delta_raw_name,
                        error=err_str,
                        raw_text=del_raw_text,
                        parse_mode=del_mode,
                        parse_error=del_parse_error,
                        parsed_data_preview=del_parsed_preview,
                        prompt_name="delta_v1",
                        model=del_model,
                        latency_s=del_latency if del_latency > 0 else None,
                    )

            per_step.append(
                StepRun(
                    step=sd.name,
                    inventory_ok=inv_ok,
                    delta_ok=del_ok,
                    inventory_parse_mode=inv_mode,
                    delta_parse_mode=del_mode,
                    latency_inventory_s=inv_latency,
                    latency_delta_s=del_latency,
                    errors=errs,
                )
            )

        inv_ok_count = sum(1 for r in per_step if r.inventory_ok)
        del_ok_count = sum(1 for r in per_step if r.delta_ok)

        inv_latency_values = [r.latency_inventory_s for r in per_step if r.latency_inventory_s > 0]
        del_latency_values = [r.latency_delta_s for r in per_step if r.latency_delta_s > 0]

        report: JsonDict = {
            "steps_root": str(self.steps_root),
            "total_steps": len(per_step),
            "inventory_ok": inv_ok_count,
            "delta_ok": del_ok_count,
            "inventory_ok_rate": inv_ok_count / len(per_step) if per_step else 0.0,
            "delta_ok_rate": del_ok_count / len(per_step) if per_step else 0.0,
            # report average latency even if ok_count is 0 (use observed values)
            "avg_latency_inventory_s": (sum(inv_latency_values) / len(inv_latency_values)) if inv_latency_values else 0.0,
            "avg_latency_delta_s": (sum(del_latency_values) / len(del_latency_values)) if del_latency_values else 0.0,
            "per_step": [
                {
                    "step": r.step,
                    "inventory_ok": r.inventory_ok,
                    "delta_ok": r.delta_ok,
                    "inventory_parse_mode": r.inventory_parse_mode,
                    "delta_parse_mode": r.delta_parse_mode,
                    "latency_inventory_s": r.latency_inventory_s,
                    "latency_delta_s": r.latency_delta_s,
                    "errors": r.errors,
                }
                for r in per_step
            ],
        }

        write_json(self.steps_root / "teacher_debug_report.json", report)
        return report


def main() -> int:
    ap = argparse.ArgumentParser("teacher_debug_runner")
    ap.add_argument("--steps-root", required=True)
    ap.add_argument("--settings", default="config/settings.yaml")
    ap.add_argument("--teacher-config", default="config/teachers/openai_gpt.yaml")
    ap.add_argument("--max-steps", type=int, default=None)
    args = ap.parse_args()

    runner = TeacherDebugRunner(
        steps_root=Path(args.steps_root),
        settings_path=args.settings,
        teacher_config_path=args.teacher_config,
    )
    runner.run(max_steps=args.max_steps)
    print(f"Done: {Path(args.steps_root) / 'teacher_debug_report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
