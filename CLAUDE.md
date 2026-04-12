# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

**gui2mcp** — A11Y-first GUI Trajectory Agent that collects GUI interaction trajectories for training data.
An LLM agent controls real desktop applications via AT-SPI2 accessibility tree (primary) + VLM locator (parallel, for IoU metric).
Results are exported in DART-like format for downstream use.

**Branch:** `phase_2` — clean branch from `main`, contains only agent-relevant code.

**TZ document:** `A11Y-first GUI Trajectory Agent.md` — kept in sync with implementation.

---

## Supported Applications

| app_id | Application | Launcher |
|---|---|---|
| `calc` | GNOME Calculator | `gnome-calculator` |
| `writer` | LibreOffice Writer | `libreoffice --writer` |
| `gedit` | gedit | `gedit` |

Adding a new app requires: `config/app_basket.yaml` + `config/task_basket.yaml` + new evaluator in `src/evaluation/` + one `if` branch in `src/agents/gui2mcp_agent.py:_build_evaluator()`.

---

## Commands

### Run agent (real display)
```bash
python -m src.cli.gui2mcp_agent_runner \
  --app calc \
  --task-id calc_001 \
  --max-steps 15 \
  --display :0 \
  --screen-width 1920 \
  --screen-height 1080 \
  --output results/ \
  --dart-output data/ \
  --verbose
```

### Run agent (headless / Xvfb)
```bash
Xvfb :99 -screen 0 1280x1024x24 -ac &
sleep 1
DISPLAY=:99 python -m src.cli.gui2mcp_agent_runner \
  --app calc \
  --task-id calc_001 \
  --max-steps 15 \
  --display :99 \
  --screen-width 1280 \
  --screen-height 1024 \
  --output results/ \
  --dart-output data/ \
  --verbose
```

### Run tests
```bash
pytest tests/unit/test_gui2mcp.py -v
```

---

## Architecture

```
CLI (gui2mcp_agent_runner)
  └── Gui2MCPAgent                    # top-level orchestrator
        ├── AppRegistry / TaskRegistry  # load app_basket.yaml / task_basket.yaml
        ├── _reset()                    # close + relaunch app before each episode
        ├── EpisodeController           # step loop (max N steps)
        │     ├── TakeScreenshotTool    # pyautogui.screenshot()
        │     ├── GetA11YTreeTool       # AT-SPI2 → XML + TXT
        │     ├── Planner (LLM)         # gpt-5.4-mini → PlannerResponse (action + done?)
        │     ├── FindElementA11YTool   # A11Y primary locator
        │     ├── FindElementVLMTool    # VLM locator (always, for IoU)
        │     ├── compute_iou()         # A11Y bbox = GT, VLM bbox = pred
        │     ├── ActionExecutor        # click / type_text / hotkey / scroll
        │     └── compute_dhash_record()# perceptual hash Δ between frames
        ├── Evaluator                   # programmatic ground-truth check (post-loop)
        │     ├── CalcEvaluator         # reads last A11Y XML → last numeric label
        │     ├── WriterEvaluator       # searches expected_text in last A11Y XML
        │     └── GeditEvaluator        # same as WriterEvaluator
        └── DartExporter / SummaryExporter  # DART-like export
```

**Episode termination:**
- LLM returns `done=true` → loop breaks early (efficiency)
- `max_steps` exhausted → loop ends
- Evaluator always runs after loop → assigns `score=1.0` or `score=0.0`

---

## Key Files

| File | Purpose |
|---|---|
| `config/app_basket.yaml` | App definitions (launcher, a11y_app_name) |
| `config/task_basket.yaml` | Task definitions per app (instruction, evaluator, expected_text) |
| `config/settings.yaml` | Runtime profile, display geometry, LLM API defaults |
| `config/llm/planner_gpt-5.4-mini.yaml` | Planner LLM config (model: gpt-5.4-mini) |
| `config/llm/locator_gpt-5.4-mini.yaml` | Locator LLM config (model: gpt-5.4-mini) |
| `config/prompts/planner_task_v1.md` | Planner prompt template |
| `config/prompts/locator_vlm_v1.md` | VLM locator prompt (includes screen resolution + app name) |
| `src/domain/models.py` | All Pydantic v2 data models |
| `src/agents/gui2mcp_agent.py` | Top-level agent, evaluator factory |
| `src/agents/episode_controller.py` | Step loop |
| `src/agents/planner.py` | LLM planner wrapper |
| `src/evaluation/calc_evaluator.py` | Reads last numeric label from A11Y XML |
| `src/teachers/openai_client.py` | OpenAI API client |
| `src/teachers/json_parser.py` | RobustJSONParser |
| `src/core/a11y_capture.py` | AT-SPI2 capture → XML/TXT |
| `tests/unit/test_gui2mcp.py` | Unit tests (13 tests) |

---

## Output Structure

```
results/<uuid>/                          # internal artifacts per episode
  step_0000.png, a11y_step_0000.xml, ...
  steps/step_0000.json, ...
  episode.json                           # full episode record with score
  hamming_chart.png

data/pyautogui/screenshot/gui2mcp_agent/  # DART-like export
  <app_id>/<uuid>/
    step_N_<timestamp>.png
    traj.jsonl
    result.txt
  all_result.json                        # summary across all episodes
  summary/results.json
```

---

## Task Design

**Calculator (12 tasks):**
- `calc_001–004`: multi-step arithmetic in Basic mode
- `calc_005–008`: Scientific mode (power, sqrt, factorial, log)
- `calc_009`: mode switch Basic → Scientific
- `calc_010–012`: Programming mode (hex, AND, XOR)

Evaluator reads expected value from `evaluator` field: `display_equals_108` → `108`.
CalcEvaluator takes the **last** pure numeric label from A11Y XML (GNOME Calculator keeps history of results — first label is an intermediate value, not the final result).

**Writer / gedit (10 tasks each):**
- Mix of `text_edit` (type only) and `text_edit_save` (type + Ctrl+S)
- Evaluator checks `expected_text` presence in last A11Y XML
- Note: `writer_saved_with_text` evaluator currently does not verify save separately from text presence — known limitation.

---

## Environment

- **API key:** stored in `.env`, loaded automatically via `python-dotenv` at CLI startup
- **LLM model:** `gpt-5.4-mini` for both planner and locator (not `gpt-4o-mini`)
- **Python:** 3.10+
- **Key deps:** pyautogui, pyatspi, pydantic v2, openai, python-dotenv, matplotlib, Pillow
- **Display:** `:0` for real display, `:99` for Xvfb headless
