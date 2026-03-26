# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GUI Distillation** — A research project that distills GUI navigation skills from multimodal LLMs (MLLMs) into specialized compact models. The proof-of-concept application is GNOME Calculator. The current active phase is **Phase 1** (data collection and semantic annotation).

## Commands

### Setup (VM environment)
```bash
sudo bash scripts/setup/setup_vm.sh        # Install Python, pip, venv, git
sudo bash scripts/setup/install_apps.sh    # Install GNOME Calculator
sudo bash scripts/setup/setup_xvfb.sh      # Install Xvfb and X11 tools
bash scripts/setup/reset_display.sh        # Start/restart virtual display on :99
```

### Running Tests
```bash
pytest                                     # Run all tests
pytest -q tests/unit/test_schemas.py       # Run a single test file
pytest -v                                  # Verbose output
```

### Main Workflows

**Online task execution** (LLM drives a live GUI session):
```bash
# Single task mode
python -m src.exploration.task_runner \
  --task "add 3 and 5, then subtract 2" \
  --max-steps 20 \
  --settings config/settings.yaml \
  --app-config config/apps/calculator.yaml \
  --teacher-config config/teachers/openai_gpt.yaml \
  --output data/exploration/task_runs/run_001

# Autonomous exploration mode
python -m src.exploration.task_runner \
  --exploration \
  --task "Explore GNOME Calculator..." \
  --max-steps 50 \
  --output data/exploration/task_runs/explore_001
```

**Offline annotation** (annotate existing step artifacts with LLM):
```bash
# Output filename is derived from the model in teacher config:
#   openai_gpt.yaml        -> observation_grounded_gpt-4.1.json
#   openai_gpt-5.4.yaml    -> observation_grounded_gpt-5.4.json
#   openai_gpt-5.4-mini.yaml -> observation_grounded_gpt-5.4-mini.json
python -m src.exploration.annotator_runner \
  --steps-root data/exploration/phase_1_debug \
  --settings config/settings.yaml \
  --teacher-config config/teachers/openai_gpt.yaml \
  --max-steps 5
```

**IoU evaluation** (compare grounded bboxes against calibrated gold standard):
```bash
# Output filename mirrors the input: observation_grounded_gpt-4.1.json -> iou_eval_gpt-4.1.json
python -m src.exploration.evaluate_iou \
  --predicted data/exploration/phase_1_debug/step_0000/observation_grounded_gpt-4.1.json
```

**dHash interface-change detection experiment** (A11Y tree + dHash pipeline):
```bash
# Requires virtual display running and DISPLAY=:99
python -m src.core.automation_dhash \
  --output data/exploration/task_runs/run_dhash_001 \
  --display :99 \
  --verbose
```

**Infrastructure test**:
```bash
python scripts/tools/test_automation.py --display :99 --app gnome-calculator -v
```

**Calibration tools**:
```bash
python scripts/tools/find_coordinates.py        # Calibrate button center coords
python scripts/tools/find_coordinates_bboxes.py # Calibrate button bounding boxes
```

## Architecture

The system has two pipelines that share a common artifact format:

### Step Artifact Format
Every action produces a step directory:
```
step_0000/
  before.png          # Screenshot before action
  after.png           # Screenshot after action
  action.json         # What action was taken
  metadata.json       # Timing, hashing (MD5/SHA1/SHA256/dHash), etc.
  # Added by offline annotation:
  observation.json                    # UI element inventory with IDs and confidence
  observation_grounded_{model}.json   # UI elements with bounding boxes (model = gpt-4.1, gpt-5.4, etc.)
  delta.json                          # Description of state change
```

### Online Pipeline (`src/exploration/task_runner.py`)
`TaskRunner` runs a live GNOME Calculator session. At each step it:
1. Captures a screenshot + retrieves the button list from `config/apps/calculator.yaml`
2. Sends screenshot + history to LLM with a prompt from `config/prompts/`
3. LLM returns the next button to click
4. `GUIAutomation` executes the click and saves the step artifact

Two modes: **task mode** (execute a specific goal) and **exploration mode** (LLM autonomously invents sub-goals, history resets between goals).

### Offline Pipeline (`src/exploration/annotator_runner.py`)
`AnnotatorRunner` processes pre-existing step artifacts without a running GUI. For each step it calls the LLM three times (observation, grounded observation, delta) and saves the JSON annotations back into the step directory. The grounded observation filename is derived from the `model` field in the teacher config YAML. Generates `annotator_debug_report.json` on completion.

### dHash Experiment Pipeline (`src/core/automation_dhash.py` + `src/core/a11y_capture.py`)
Experimental pipeline demonstrating that UI state changes (mode switches, layout changes) can be tracked via dHash without manual recalibration. Uses A11Y tree coordinates exclusively — no dependency on `calculator.yaml`.

Pipeline stages:
1. Launch calculator → capture A11Y tree (XML + filtered TXT with button coordinates)
2. Take `screenshot_start.png` + MD5 + dHash
3. Execute 2 calculations using A11Y coordinates (`"3"`, `"+"`, `"5"`, `"="` etc.)
4. Open mode-selection popup (click `"Mode selection"` toggle) → re-scan A11Y → detect current mode via `gsettings` → click a different mode
5. Compare dHash before/after the mode click — if changed → re-capture A11Y tree with updated coordinates
6. Run 2 more calculations using updated A11Y coords (fallback to initial A11Y if dHash unchanged)
7. Take `screenshot_final.png` + MD5 + dHash
8. Save `dhash_comparison.json` and `run_summary.json`

Root run directory contains exactly two pipeline-level screenshots: `screenshot_start.png` (before any actions) and `screenshot_final.png` (after all stages complete). Each step directory retains its own `before.png` / `after.png` pair.

`A11YCapture` (`src/core/a11y_capture.py`) uses `pyatspi` (AT-SPI2) to traverse the live accessibility tree, serialize it to XML (with element roles, names, coordinates, and states), and filter it to a readable TXT. `find_unchecked_mode_button()` reads AT-SPI states to avoid re-selecting the already-active mode. Current mode is also cross-checked via `gsettings get org.gnome.calculator button-mode`.

**Key finding:** Basic→Programming mode switch produced 27→96 buttons with all coordinates changed, dHash signal fired correctly, and the re-captured A11Y tree provided accurate new coordinates — demonstrating that dHash + A11Y is a viable self-updating coordinate system.

**`pyatspi` setup note:** `python3-pyatspi` is a system package (not on PyPI). `setup_vm.sh` installs it via apt and creates `system_dist_packages.pth` in the venv's site-packages to make it importable.

### Core Automation (`src/core/automation.py`)
`GUIAutomation` owns all interaction with the OS: app launch/close, screenshot capture, action dispatch (click, type, key press, hotkey, mouse move), and artifact persistence. It normalizes coordinates and computes perceptual hashes (dHash via `imagehash`) for state change detection.

### LLM Layer (`src/teachers/`)
- `openai_client.py` — OpenAI API wrapper with retry logic and image encoding
- `prompt_loader.py` — Loads markdown prompt templates from `config/prompts/`
- `json_parser.py` — Robust JSON extraction with fallback modes (handles fenced code blocks, partial responses)

### Schemas (`src/skills/`)
- `schemas.py` — Pydantic v2 models for the four distillation skills: **Grounding** (locate elements), **Action** (predict next click), **State** (compare UI states), **Simplifier** (NL → action sequence). `BBox` uses normalized [0,1] coordinates.
- `teacher_schemas.py` — Pydantic models for LLM output: `ObservationResponse`, `GroundedObservationResponse`, `DeltaResponse`.

## Configuration

**`config/settings.yaml`** — Master config covering paths, display/screen geometry (1280×1024×24 on `:99`), automation timing, LLM defaults, exploration protocol, dataset engineering, training, and feature flags (e.g., `use_grounded_observation`).

**`config/apps/calculator.yaml`** — Calibrated absolute pixel coordinates for 24 GNOME Calculator buttons. Used by `TaskRunner` to provide LLM with the available actions and to execute clicks accurately. This is authoritative for coordinates; MLLM-predicted bboxes have weak accuracy (~18% IoU).

**`config/teachers/openai_gpt.yaml`** (also `openai_gpt-5.4.yaml`, `openai_gpt-5.4-mini.yaml`) — Teacher model configs (model name, temperature, max_tokens, image_detail, timeout, retries). The `model` field is used to derive the grounded observation output filename.

**`config/prompts/*.md`** — Prompt templates loaded at runtime. Naming convention: `{purpose}_v{N}.md`.

## Environment

Requires a running X display (Xvfb on `:99` in VM, native display on host). Set `DISPLAY=:99` or rely on `config/settings.yaml` profile overrides. API keys are loaded via `python-dotenv` from a `.env` file (not committed).
