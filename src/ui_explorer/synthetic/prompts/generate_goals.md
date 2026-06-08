# Microaction user-goal rephrasing (from source tasks)

Generate **short, natural user goals** for LibreOffice Writer microactions visible in the attached screenshot.

Each source task is a one-step local instruction from task mode. Produce multiple realistic rephrasings of the same underlying user intent per source task.

## Macro state

- macro_state_id: `{macro_state_id}`
- source_task_generation_run: `{source_task_generation_run}`

## Target microactions

Generate goals for **every** microaction listed below. Each entry includes `goal_count_required`, `goal_variant_count_required`, `preflight_trajectory_context`, and `source_tasks`.

Use `preflight_trajectory_context` and source-task preconditions only to understand what the user wants — **never** describe starting state or navigation in the goal text.

```json
{target_microactions_json}
```

## Required output inventory

The `microactions` output array must contain exactly `{target_microaction_count}` result object(s), one for each ID below and no others:

```json
{target_microaction_ids_json}
```

## Rules

1. Return exactly `{target_microaction_count}` microaction objects with matching `micro_action_id` values.
2. Each object must include `task_type` and a `goal` array with **exactly one entry per source task** (`goal_count_required`).
3. Every goal item must include `task_index` matching a source task index and a `variants` array.
4. Each `variants` array must contain between 1 and `goal_variant_count_required` entries.
5. Each variant must include `{ goal, expected_outcome }`.
6. Goals must read like short user requests — imperative, polite, or declarative. Vary phrasing and tone across variants.
7. Examples: "Disable spell checking", "Turn off spell checking", "Spell checking should be turned off", "I no longer want spell checking to be enabled".
8. No menu paths, document setup, or "where to start" language in `goal`.
9. For `availability_check` source tasks, phrase the user intent as checking or confirming state, not as agent navigation steps.
10. Do not propose unsafe actions (Save, Print, Exit, external links).

Return JSON: `microactions` array of `{ micro_action_id, task_type, goal }` where each `goal` item is `{ task_index, variants }` and each variant is `{ goal, expected_outcome }`.
