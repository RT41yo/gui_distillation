# LibreOffice Writer Active-Root Microaction Popup Risk

Generated: 2026-06-07T11:09:35Z
Source scope map: `data/maps/libreoffice_writer/agent_map_active_root_scope.json`
Heuristic: `heuristic-v2`

## Score definitions

| Score | Meaning |
|------:|---------|
| 0 | Likely direct/internal state change only; no extra menu/dialog/popup. |
| 1 | Likely changes visible UI in place without opening another surface. |
| 2 | Likely opens extra menu, dialog, chooser, or popup window. |

## Totals

| Metric | Count |
|--------|------:|
| Microactions | 231 |
| Macro states with microactions | 34 |

## By score

| Score | Label | Count | Share |
|------:|-------|------:|------:|
| 2 | opens extra menu/dialog/popup | 111 | 48.1% |
| 1 | visible UI change in place | 15 | 6.5% |
| 0 | direct/internal state only | 105 | 45.5% |

## By score and role

| Score | menu item | push button | toggle button |
|------:|----------:|------------:|--------------:|
| 2 | 86 | 25 | 0 |
| 1 | 0 | 5 | 10 |
| 0 | 96 | 9 | 0 |

## By score and active-root kind

| Score | main | menu | dialog |
|------:|-----:|-----:|-------:|
| 2 | 20 | 86 | 5 |
| 1 | 11 | 0 | 4 |
| 0 | 9 | 96 | 0 |

## Full classification table

See `active_root_microaction_popup_risk.csv` for the complete 231-row table.
See `active_root_microaction_popup_risk.json` for machine-readable rows plus embedded summaries.

