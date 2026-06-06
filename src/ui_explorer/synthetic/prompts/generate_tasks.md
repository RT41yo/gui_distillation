# Microaction task generation (batch per macro state)

You are generating synthetic GUI-agent training task instructions for multiple LibreOffice Writer microactions visible in one macro-state screenshot.

The agent will reach this macro state via programmatic navigation. Each task must be a self-contained natural-language instruction the agent can attempt from the screenshot state.

## Macro state

- macro_state_id: `{macro_state_id}`

## Macro navigation context

```json
{macro_context_json}
```

## Active-root context

```json
{active_root_context_json}
```

## Target microactions

Generate tasks for **every** microaction listed below. Each entry includes its yield tier and task-count guidance.

```json
{target_microactions_json}
```

## Rules

1. Return one result object per listed `micro_action_id`; do not skip or invent ids.
2. Generate instruction-only task strings (no JSON inside tasks, no markdown).
3. Tasks must refer to the specific microaction and be realistic from this macro state screenshot.
4. Do not propose unsafe actions (Save, Print, Exit, file-system dialogs, external links).
5. Vary phrasing across tasks while keeping the same underlying goal.
6. Respect per-microaction task count guidance based on yield tier.

Return JSON matching the required schema: `microactions` array of `{ micro_action_id, task }` objects.
