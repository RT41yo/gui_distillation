#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKSPACE="${WORKSPACE:-$ROOT/data/synthetic/libreoffice_writer/active_root_231}"
MODEL="${MODEL:-gpt-5.4}"
GOAL_VARIANT_COUNT="${GOAL_VARIANT_COUNT:-4}"
BATCH_SIZE="${BATCH_SIZE:-4}"
LOG_DIR="$WORKSPACE/.logs/tmux-goal-${MODEL}"
SESSION_PREFIX="${SESSION_PREFIX:-goal-${MODEL}}"

mkdir -p "$LOG_DIR"

export WORKSPACE MODEL GOAL_VARIANT_COUNT
mapfile -t PENDING_STATES < <(
  cd "$ROOT" && source .venv/bin/activate && PYTHONPATH=src python3 - <<'PY'
import os
from pathlib import Path
from ui_explorer.synthetic.goal_source import filter_microactions_with_complete_goals, find_latest_task_generation_run
from ui_explorer.synthetic.generation_output import load_generation_run_outputs

workspace = Path(os.environ["WORKSPACE"])
model = os.environ["MODEL"]
variant_count = int(os.environ["GOAL_VARIANT_COUNT"])
base = workspace / "task_generation" / model
for ms in sorted(base.iterdir()):
    if not ms.is_dir():
        continue
    run = find_latest_task_generation_run(workspace, ms.name, model=model)
    if run is None:
        continue
    outputs = load_generation_run_outputs(run)
    keys = set(outputs)
    pending, _ = filter_microactions_with_complete_goals(
        run, keys, outputs, goal_variant_count=variant_count
    )
    if pending:
        print(ms.name)
PY
)

if ((${#PENDING_STATES[@]} == 0)); then
  echo "No macro states with pending goal generation."
  exit 0
fi

echo "Launching ${#PENDING_STATES[@]} tmux session(s) (batch_size=${BATCH_SIZE})"

delay=0
for state_id in "${PENDING_STATES[@]}"; do
  session="${SESSION_PREFIX}-${state_id}"
  log_file="$LOG_DIR/${state_id}.log"
  if tmux has-session -t "$session" 2>/dev/null; then
    echo "skip $session (already running)"
    continue
  fi
  tmux new-session -d -s "$session" \
    "bash -lc 'cd \"$ROOT\" && source .venv/bin/activate && PYTHONPATH=src python scripts/generate_microaction_tasks.py --workspace-root \"$WORKSPACE\" --prompt goal --model \"$MODEL\" --goal-variant-count $GOAL_VARIANT_COUNT --batch-size $BATCH_SIZE --macro-state-id \"$state_id\" 2>&1 | tee \"$log_file\"; echo \"[$state_id] finished with exit=\$?\"'"
  echo "started $session -> $log_file"
  delay=$(python3 -c "print(min(6.0, $delay + 0.4))")
  sleep "$delay"
done

echo "Done. Attach with: tmux attach -t ${SESSION_PREFIX}-<macro_state_id>"
