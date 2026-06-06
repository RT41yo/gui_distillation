# Microaction task generation (batch per macro state)

You are generating synthetic GUI-agent training task specs for multiple LibreOffice Writer microactions visible in one macro-state screenshot.

The agent will reach this macro state via programmatic navigation. For each microaction:

1. Classify it into exactly one **task type** from the list below.
2. Generate diverse tasks appropriate for that type, using the type's example content as inspiration.

Each task must include:

- a self-contained natural-language instruction
- environment preconditions needed to make the task meaningful and verifiable
- an expected outcome describing what should be different after successful completion compared to the preconditions

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

## Required output inventory

The `microactions` output array must contain exactly `{target_microaction_count}` result object(s), one for each ID below and no others:

```json
{target_microaction_ids_json}
```

Returning fewer `microactions` objects is invalid. If you cannot generate the target number of tasks for a microaction, output fewer tasks for that microaction; never omit the microaction object itself.

## Task types

Assign **one** `task_type` per microaction — the best primary fit for what the control does from this macro state. Then generate tasks that match that type.

Use the example actions and content below as guidance for realistic instructions, preconditions, and expected outcomes. Do not copy them verbatim; adapt to the specific microaction.

### 1. `selection_transform`

Modifies already-selected text or a selected range.

Example actions/content: Bold, Italic, Underline, Strikethrough, UPPERCASE, lowercase, Cycle Case, Font Color, Highlight Color, Clear Direct Formatting.

Typical preconditions: `main_edit_text`, `selection`, and optionally current formatting state.

### 2. `cursor_format_toggle`

Toggles formatting or structure that affects future typing rather than existing text.

Example actions/content: Bold, Italic, Superscript, Subscript, Unordered List, Formatting Marks.

Typical preconditions: current toggle state, document content; do not specify cursor location.

### 3. `paragraph_layout`

Paragraph-level layout and spacing.

Example actions/content: Left, Center, Right, Justified, Increase/Decrease Spacing, Increase/Decrease Indent, Paragraph..., Columns..., Watermark..., Page Style...

Typical preconditions: paragraph content, one or more paragraphs, current alignment/spacing if relevant.

### 4. `insert_at_cursor`

Inserts content or structure at the agent's chosen insertion point.

Example actions/content: Page Break, Table, Chart, Text Box, Symbol, Field, Footnote, Endnote, Comment, Section..., Page Number.

Typical preconditions: surrounding text and document structure; the instruction tells the agent where to click or place the insertion.

### 5. `dialog_open`

Main verifiable result is opening a named dialog.

Example actions/content: Character..., Paragraph..., Bullets and Numbering..., Table Properties..., Word Count..., Accessibility Check..., Extension Manager..., Special Character..., Cross-reference...

Expected outcome: the named dialog appears; document content may be unchanged.

### 6. `document_analysis`

Inspects or reports on document content.

Example actions/content: Spelling..., Word Count..., Accessibility Check..., Calculate, Search Commands.

Typical preconditions: text with misspellings, countable words, accessibility issues, formulas, or searchable content.

### 7. `list_manipulation`

Changes list hierarchy, order, or numbering.

Example actions/content: Promote/Demote One Level, Move Up/Move Down, Restart Numbering, Add to List, Insert Unnumbered Entry.

Typical preconditions: numbered or bulleted list with multiple items; instruction identifies the target item.

### 8. `table_structure`

Edits table shape or cell structure.

Example actions/content: Insert Table..., Rows Above/Below, Columns Before/After, Merge Cells, Split Cells..., Protect/Unprotect Cells, Row Height..., Column Width..., Sort...

Typical preconditions: document contains a table, selected cell or range.

### 9. `table_content`

Edits table values or cell formatting.

Example actions/content: Number Format..., Edit Formula, AutoFormat Styles..., Sort...

Typical preconditions: table with concrete values, selected cells, headers.

### 10. `language_spelling_setting`

Language, spelling, or hyphenation settings.

Example actions/content: English (USA), None (Do not check spelling), Reset to Default Language, More..., Hyphenation..., More Dictionaries Online...

Typical preconditions: document text with a known current language or spell-check state.

### 11. `view_or_zoom`

Changes viewport or visible UI chrome, not document content.

Example actions/content: Entire Page, Page Width, Optimal View, 50%, 75%, 100%, 150%, 200%, Comments, Resolved Comments, Styles pane.

Expected outcome: viewport or pane visibility changes.

### 12. `style_management`

Creates, updates, or loads paragraph/character styles.

Example actions/content: Edit Style..., Update Selected Style, New Style from Selection, Load Styles from Template, Manage Styles.

Typical preconditions: styled text, selected paragraph, existing named style.

### 13. `review_commenting`

Comments and review workflows.

Example actions/content: Comment, Comments..., Track Changes → Compare/Merge Document, Resolved Comments.

Typical preconditions: text to comment on, existing comments, or selected text.

### 14. `availability_check`

Verifies disabled, unavailable, or no-op-prone controls without activating risky side effects.

Example actions/content: Cut / Copy / Paste with no selection, Undo / Redo in a blank doc, No Documents in Recent Documents, disabled toolbar buttons.

Expected outcome: control remains disabled, unavailable, or unchanged after verification.

### 15. `unsafe_or_external_observation`

Locates or confirms risky or external actions without performing them.

Example actions/content: Save, Print, Export as PDF/EPUB, Release Notes, Donate to LibreOffice, Get Help Online, Website.

Expected outcome: button or menu item is found and its label/state is confirmed; the action is not executed.

## Rules

1. Return exactly one result object per listed `micro_action_id`; do not skip or invent ids. The set of returned IDs must exactly match the Required output inventory.
2. Each result must include `task_type` (one of the 15 values above) and a `task` array.
3. Choose the single best-fitting `task_type` for each microaction from this screenshot and context. Generate tasks only for that type.
4. Respect per-microaction task count guidance based on yield tier (`high`: 10–15, `medium`: 5–10, `low`: 2–4). Treat these as targets, not hard requirements.
5. **Unique changed content:** every task for the same microaction must differ in the substantive content being changed, applied, inserted, inspected, or verified. Examples:
   - Allowed: one task applies Bold, another applies Italic.
   - Allowed: one task bolds the word "quarterly", another bolds the word "revenue".
   - Not allowed: two tasks both apply Bold to different paraphrases of the same setup.
   - Not allowed: two tasks that only differ in wording but change the same target in the same way.
6. If you cannot produce the target number of tasks while keeping each task's changed content unique and high quality, output **fewer tasks for that same microaction** rather than padding with near-duplicates. This does not permit omitting a microaction.
7. Tasks must refer to the specific microaction and be realistic from this macro state screenshot.
8. Do not propose unsafe actions (Save, Print, Exit, file-system dialogs, external links). For risky buttons, use `unsafe_or_external_observation` or `availability_check` and verify presence/state instead of activating.
9. Prioritize **task diversity**, not paraphrases. Within the assigned `task_type`, vary meaningful dimensions such as:
   - document content shape (plain paragraph, selected word, heading, list, table, footnote area)
   - exact target text, selection, or inserted object
   - current formatting or settings state
   - relevant document structure
   - expected verifier signal
10. Avoid generating many tasks that differ only by wording. If two tasks would exercise the same changed content and verifier, keep only one.
11. Each task must include `preconditions` for environment generation:
    - `description`: concise general description of involved environment elements, such as main edit text window, current selection, document structure, toolbar state, or settings.
    - `extras`: array of free-form key/value entries with concrete values needed to create the environment. Examples: `[{"key": "main_edit_text", "value": "Alpha beta gamma"}, {"key": "selection", "value": "beta"}]`, `[{"key": "paragraph_style", "value": "Heading 1"}]`, `[{"key": "list_items", "value": "Alpha; Beta"}]`.
    - **Do not use cursor location as a precondition.** The agent may click anywhere in the document to reach the target; do not specify `cursor_location`, caret position, insertion point, or similar in `preconditions.description` or `preconditions.extras`. Use document content, selection, structure, and settings instead.
12. Each task must include `expected_outcome`: a free-form description of the state change or observable verifier signal after the instruction succeeds, explicitly contrasted with the preconditions. Examples: selected text becomes bold; spell-check marks disappear; language setting changes from French to English (USA); a dialog opens; the target toolbar button remains disabled.
13. Keep instructions independent from precondition setup. The instruction should describe what the agent should do after the environment is prepared. The instruction may tell the agent where to click or what to select; that navigation is part of the task, not the environment precondition.
14. Assume documents are populated with realistic text unless the microaction specifically requires an empty or minimal document (e.g. some `availability_check` tasks).

Return JSON matching the required schema: `microactions` array of exactly `{target_microaction_count}` `{ micro_action_id, task_type, task }` objects, where `task` is an array of `{ instruction, expected_outcome, preconditions }` objects.
