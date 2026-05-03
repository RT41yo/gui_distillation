# UI Exploration Evaluation Metrics

This document defines a compact set of metrics for comparing different UI exploration approaches. The metrics are intentionally strategy-agnostic: they can be applied to A11Y-first exploration, screenshot-based exploration, MLLM-driven exploration, BFS, DFS, heuristic agents, scripted explorers, or hybrid systems.

The goal is not to prove that one approach is universally better in every dimension, but to make comparison concrete: cost, speed, coverage, correctness, graph quality, and robustness.

## Evaluation setup

To compare approaches fairly, every run should use the same benchmark conditions:

| Parameter | Description |
|---|---|
| Application | Same target app and version, for example GNOME Calculator. |
| Start state | Same initial app state and window size. |
| Budget | Same max steps, max time, or max depth, depending on the experiment. |
| Stop condition | Same rule for stopping, for example “no more actions available”, “time budget reached”, or “N steps completed”. |
| Action definition | Same notion of a UI action: click, type, select, open menu, etc. |
| State definition | Each approach may use its own internal state representation, but evaluation should normalize outputs into comparable graph nodes and edges. |
| Environment | Same display, OS/session, app configuration, and reset policy where possible. |

For the current A11Y-first project, the already available checkpoint is root-level exploration of GNOME Calculator:

```text
root_state_id: 8251e16b481b
root macro actions: 10
confirmed root transitions: 10
nodes: 11
edges: 86
pending edges: 76
model tokens: 0
model cost: 0
```

These values can be used as the first baseline.

---

## Metric 1. Model cost

**Purpose:** Measure direct LLM/MLLM spending.

| Field | Description |
|---|---|
| Name | `model_cost_total` |
| Unit | Currency, for example USD |
| Formula | Sum of all model/API costs during the run |
| Lower is better | Yes |

This is especially important when comparing A11Y-first exploration with screenshot/MLLM-based exploration. If an approach calls a multimodal model on every step, this metric captures that recurring cost. If an approach does not use a model, its value is `0`.

Example interpretation:

```text
A11Y-first: model_cost_total = 0
Screenshot/MLLM: model_cost_total = cost of all MLLM calls
```

This metric is universal because it does not assume any traversal strategy. It only asks how much model inference was used to obtain the final exploration result.

---

## Metric 2. Model token usage

**Purpose:** Measure model usage volume independently of pricing.

| Field | Description |
|---|---|
| Name | `model_tokens_total` |
| Unit | Tokens |
| Formula | input_tokens + output_tokens across all model calls |
| Lower is better | Usually yes |

Pricing changes across providers and models, so token usage is useful as a provider-independent measure. For MLLM approaches, it can also be helpful to track image input units separately if the provider reports them.

Recommended subfields:

```text
model_input_tokens_total
model_output_tokens_total
model_image_inputs_total
model_tokens_total
```

For A11Y-first exploration without LLM calls:

```text
model_tokens_total = 0
```

---

## Metric 3. Total runtime

**Purpose:** Measure wall-clock speed.

| Field | Description |
|---|---|
| Name | `runtime_total_seconds` |
| Unit | Seconds |
| Formula | end_time - start_time |
| Lower is better | Yes, if quality is comparable |

This metric includes everything: application launch, capture, model calls, action execution, waits, graph updates, and recovery steps.

It is important to measure wall-clock time rather than only model latency, because different systems may spend time in different places:

```text
A11Y-first: A11Y capture + click + wait + graph update
Screenshot/MLLM: screenshot + model latency + parsing + click + wait
```

A useful derived metric is:

```text
runtime_per_terminal_edge = runtime_total_seconds / terminal_edges
```

But the primary metric should remain total runtime for the same benchmark budget or stop condition.

---

## Metric 4. Step efficiency

**Purpose:** Measure how many exploration attempts are needed to produce useful graph results.

| Field | Description |
|---|---|
| Name | `terminal_edge_rate` |
| Unit | Ratio |
| Formula | terminal_edges / executed_steps |
| Higher is better | Yes |

Definitions:

```text
executed_steps = number of attempted exploration actions
terminal_edges = edges that ended with a final status
```

Terminal statuses may include:

```text
confirmed
same_state
content_changed
failed_click
failed_navigation
skipped_policy
```

This metric is useful because an explorer may take many steps but produce little confirmed structure. A high terminal edge rate means most steps produce a graph decision.

Example:

```text
executed_steps = 10
terminal_edges = 10
terminal_edge_rate = 1.0
```

This metric is independent of BFS or DFS. It only evaluates how productive each attempted step was.

---

## Metric 5. Action coverage

**Purpose:** Measure how many available actions were actually evaluated.

| Field | Description |
|---|---|
| Name | `action_coverage` |
| Unit | Ratio |
| Formula | terminal_candidate_actions / discovered_candidate_actions |
| Higher is better | Yes |

This metric requires defining the set of candidate actions for a state or benchmark. For A11Y-first, candidates can be `macro_candidate` actions. For screenshot/MLLM approaches, candidates may come from its detected clickable elements or a shared evaluator.

For root-level evaluation:

```text
action_coverage_root = terminal_root_actions / discovered_root_candidate_actions
```

Current A11Y-first root-level result:

```text
discovered_root_candidate_actions = 10
terminal_root_actions = 10
action_coverage_root = 100%
```

This metric is universal if the benchmark clearly defines the candidate action set. It does not require the explorer itself to be BFS.

---

## Metric 6. Confirmed transition yield

**Purpose:** Measure how many attempted actions produced confirmed state transitions.

| Field | Description |
|---|---|
| Name | `confirmed_transition_yield` |
| Unit | Ratio |
| Formula | confirmed_edges / executed_steps |
| Higher is better, with caveats |

This metric answers:

```text
Out of all executed steps, how many produced a confirmed transition to a state?
```

It is not always bad if an action does not produce a new state. Some actions legitimately result in `same_state` or `content_changed`. Therefore this metric should be interpreted together with action coverage and graph quality.

For root-level GNOME Calculator in the current A11Y-first checkpoint:

```text
confirmed_edges = 10
executed_steps = 10
confirmed_transition_yield = 100%
```

For deeper exploration, this metric may naturally decrease, because some actions are toggles, no-ops, or content-only changes.

---

## Metric 7. State discovery count

**Purpose:** Measure how many distinct UI states were discovered.

| Field | Description |
|---|---|
| Name | `states_discovered` |
| Unit | Count |
| Formula | number of unique graph nodes |
| Higher is not always better |

This metric is useful, but it must not be used alone. A noisy explorer can inflate the number of states by treating small focus changes or repeated screenshots as new states.

Recommended companion fields:

```text
states_discovered_total
states_discovered_by_depth
unique_active_root_kinds
```

For the current A11Y-first root-level result:

```text
states_discovered_total = 11
states_discovered_by_depth = {0: 1, 1: 10}
```

This metric shows exploration reach. It should be interpreted together with duplicate/noise metrics.

---

## Metric 8. Failure rate

**Purpose:** Measure operational robustness.

| Field | Description |
|---|---|
| Name | `failure_rate` |
| Unit | Ratio |
| Formula | failed_steps / executed_steps |
| Lower is better | Yes |

Failures include cases where the explorer could not execute or evaluate a step correctly:

```text
failed_click
failed_navigation
invalid_action
invalid_model_output
parse_error
timeout
app_crash
```

For screenshot/MLLM systems, useful sub-metrics include:

```text
invalid_json_rate
hallucinated_action_rate
coordinate_miss_rate
```

For A11Y-first systems, useful sub-metrics include:

```text
a11y_capture_failure_rate
navigation_failure_rate
click_failure_rate
```

A low failure rate is important because failed steps consume budget and may corrupt the graph if not handled explicitly.

---

## Metric 9. Graph status completeness

**Purpose:** Measure whether the produced graph is self-explanatory and auditable.

| Field | Description |
|---|---|
| Name | `edge_status_completeness` |
| Unit | Ratio |
| Formula | edges_with_valid_status / total_edges |
| Higher is better | Yes |

A useful exploration graph should not contain ambiguous edges with missing outcomes. Every edge should have an explicit status, for example:

```text
pending
confirmed
same_state
content_changed
failed_click
failed_navigation
skipped_policy
```

A graph with many `null`, `unknown`, or missing statuses is hard to interpret and hard to compare.

For the A11Y-first graph, this should be close to:

```text
edge_status_completeness = 100%
```

because every edge is represented with a `status` field.

This metric is strategy-independent. Any exploration approach that outputs a graph can be evaluated for status completeness.

---

## Metric 10. Graph noise ratio

**Purpose:** Measure how much irrelevant or duplicated structure appears in the graph.

| Field | Description |
|---|---|
| Name | `graph_noise_ratio` |
| Unit | Ratio |
| Formula | noisy_graph_items / total_graph_items |
| Lower is better | Yes |

This is a practical quality metric. Different explorers may discover many states and edges, but some of them may be noise.

Examples of noisy graph items:

```text
background actions incorrectly attached to an overlay state
repeated states caused by focus-only changes
hallucinated actions that do not exist in the UI
duplicate states representing the same UI context
orphan state artifacts not referenced by the graph
```

For a simple first version, split this into measurable subfields:

```text
overlay_background_edge_count
possible_duplicate_state_count
orphan_state_artifact_count
invalid_action_count
```

Then compute:

```text
graph_noise_ratio = noisy_graph_items / (nodes + edges)
```

For A11Y-first exploration, this metric is especially useful for evaluating `active_root`. If a menu state contains only menu actions, noise is low. If it also contains all background buttons from the main window, noise is high.

This metric may require light manual review or a benchmark oracle for the first version. That is acceptable: graph noise is partly semantic, and automatic detection can be added later.

---

## Recommended comparison table

A compact comparison table can use these 10 metrics:

| # | Metric | Field | Direction | Why it matters |
|---:|---|---|---|---|
| 1 | Model cost | `model_cost_total` | Lower | Captures direct LLM/MLLM spending. |
| 2 | Model token usage | `model_tokens_total` | Lower | Provider-independent model usage. |
| 3 | Total runtime | `runtime_total_seconds` | Lower | End-to-end latency. |
| 4 | Step efficiency | `terminal_edge_rate` | Higher | Shows how productive steps are. |
| 5 | Action coverage | `action_coverage` | Higher | Measures how much of the available UI was evaluated. |
| 6 | Confirmed transition yield | `confirmed_transition_yield` | Higher | Measures how often actions produce confirmed transitions. |
| 7 | State discovery count | `states_discovered` | Contextual | Shows exploration reach. |
| 8 | Failure rate | `failure_rate` | Lower | Measures robustness. |
| 9 | Graph status completeness | `edge_status_completeness` | Higher | Ensures graph is auditable. |
| 10 | Graph noise ratio | `graph_noise_ratio` | Lower | Measures redundant/incorrect graph structure. |

---

## Minimal result schema

Each approach should report results in a common summary format:

```json
{
  "approach": "a11y_first",
  "app": "gnome_calculator",
  "run_id": "...",
  "budget": {
    "max_steps": 10,
    "max_depth": 1,
    "stop_condition": "root_level_complete"
  },
  "raw_counts": {
    "executed_steps": 10,
    "terminal_edges": 10,
    "confirmed_edges": 10,
    "discovered_candidate_actions": 10,
    "terminal_candidate_actions": 10,
    "states_discovered": 11,
    "total_edges": 86,
    "failed_steps": 0,
    "noisy_graph_items": 0
  },
  "cost": {
    "model_cost_total": 0,
    "model_tokens_total": 0
  },
  "latency": {
    "runtime_total_seconds": 0
  },
  "metrics": {
    "terminal_edge_rate": 1.0,
    "action_coverage": 1.0,
    "confirmed_transition_yield": 1.0,
    "failure_rate": 0.0,
    "edge_status_completeness": 1.0,
    "graph_noise_ratio": 0.0
  }
}
```

The same schema can be filled by screenshot/MLLM-based exploration. Some fields, such as `model_cost_total` and `model_tokens_total`, will likely be non-zero there.

---

## Suggested first benchmark

For the first comparison, use a small benchmark that both approaches can run:

```text
Application: GNOME Calculator
Start state: fresh launch, same window size
Goal: build root-level state map
Stop condition: all root-level candidate actions are terminal, or max 20 steps
Reported metrics: all 10 metrics above
```

This benchmark is simple enough to run repeatedly, but already tests important behavior:

```text
finding actions
executing actions
handling menus/popovers/dialogs
recording transitions
avoiding graph noise
tracking cost and latency
```

A strong result for A11Y-first can be summarized as:

```text
A11Y-first completed root-level exploration with 10/10 confirmed root transitions, 11 discovered states, explicit edge statuses, visible pending frontier, and zero model tokens.
```
