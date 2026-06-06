# Microaction task generation

Generate synthetic GUI-agent training tasks for LibreOffice Writer microactions visible in the attached screenshot.

The agent reaches this macro state via programmatic navigation (`macro_path`). For each listed microaction:

1. Assign exactly one `task_type` from the list below.
2. Generate diverse tasks for that type. Respect per-microaction task-count guidance (`high`: 10–15, `medium`: 5–10, `low`: 2–4).

Each task needs: `instruction`, `preconditions` (`description` + `extras` key/value pairs), and `expected_outcome` (what changes vs preconditions).

## Macro state

- macro_state_id: `{macro_state_id}`
- macro_path: `{macro_path_text}`
{active_root_line}

## Target microactions

Return exactly `{target_microaction_count}` result object(s) in `microactions` — one per entry below, same `micro_action_id` values, no extras.

```json
{target_microactions_json}
```

## Task types

Pick the best primary fit per microaction:

- `selection_transform` — modify selected text/range (bold, color, case, clear formatting)
- `cursor_format_toggle` — toggle formatting for future typing (bold/italic toggles, lists, formatting marks)
- `paragraph_layout` — alignment, spacing, indent, columns, page style
- `insert_at_cursor` — insert break, table, chart, field, footnote, comment, etc.
- `dialog_open` — verifiable result is opening a named dialog
- `document_analysis` — spell-check, word count, accessibility check, calculate
- `list_manipulation` — promote/demote, move, restart numbering
- `table_structure` — rows/columns, merge/split, protect, sort structure
- `table_content` — cell values, number format, formulas
- `language_spelling_setting` — language, spelling, hyphenation
- `view_or_zoom` — zoom level, page view, pane visibility
- `style_management` — edit/update/create/load styles
- `review_commenting` — comments, track changes, resolved comments
- `availability_check` — verify disabled/unavailable controls without activating them
- `unsafe_or_external_observation` — locate risky/external actions (Save, Print, Help links) without executing

## Rules

1. Return exactly `{target_microaction_count}` microaction objects; IDs must match the target list exactly.
2. Each object: `micro_action_id`, `task_type`, `task` array.
3. Vary substantive changed content across tasks for the same microaction; no near-duplicate setups.
4. If quality limits task count, output fewer tasks for that microaction — never omit the microaction object.
5. Use the screenshot for what is visible/enabled. Do not use cursor location in preconditions.
6. Do not activate unsafe actions (Save, Print, Exit, external links). Use `availability_check` or `unsafe_or_external_observation` instead.
7. Instructions describe agent actions after the environment is prepared; preconditions describe document/selection/state setup.

Return JSON: `microactions` array of `{ micro_action_id, task_type, task }` where each `task` item is `{ instruction, expected_outcome, preconditions }`.
