# Microaction yield classification (per macro state)

You are classifying GUI microactions visible in a LibreOffice Writer macro-state screenshot.

Use the screenshot and structured context below. Every microaction in the candidate list must appear in exactly one bucket.

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

## Candidate microactions visible in this macro state

Each item uses `micro_action_id` (stable action key). Classify every listed id.

```json
{microactions_json}
```

## Yield guidance

```json
{yield_guidance_json}
```

## Rules

1. Assign every candidate `micro_action_id` to exactly one of: **high**, **medium**, or **low**.
2. Base decisions on verifiability, dialog/value potential, and what is visible in the screenshot.
3. Do not invent ids. Do not omit ids. Do not duplicate ids across buckets.
4. Skip unsafe actions (Save, Print, Exit, external links) by placing them in **low** unless clearly high-value and verifiable.

Return JSON matching the required schema with only keys `high`, `medium`, and `low`.
