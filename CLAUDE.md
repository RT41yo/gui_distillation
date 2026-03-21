# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GUI Distillation** — distills GUI interaction skills from multimodal LLMs (MLLMs) into compact specialized models delivered as MCP tools. The reference application is **GNOME Calculator** running in a headless Xvfb virtual display.

Current phase: **Phase 1** — data collection and semantic annotation via OpenAI GPT-4.1.

## Commands

### Install dependencies
```bash
pip install -r requirements.txt
```

### Run tests
```bash
pytest tests/unit/               # Unit tests (no external deps)
pytest tests/integration/        # Integration smoke tests
pytest -v                        # All tests, verbose
pytest -q tests/unit/test_schemas.py  # Single test file
```

### Phase 1 pipeline

**Part 1 — Data collection** (requires Xvfb):
```bash
Xvfb :99 -screen 0 1280x1024x24 -ac &
export DISPLAY=:99
python -m src.core.automation \
  --random-buttons --steps 5 \
  --settings config/settings.yaml \
  --app-config config/apps/calculator.yaml \
  --output data/exploration/phase_1_debug
```

**Part 2 — Semantic annotation** (requires `OPENAI_API_KEY`):
```bash
python -m src.exploration.teacher_debug_runner \
  --steps-root data/exploration/phase_1_debug \
  --settings config/settings.yaml \
  --teacher-config config/teachers/openai_gpt.yaml \
  --max-steps 5
```

**Part 3 — Evaluation:**
```bash
python -m src.exploration.evaluate_bbox \
  --calculator-yaml config/apps/calculator.yaml \
  --observation-grounded data/exploration/phase_1_debug/step_0001/observation_grounded.json

python -m src.exploration.evaluate_iou \
  --gold-bboxes config/apps/calculator_bboxes.yaml \
  --predicted data/exploration/phase_1_debug/step_0000/observation_grounded.json
```

### Calibration tools
```bash
python scripts/tools/find_coordinates.py          # Re-calibrate click points
python scripts/tools/find_coordinates_bboxes.py   # Re-calibrate bbox gold standard
```

## Architecture

### Four formal skills (defined in `docs/phase_0/skill_formalization.md`)

| Skill | Name | Role |
|-------|------|------|
| 0 | SimplifierTask | Decomposes high-level instructions into atomic tasks |
| A | GroundingTool | Localizes UI elements in screenshots → bounding boxes |
| B | ActionModel | Selects and parameterizes the next GUI action |
| C | StateModel | Interprets before/after screenshots → semantic state changes |

Pydantic schemas for all four skills: `src/skills/schemas.py`. MLLM response schemas (what GPT-4.1 returns): `src/skills/teacher_schemas.py`.

### Data flow

```
GUIAutomation (src/core/automation.py)
  → step_NNNN/{before.png, after.png, action.json, metadata.json}

TeacherDebugRunner (src/exploration/teacher_debug_runner.py)
  → step_NNNN/{observation.json, observation_grounded.json, delta.json}
  → annotator_debug_report.json

evaluate_bbox.py / evaluate_iou.py
  → metrics against config/apps/calculator_bboxes.yaml gold standard
```

### Key modules

- **`src/core/automation.py`** — `GUIAutomation` class: launches GNOME Calculator, takes screenshots, executes clicks/key presses, runs random exploration sessions.
- **`src/exploration/teacher_debug_runner.py`** — `TeacherDebugRunner`: loads collected steps, calls GPT-4.1 with observation/grounded/delta prompts, saves annotated outputs.
- **`src/teachers/openai_client.py`** — Thin wrapper around OpenAI SDK; handles retries, image encoding, structured JSON responses.
- **`src/teachers/json_parser.py`** — `RobustJSONParser`: handles direct JSON, fenced code blocks, and first-object extraction from model outputs.
- **`src/core/exceptions.py`** — Full exception hierarchy rooted at `GUIDistillationError` with subcategories: `AppError`, `AutomationError`, `TeacherError`, `DataError`, `ConfigError`, `ExplorationError`, `MCPError`.

### Configuration

- **`config/settings.yaml`** — Master runtime config: paths, display settings (`:99`, `1280x1024`), feature flags (`use_grounded_observation`), teacher timeouts/retries.
- **`config/apps/calculator.yaml`** — Calibrated click-point coordinates `[x, y]` for each button (20 buttons), calibrated on `1280x1024`.
- **`config/apps/calculator_bboxes.yaml`** — Gold-standard bounding boxes `[x1, y1, x2, y2]` used as IoU evaluation ground truth.
- **`config/teachers/openai_gpt.yaml`** — Model: `gpt-4.1`, temperature `0.0`, image detail `high`.
- **`config/prompts/`** — Markdown prompt templates: `observation_v1.md`, `observation_grounded_v1.md`, `delta_v1.md`, `action_v1.md`.

### Vocabularies (closed sets)

`vocabularies/atomic_tasks.yaml` defines the 9 atomic task types (e.g. `enter_number`, `operation`, `compute`, `clear`). `vocabularies/action_types.yaml` defines action types (`click`, `type`, `press`, `hotkey`, `move_to`). These are the canonical enums used in `src/skills/schemas.py`.

### Current grounding quality (Phase 1 results)

MLLM-predicted bboxes are weak: mean IoU ≈ 0.18, IoU@0.5 ≈ 5.6%, IoU@0.75 = 0%. Calibrated coordinates in `calculator.yaml` remain the primary source of truth for click positions.

## Environment

Copy `.env.example` to `.env` and set `OPENAI_API_KEY`. The virtual display must be running (`DISPLAY=:99`) for any automation or integration tests.
