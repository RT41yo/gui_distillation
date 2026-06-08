# Microaction user-goal rephrasing (from source tasks)

Generate **short, natural user goals** for LibreOffice Writer microactions. Each source task describes one local UI action; produce multiple realistic rephrasings of the same underlying intent.

## Macro state

- macro_state_id: `{macro_state_id}`
- source_task_generation_run: `{source_task_generation_run}`

## Target microactions

Return exactly `{target_microaction_count}` result object(s) in `microactions` — one per entry below, same `micro_action_id` values, no extras.

Each entry includes `source_tasks` (one-step tasks from task mode) and background context. Use that context only to understand the intent; **do not** put starting state, navigation, or preconditions into the goal text.

```json
{target_microactions_json}
```

## Task types

Use the `task_type` provided for each microaction.

## Rules

1. Return exactly `{target_microaction_count}` microaction objects; IDs must match the target list exactly.
2. Each object: `micro_action_id`, `task_type`, `goal` array.
3. `len(goal)` must equal `goal_count_required` and match `len(source_tasks)`; include every `task_index` from the source tasks exactly once.
4. Each goal item: `{ task_index, variants }` where `variants` is a non-empty array with **at most** `goal_variant_count_required` entries.
5. Each variant: `{ goal, expected_outcome }`.
6. Write goals as brief utterances a real user might say or type — imperative, polite request, or declarative preference. Vary wording and tone across variants.
7. Good examples for the same intent: "Disable spell checking", "Turn off spell checking", "Spell checking should be turned off", "I no longer want spell checking to be enabled".
8. Keep goals short (typically under 15 words). No menu paths, no "open Tools", no "with the document already open", no "from the main window".
9. Do not use deictic phrases like "this item", "active selection", or "current menu".
10. `expected_outcome` should briefly state what success looks like (can mirror the source task outcome).
11. Do not activate unsafe actions (Save, Print, Exit, external links).

Return JSON: `microactions` array of `{ micro_action_id, task_type, goal }` where each `goal` item is `{ task_index, variants }` and each variant is `{ goal, expected_outcome }`.
