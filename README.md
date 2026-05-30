# UI Explorer

A11Y-first UI exploration prototype.

Проект строит карту состояний GUI-приложения на основе A11Y Tree. Скриншоты не используются для построения стратегии exploration. Источник истины — accessibility tree приложения.

Текущая версия реализует:

- захват A11Y Tree приложения в XML;
- парсинг A11Y XML;
- определение активной области взаимодействия (`active_root`);
- извлечение интерактивных действий;
- классификацию действий на `macro_candidate`, `micro_candidate`, `input_candidate`, `ignored`;
- построение A11Y-only state signature;
- инициализацию `graph.json`;
- strict BFS scheduler;
- выполнение одного pending edge с обновлением `graph.json`;
- replay confirmed path для состояний глубины `depth > 0`;
- hard-reset navigation через перезапуск приложения перед exploration step;
- построение карты состояний GNOME Calculator до clean frontier `depth 5`;
- статичную и интерактивную визуализацию графа.

---

## 1. Системные зависимости

Python-зависимости описаны в `pyproject.toml`.

Но часть зависимостей системная и через `pip` не устанавливается:

```bash
sudo apt-get update
sudo apt-get install -y \
  python3-pyatspi \
  xvfb \
  xdotool \
  x11-utils
```

Что для чего нужно:

- `python3-pyatspi` — доступ к AT-SPI / A11Y Tree;
- `xvfb` — виртуальный X display для запуска GUI-приложений в headless-среде;
- `xdotool` — активация окна перед кликом;
- `x11-utils` — утилиты вроде `xdpyinfo`, `xset` для проверки display.

---

## 2. Python environment

Активируй виртуальное окружение.

Пример для текущей среды:

```bash
source ~/gui-distill-venv/bin/activate
cd /mnt/repo
```

Установи проект в editable mode:

```bash
python -m pip install -e ".[dev]"
```

Проверка:

```bash
python -m ui_explorer.cli.doctor
```

Ожидаемый вывод:

```text
ui-explorer setup OK
apps: 1
display: :99
```

---

## 3. Запуск Xvfb

Если виртуальный display `:99` ещё не запущен:

```bash
Xvfb :99 -screen 0 1280x1024x24 -ac &
sleep 1
```

Проверка:

```bash
DISPLAY=:99 xdpyinfo >/dev/null && echo "DISPLAY OK"
```

или:

```bash
DISPLAY=:99 xset q >/dev/null && echo "DISPLAY OK"
```

Проверить запущенные Xvfb процессы:

```bash
pgrep -a Xvfb || true
```

---

## 4. Конфигурация приложения

Приложения описаны в:

```text
config/apps.yaml
```

Текущий пример:

```yaml
apps:
  - app_id: calc
    display_name: GNOME Calculator
    launcher: gnome-calculator
    a11y_name: gnome-calculator
```

Настройки runtime находятся в:

```text
config/settings.yaml
```

---

## 5. Захват A11Y Tree

Запустить приложение и снять A11Y XML:

```bash
DISPLAY=:99 python -m ui_explorer.cli.capture \
  --app calc \
  --display :99 \
  --launch \
  --verbose
```

Ожидаемый результат:

```text
data/maps/calc/_captures/a11y_tree.xml
```

Проверить, что XML не пустой:

```bash
head -40 data/maps/calc/_captures/a11y_tree.xml
grep -c '<element' data/maps/calc/_captures/a11y_tree.xml
```

---

## 6. Инспекция A11Y XML

Посмотреть базовую статистику по A11Y Tree:

```bash
python -m ui_explorer.cli.inspect_a11y \
  data/maps/calc/_captures/a11y_tree.xml \
  --limit 10
```

Пример вывода:

```text
root: application/gnome-calculator
all_nodes: 667
visible_nodes: 150
visible_role_counts:
{
  "combo box": 1,
  "editbar": 1,
  "push button": 109,
  "toggle button": 8
}
```

---

## 7. Определение active root

Active root — это активная область UI, из которой будут извлекаться действия.

Проверить active root для XML:

```bash
python -m ui_explorer.cli.active_root \
  data/maps/calc/_captures/a11y_tree.xml
```

Для обычного стартового состояния ожидаемо:

```json
{
  "kind": "main",
  "role": "frame",
  "name": "Calculator"
}
```

Для меню или popover active root может быть:

```text
kind = menu
kind = dialog
kind = window_overlay
```

---

## 8. Список действий

Вывести все actionable элементы из active root:

```bash
python -m ui_explorer.cli.list_actions \
  data/maps/calc/_captures/a11y_tree.xml \
  --limit 20
```

Вывести только macro candidates:

```bash
python -m ui_explorer.cli.list_actions \
  data/maps/calc/_captures/a11y_tree.xml \
  --kind macro_candidate \
  --limit 30
```

Для GNOME Calculator root-состояния ожидаемо около 10 macro actions:

```text
Mode selection
Primary menu
Decimal
Word Size
Store
Insert Character
Shift Right
Shift Left
Superscript
Subscript
```

---

## 9. State signature

Посчитать A11Y-only подпись состояния:

```bash
python -m ui_explorer.cli.state_signature \
  data/maps/calc/_captures/a11y_tree.xml
```

Пример:

```json
{
  "state_id": "8251e16b481b",
  "macro_hash": "...",
  "content_hash": "...",
  "active_root": {
    "kind": "main",
    "role": "frame",
    "name": "Calculator"
  },
  "macro_action_count": 10,
  "visible_node_count": 150,
  "signature_source": "a11y_only",
  "screenshot_used": false
}
```

---

## 10. Инициализация graph.json

Создать начальный граф из captured A11Y XML:

```bash
python -m ui_explorer.cli.init_graph \
  --app calc \
  --xml data/maps/calc/_captures/a11y_tree.xml
```

Ожидаемый результат:

```json
{
  "graph_path": "data/maps/calc/graph.json",
  "root_state_id": "8251e16b481b",
  "nodes": 1,
  "edges": 10,
  "pending_edges": 10
}
```

После этого будет создан:

```text
data/maps/calc/graph.json
data/maps/calc/states/<state_id>/a11y.xml
```

---

## 11. Инспекция графа

Посмотреть состояние графа:

```bash
python -m ui_explorer.cli.inspect_graph --app calc
```

Посмотреть следующий pending edge по scheduler-у:

```bash
python -m ui_explorer.cli.next_edge --app calc
```

Scheduler использует strict BFS:

```text
1. from_state.depth ASC
2. priority ASC
3. attempts ASC
4. created_order ASC
```

То есть сначала закрываются все transitions из `depth 0`, затем `depth 1`, и так далее.

---

## 12. Пробное выполнение edge без записи в граф

Команда выполняет следующий pending edge, снимает before/after A11Y, считает новое состояние, но не обновляет `graph.json`:

```bash
DISPLAY=:99 python -m ui_explorer.cli.try_edge \
  --app calc \
  --display :99 \
  --verbose
```

Результаты сохраняются во временную директорию:

```text
data/maps/calc/_tmp/try_edge/
```

---

## 13. Выполнение одного exploration step

Команда выполняет следующий pending edge и обновляет `graph.json`:

```bash
DISPLAY=:99 python -m ui_explorer.cli.step_edge \
  --app calc \
  --display :99 \
  --verbose
```

Один запуск = один exploration step.

По умолчанию используется стратегия навигации `hard`:

```text
hard reset app → capture root → replay confirmed path → execute edge → capture after → update graph
```

То есть перед каждым шагом приложение перезапускается из `config/apps.yaml`, затем система проверяет root-состояние и воспроизводит подтверждённый путь до `edge.from_state`. Это делает exploration устойчивым к persistent GUI-состояниям, которые не закрываются через `Escape`.

Старый soft-режим доступен явно:

```bash
DISPLAY=:99 python -m ui_explorer.cli.step_edge \
  --app calc \
  --display :99 \
  --navigation soft \
  --verbose
```

В `soft`-режиме сначала выполняется попытка навигации из текущего live-состояния, а при неудаче используется hard fallback.

На каждом шаге происходит:

1. загрузка `graph.json`;
2. выбор следующего pending edge по strict BFS scheduler;
3. hard reset приложения, если выбран `--navigation hard`;
4. захват root/current A11Y-состояния;
5. replay confirmed path от root до `edge.from_state`;
6. проверка, что достигнут ожидаемый `from_state`;
7. выполнение одного действия;
8. захват A11Y после действия;
9. сравнение before/after;
10. обновление edge status;
11. добавление нового state, если найден новый macro state;
12. seed новых pending edges из active root нового состояния.

---

## 14. BFS exploration workflow

После `init_graph` можно запускать exploration пошагово:

```bash
python -m ui_explorer.cli.next_edge --app calc

DISPLAY=:99 python -m ui_explorer.cli.step_edge \
  --app calc \
  --display :99 \
  --navigation hard \
  --verbose

python -m ui_explorer.cli.inspect_graph --app calc
```

Чтобы автоматически идти до clean frontier заданной глубины, например `depth 5`:

```bash
while true; do
  depth=$(python -m ui_explorer.cli.next_edge --app calc | python -c '
import json,sys
d=json.load(sys.stdin)
e=d.get("next_edge")
print(e.get("from_depth") if e else "done")
')

  echo "next from_depth=$depth"

  if [ "$depth" = "done" ]; then
    echo "No pending edges. Exploration complete."
    break
  fi

  if [ "$depth" -ge 5 ]; then
    echo "Reached clean depth 5 frontier."
    break
  fi

  DISPLAY=:99 python -m ui_explorer.cli.step_edge \
    --app calc \
    --display :99 \
    --navigation hard \
    --max-depth 5 || break
done
```

Интерпретация остановки:

```text
next_edge.from_depth = 5
```

означает, что все pending edges с меньшей глубиной уже обработаны, и scheduler перешёл к frontier глубины 5.

---

## 15. Результат для GNOME Calculator для --max-depth 5

После перехода на hard-reset navigation был построен граф GNOME Calculator до clean frontier `depth 5`.

Текущий результат:

```text
root_state_id: 3eb3742139fc
nodes: 55
edges: 299
completion: partial, pending_edges=54

node_depth_counts:
  0: 1
  1: 9
  2: 11
  3: 17
  4: 9
  5: 8

edge_status_counts:
  confirmed: 230
  pending: 54
  same_state: 15
  failed_navigation: 0
```

Ключевой checkpoint:

```text
next_edge.from_depth = 5
```

Это означает, что exploration чисто закрыл frontier до `depth 4` включительно и перешёл к действиям из состояний глубины 5. Ошибок навигации нет.

Граф уже достаточно большой для использования как статическая карта состояний приложения:

```text
graph.json = source of truth / карта GUI-состояний
states/<state_id>/a11y.xml = сохранённые A11Y snapshots
confirmed edges = проверенные переходы между состояниями
pending edges = frontier для возможного дальнейшего углубления
```

---

## 16. Navigation strategy

Первоначальная soft-навигация через `Escape` оказалась недостаточной для persistent GUI-состояний GNOME Calculator: Binary/Octal/Keyboard/unit-conversion режимы и dialog states не всегда возвращались к root-состоянию через `Escape`.

Текущая основная стратегия — hard reset перед каждым edge:

```text
1. закрыть процесс приложения по launcher из config/apps.yaml;
2. запустить приложение заново на нужном DISPLAY;
3. дождаться A11Y root;
4. проверить root_state_id;
5. воспроизвести confirmed path от root до target from_state;
6. выполнить исследуемое действие.
```

Плюсы hard-reset navigation:

- каждый edge стартует из контролируемого baseline;
- exploration меньше зависит от остаточного live-состояния GUI;
- confirmed path replay становится воспроизводимым;
- `failed_navigation` исчезает для проверенного depth-5 прогона;
- стратегия не захардкожена под калькулятор: используется launcher из `config/apps.yaml`.

Soft-navigation сохранена как дополнительный режим для отладки:

```bash
DISPLAY=:99 python -m ui_explorer.cli.step_edge \
  --app calc \
  --display :99 \
  --navigation soft \
  --verbose
```

---

## 17. Тесты

Запустить unit tests:

```bash
pytest -q
```

Ожидаемый текущий результат:

```text
41 passed
```

---

## 18. Полезные команды диагностики

Проверить Xvfb:

```bash
pgrep -a Xvfb || true
```

Проверить display:

```bash
DISPLAY=:99 xset q >/dev/null && echo "DISPLAY OK"
```

Проверить, запущен ли калькулятор:

```bash
pgrep -a gnome-calculator || true
```

Остановить калькулятор:

```bash
pkill -f gnome-calculator || true
```

Перезапустить приложение и снять новый A11Y capture:

```bash
pkill -f gnome-calculator || true
DISPLAY=:99 python -m ui_explorer.cli.capture \
  --app calc \
  --display :99 \
  --launch \
  --verbose
```

Важно: `capture --launch` не пересоздаёт граф.  
`init_graph` пересоздаёт `graph.json` с нуля.

---

## 19. Очистка orphan state directories

Во время разработки в `data/maps/calc/states/` могут остаться директории состояний, которых уже нет в `graph.json`.

Проверить orphan directories:

```bash
python - <<'PY'
import json
from pathlib import Path

base = Path("data/maps/calc")
g = json.loads((base / "graph.json").read_text())

graph_nodes = set(g["nodes"].keys())
state_dirs = {p.name for p in (base / "states").iterdir() if p.is_dir()}

print("nodes in graph:", len(graph_nodes))
print("state dirs:", len(state_dirs))
print("orphan dirs:", sorted(state_dirs - graph_nodes))
print("missing dirs:", sorted(graph_nodes - state_dirs))
PY
```

Удалять orphan directories вручную стоит только после проверки.

---

## 20. Current project status

Implemented:

- A11Y capture;
- A11Y parser;
- active root resolver;
- action extraction;
- action classification policy;
- A11Y-only state signature;
- graph models and store;
- strict BFS scheduler;
- one-edge execution with graph update;
- replay confirmed path navigation for `depth > 0`;
- hard-reset navigation before edge execution;
- soft-navigation fallback mode;
- complete GNOME Calculator exploration under current macro-action policy;
- static graph visualization;
- extra graph visualizations: Sankey, frontier chart, metro map;
- interactive Cytoscape.js graph visualization prototype.

Current GNOME Calculator checkpoint:

```text
nodes: 61
edges: 362
confirmed: 347
same_state: 15
pending: 0
failed_navigation: 0
max_depth: 7
root_state_id: e14ee107e46f
```

Not implemented yet / next steps:

- MCP/graph-tool API for Computer-use agent navigation;
- compact state/action indexes for agent memory;
- semantic state labels and goal aliases;
- advanced transition classification;
- built-in autonomous exploration runner with configurable stopping policy;
- broader validation on non-calculator applications.

---

## 21. Эксперименты с другими приложениями

Помимо GNOME Calculator были проверены другие GUI-приложения, чтобы убедиться, что подход не захардкожен под калькулятор.

Краткий результат:

```text
VLC:
  GUI запускается, X11-окна видны, но AT-SPI отдаёт только application/vlc с childCount=0.
  В текущей среде приложение непригодно для A11Y-only exploration.

Thunderbird:
  X11-окна появляются, но приложение не регистрируется в AT-SPI registry.
  В текущей среде приложение непригодно без дополнительной настройки accessibility/DBus.

gedit:
  A11Y Tree полноценный.
  Root-level exploration успешно построил отдельный граф в data/maps/gedit/.
  Подтверждены root-level переходы для Menu и Open.

Nautilus:
  A11Y Tree полноценный.
  Эксперимент выявил важную проблему active_root detection: постоянный sidebar был ошибочно принят за overlay.
  После уточнения эвристики sidebar исключается из overlay-кандидатов.
  Также выявлено ограничение reset-to-root: Escape не всегда возвращает приложение в root-состояние.
```

Выводы:

- проект не привязан к calc: gedit успешно прошёл root-level exploration;
- не каждое GUI-приложение отдаёт полезный AT-SPI tree в текущей среде;
- для приложений вроде Nautilus нужен более надёжный reset strategy, например fallback через restart приложения;
- текущий универсальный следующий шаг — реализовать replay-path navigation для depth > 0.


Для базовой визуализации графа используется CLI-команда:

```bash
ui-explorer-visualize-graph --app calc
ui-explorer-visualize-graph --app gedit
ui-explorer-visualize-graph --app nautilus
```

---

## 22. Визуализация графа

Для маленьких графов достаточно статичного PDF:

```bash
ui-explorer-visualize-graph --app calc
```

Ожидаемый результат:

```text
data/maps/calc/graph.pdf
```

Для более крупного графа GNOME Calculator на `depth > 5` статичный PDF становится плотным, поэтому используются дополнительные представления:

```bash
python -m ui_explorer.cli.visualize_graph_extra --app calc
python -m ui_explorer.cli.visualize_graph_interactive --app calc
```

Ожидаемые файлы:

```text
data/maps/calc/graph_sankey.html
data/maps/calc/graph_frontier.pdf
data/maps/calc/graph_metro.pdf
data/maps/calc/graph_interactive.html
```

Назначение:

```text
graph.pdf              полный технический layered graph
graph_metro.pdf        упрощённая карта confirmed-переходов
graph_frontier.pdf     pending frontier по состояниям
graph_sankey.html      интерактивный flow depth/kind
graph_interactive.html полный интерактивный Cytoscape.js graph
```

Практическое правило:

- для отчёта использовать `graph_metro.pdf`, `graph_frontier.pdf` и summary;
- полный `graph.pdf` хранить как техническое приложение;
- для анализа большого графа использовать `graph_interactive.html`.

---

## 23. Agent-facing UI map

Для Computer-use агента сырой `graph.json` слишком подробный и содержит только проверенные переходы. Поэтому добавлен компактный файл:

```text
data/maps/<app>/agent_map.json
```

Он строится из:

```text
data/maps/<app>/graph.json
data/maps/<app>/states/*/a11y.xml
```

Разделение такое:

```text
graph.json      — внутренний граф exploration / source of truth
agent_map.json  — компактная карта для агента
```

### Зачем нужен agent_map.json

Текущий граф Calculator завершён в рамках A11Y macro-action policy:

```text
nodes: 61
edges: 362
confirmed: 347
same_state: 15
pending: 0
failed_navigation: 0
max_depth: 7
```

Но часть важных UI-элементов есть в A11Y-снимках, хотя не стала проверенными переходами графа. Например:

```text
Frequency
Hertz
Currency
Australian Dollar
Periodic Payment
Periodic Interest Rate
```

`agent_map.json` сохраняет такие элементы как знания об интерфейсе, не выдавая агенту плохие координаты.

### Структура

В каждом состоянии есть два основных блока:

```text
verified_actions — проверенные действия с переходами
observed_items   — найденные, но непроверенные UI-элементы
```

Пример `verified_actions`:

```json
{
  "role": "combo box",
  "name": "Decimal",
  "status": "verified",
  "method": "bbox_click",
  "bbox": [23, 257, 126, 34],
  "to_state": "..."
}
```

Пример `observed_items`:

```json
{
  "role": "menu item",
  "name": "Hertz",
  "status": "observed_unverified",
  "states": ["enabled", "sensitive", "visible"],
  "parent_path_tail": ["filler", "combo box", "menu", "menu/Frequency"]
}
```

Важно: для `observed_items` поле `bbox` не записывается. Если элемент не был проверен как исполняемый переход, агент не получает ни `bbox: null`, ни невалидные координаты вида `[-2147483648, ...]`.

### Команды

Построить карту:

```bash
python -m ui_explorer.cli.build_agent_map --app calc
```

Ожидаемый результат:

```json
{
  "ok": true,
  "app_id": "calc",
  "output": "data/maps/calc/agent_map.json",
  "states": 61,
  "edges": 362,
  "item_index": 299
}
```

Посмотреть summary:

```bash
python -m ui_explorer.cli.inspect_agent_map --app calc
```

Поиск по подстроке:

```bash
python -m ui_explorer.cli.inspect_agent_map --app calc --query Hertz
```

Точный поиск:

```bash
python -m ui_explorer.cli.inspect_agent_map --app calc --query Hertz --exact
```

Поиск с деталями:

```bash
python -m ui_explorer.cli.inspect_agent_map \
  --app calc \
  --query Hertz \
  --exact \
  --details \
  --limit 5
```

Посмотреть конкретное состояние:

```bash
python -m ui_explorer.cli.inspect_agent_map \
  --app calc \
  --state e14ee107e46f
```

### Проверка формата

Убедиться, что `observed_items` не содержат `bbox`:

```bash
python - <<'PY'
import json
from pathlib import Path

m = json.loads(Path("data/maps/calc/agent_map.json").read_text())

bad = []
for sid, state in m["states"].items():
    for item in state.get("observed_items", []):
        if "bbox" in item:
            bad.append((sid, item))

print("observed_items_with_bbox:", len(bad))
assert not bad
PY
```

Проверить, что verified actions имеют bbox, если он подтверждён:

```bash
python - <<'PY'
import json
from pathlib import Path

m = json.loads(Path("data/maps/calc/agent_map.json").read_text())

with_bbox = 0
without_bbox = 0

for state in m["states"].values():
    for item in state.get("verified_actions", []):
        if "bbox" in item:
            with_bbox += 1
        else:
            without_bbox += 1

print("verified_with_bbox:", with_bbox)
print("verified_without_bbox:", without_bbox)
PY
```

### Интерпретация для агента

Агент должен читать карту так:

```text
verified_actions — можно использовать для навигации по графу.
observed_items   — знания о возможностях UI, но не готовые проверенные переходы.
```

Например `Hertz` как `observed_unverified` означает: элемент известен и относится к `Frequency`, но текущий граф не содержит проверенного bbox-click перехода для его выбора.

### Ограничения

`agent_map.json` улучшает семантическое покрытие, но пока не исполняет latent/invalid-bbox элементы.

Оставшиеся задачи:

```text
- extended policy для видимых push buttons;
- классификация push buttons на function/content/tool/window-control;
- обработка content-only transitions без раздувания графа;
- keyboard navigation для menu/list items с плохим bbox;
- capability summaries поверх observed_items и verified_actions.
```

### Тесты

Проверить новые тесты:

```bash
pytest tests/unit/test_build_agent_map.py tests/unit/test_inspect_agent_map.py -q
```

Проверить всё:

```bash
pytest -q
```

## 24. Улучшения Agent-facing UI map

Agent-facing карта была расширена, чтобы агенту было проще понимать не только проверенные переходы графа, но и видимое содержимое каждого состояния.

Раньше основными блоками были:

```text
verified_actions — проверенные действия и переходы
observed_items   — все найденные видимые A11Y-элементы состояния
```

Этого оказалось недостаточно для overlay/menu-состояний. Например, при открытии `Word Size` полный `observed_items` содержит не только пункты `64-bit / 32-bit / 16-bit / 8-bit`, но и фоновые элементы калькулятора. Поэтому добавлены новые agent-facing поля.

### Новые поля состояния

В каждом `states.<state_id>` теперь могут быть:

```text
primary_incoming_action
incoming_actions
scoped_observed_items
scoped_observed_source
scoped_observed_confidence
delta_base_state
delta_observed_items
state_capabilities
state_capabilities_source
```

Назначение:

```text
primary_incoming_action — основной локальный вход в состояние.
incoming_actions        — все подтверждённые входы в состояние.
observed_items          — полный видимый A11Y-контекст состояния.
delta_observed_items    — диагностическая разница относительно ближайшего incoming/base state.
scoped_observed_items   — best-effort важные видимые элементы активной части состояния.
state_capabilities      — главный список для агента: verified actions + доверенные scoped items.
```

Главное правило чтения:

```text
Для агента сначала читать state_capabilities.
Для навигации использовать verified_actions.
observed_items и delta_observed_items считать диагностическими слоями.
```

### Почему появился scoped слой

Для overlay/menu A11Y snapshot часто содержит фон основного окна. Например:

```text
Word Size overlay:
  observed_items = root UI + Word Size popup
  scoped_observed_items = 64-bit, 32-bit, 16-bit, 8-bit
```

Для `Primary menu`:

```text
verified_actions:
  Number format
  Automatic
  Fixed
  Scientific
  Engineering

scoped_observed_items:
  New Window
  Preferences
  Keyboard Shortcuts
  Help
  About Calculator
```

То есть `scoped_observed_items` пытается показать именно важное содержимое состояния, а не весь сырой A11Y-контекст.

### Confidence и source

Так как текущий `graph.json` пока не хранит точный active-root selector/path для каждого состояния, scoped слой строится best-effort.

Примеры источников:

```text
observed_items_main_root
delta_observed_items_overlay_hint
fallback_observed_items
unresolved
```

Примеры confidence:

```text
high   — main/root state, scoped примерно равен видимому main UI.
medium — overlay/menu, scoped получен из delta hints.
low    — точного scoped выделения нет, используется fallback.
```

Если `scoped_observed_confidence = low`, такие элементы не добавляются напрямую в `state_capabilities`, чтобы не загрязнять agent-facing слой фоновым UI.

### State capabilities

`state_capabilities` — основной слой для агента.

Он собирается так:

```text
state_capabilities =
  verified_actions
  + scoped_observed_items, если confidence не low
  + delta_observed_items, если scoped confidence low
```

Пример для `Mode selection`:

```text
Basic
Advanced
Financial
Programming
Keyboard
```

Пример для `Word Size`:

```text
64-bit
32-bit
16-bit
8-bit
```

Пример для `Programming/Binary` main state:

```text
Mode selection
Primary menu
Binary
Word Size
Store
Insert Character
Shift Left / Shift Right
Superscript / Subscript
AND / OR / XOR / NOT
ones / twos
A-F, 0-9, bit grid
```

### Items + refs

Чтобы карта не раздувалась повторением одинаковых observed-элементов, используется структура `items + refs`.

Верхний уровень:

```json
"items": {
  "<item_id>": {
    "role": "push button",
    "name": "Preferences",
    "status": "observed_unverified"
  }
}
```

В состоянии:

```json
"scoped_observed_items": [
  {"ref": "<item_id>", "role": "push button", "name": "Preferences"}
]
```

Это уменьшает размер карты и делает связи между состояниями и элементами явными.

### Интерактивная визуализация agent map

Построить HTML-визуализацию:

```bash
python -m ui_explorer.cli.visualize_agent_map --app calc
```

Ожидаемый файл:

```text
data/maps/calc/agent_map.html
```

Переключатели сверху:

```text
verified actions — проверенные переходы между состояниями.
scoped items     — best-effort важные видимые элементы состояния.
all observed     — полный сырой visible A11Y-контекст.
delta hints      — диагностическая разница относительно base state.
```

Практический режим по умолчанию:

```text
verified actions: ON
scoped items: ON
all observed: OFF
delta hints: OFF
```

Так граф остаётся читаемым и показывает agent-facing слой без лишнего шума.

### Диагностика карты

Пересобрать карту:

```bash
python -m ui_explorer.cli.build_agent_map --app calc
```

Посмотреть состояние:

```bash
python -m ui_explorer.cli.inspect_agent_map \
  --app calc \
  --state 3b4bc848561d \
  --limit 50
```

Поиск элемента:

```bash
python -m ui_explorer.cli.inspect_agent_map \
  --app calc \
  --query Hertz \
  --exact \
  --details \
  --limit 5
```

Проверить основные counters:

```bash
python - <<'PY'
import json
from pathlib import Path
from collections import Counter

m = json.loads(Path("data/maps/calc/agent_map.json").read_text())

print("schema:", m.get("schema_version"))
print("states:", len(m["states"]))
print("items:", len(m["items"]))
print("root:", m.get("root_state_id"))
print("summary:", json.dumps(m.get("summary", {}), indent=2, ensure_ascii=False))

print("scoped confidence:", Counter(
    s.get("scoped_observed_confidence")
    for s in m["states"].values()
))
print("scoped source:", Counter(
    s.get("scoped_observed_source")
    for s in m["states"].values()
))
PY
```

### Как читать состояние

Рекомендуемый порядок:

```text
1. primary_incoming_action — как это состояние обычно открывается.
2. state_capabilities      — что агенту полезно в этом состоянии.
3. verified_actions        — куда из этого состояния есть подтверждённые переходы.
4. scoped_observed_items   — важные видимые элементы активной области.
5. all observed            — полный сырой контекст, только для отладки.
6. delta hints             — диагностическая подсказка, особенно для overlay/menu.
```

Пример строки:

```text
e14ee107e46f -- Primary menu → this confirmed
```

означает:

```text
из состояния e14ee107e46f нажали Primary menu,
и результатом стало текущее состояние;
переход подтверждён exploration.
```

### Известные ограничения

Текущий scoped слой — best-effort. Для некоторых menu/combo states возможны неоднозначности, если `active_root` в `graph.json` назван по внутреннему пункту меню, а не по настоящему root меню.

Пример обнаруженной проблемы:

```text
combo box Degrees открывает меню категорий:
Angle / Length / Speed / ... / Currency

но graph metadata может назвать state как Currency,
потому Currency является пунктом внутри меню.
```

Это указывает на будущую задачу: улучшить формирование `graph.json`, чтобы exploration сохранял более точный active-root selector/path/bbox для menu и overlay states.

Пока безопасный agent-facing слой — это `state_capabilities`, а не raw `label` или полный `observed_items`.

### Следующие шаги

```text
- улучшить active_root resolver в exploration;
- сохранять точный selector/path/bbox active root в graph.json;
- различать menu root и menu item/submenu при label state;
- добавить runtime pathfinding current_state → target_state;
- не хранить один глобальный shortest path from root как истину для агента;
- расширить тесты для scoped/capabilities/menu-combo cases.
```

# 25. LibreOffice Writer: доработка exploration и воспроизводимый прогон для завершения второго уровня

Этот раздел фиксирует актуальное состояние LibreOffice Writer exploration после доработок `active_root`, `step_edge`, `action_policy.py` и добавления screenshot capture для каждого состояния.

Раздел заменяет предыдущие черновые разделы про top-level Writer exploration и отдельное завершение второго уровня.

## 25.1. Цель

Построить воспроизводимый `A11Y-first` graph для LibreOffice Writer:

- подтвердить Writer root state;
- раскрыть все top-level menu states;
- раскрыть выбранные безопасные submenu/dialog states из `depth=1`;
- остановиться до выполнения переходов из `depth=2`;
- сохранить для каждого состояния:
  - `a11y.xml`;
  - `screenshot.png`.

Итоговая граница exploration:

```text
depth 0 = Writer root
depth 1 = top-level меню Writer
depth 2 = безопасные submenu/dialog states из top-level меню
from_depth = 2 = frontier следующего уровня, не выполняем
```

## 25.2. Что было доработано

### Nested submenu active root

Исправлена логика `active_root` для вложенных submenu.

Теперь вложенные submenu определяются как самостоятельные состояния:

```text
Edit → Paste Special     active_root = Paste Special
Edit → Selection Mode    active_root = Selection Mode
```

Раньше такие состояния могли отображаться как повторное состояние `Edit`, из-за чего depth-2 submenu наследовали title/actions родительского меню.

### Live bbox execution в `step_edge`

`step_edge` больше не кликает по сохранённому `bbox` из `graph.json`.

Перед выполнением edge action заново ищется в текущем `before.xml` по:

```text
role
name
description
```

После этого используется актуальный `live_bbox`.

Это исправило проблему, когда LibreOffice после relaunch смещался, сохранённые координаты устаревали, а top-level menu click давал `same_state`.

### Policy вместо ручных skip

Ручные `skipped_policy` решения перенесены в `action_policy.py`.

Теперь автоматически отсекаются:

- root toolbar/sidebar controls: `Open`, `Bookmark`, `Hyperlink`, `Print Preview`, `Menu`, `Find and Replace`, `Track Changes Functions`;
- небезопасные file/document actions: `Save`, `Print`, `Exit LibreOffice`, `Send`, `Digital Signatures`;
- content-changing submenus: `Formatting Mark`, `Header and Footer`, `Table of Contents and Index`, `Delete`, `Update`, `Macros`;
- произвольные `menu item` внутри opened menu по умолчанию не становятся macro transitions.

### Context-aware `Properties...`

`Properties...` сделан context-aware:

```text
File → Properties...      разрешён
Table → Properties...     не разрешён
```

Это убрало ложное состояние, где `Table → Properties...` без выбранной таблицы возвращало снова `Table`, а не открывало ожидаемый dialog.

### Screenshot capture для состояний

Добавлен best-effort screenshot capture.

Теперь при построении graph для каждого подтверждённого состояния сохраняются:

```text
data/maps/libreoffice_writer/states/<state_id>/a11y.xml
data/maps/libreoffice_writer/states/<state_id>/screenshot.png
```

Скриншоты сохраняются:

- для root state во время `init_graph`;
- для новых confirmed states во время `step_edge`;
- рядом с `a11y.xml` в папке соответствующего state.

Screenshot capture не должен ломать exploration: если скриншот не снялся, graph generation должен продолжаться.

## 25.3. Актуальный clean checkpoint

После clean rebuild с новой policy, context-aware `Properties...` и screenshot capture:

```text
app_id = libreoffice_writer
root_state_id = 36427b830db2

states = 39
screenshots = 39

depth 0 = 1
depth 1 = 11
depth 2 = 27
```

Проверка screenshots:

```text
states:      39
screenshots: 39
```

Проверка `Properties...`:

```text
from = File
from_depth = 1
status = confirmed
to = bfbd29b4b754
reason = macro signature changed
```

`Table → Properties...` в clean checkpoint больше не появляется как confirmed transition.

## 25.4. Подтверждённые состояния

### depth 0

```text
Untitled 1 - LibreOffice Writer
```

### depth 1

```text
File
Edit
View
Insert
Format
Styles
Table
Form
Tools
Window
Help
```

### depth 2

```text
About LibreOffice
Align Text
AutoCorrect
Convert
Export As
Go to Page
Grid and Helplines
Insert
Language
Lists
More Breaks
New
Options - LibreOffice - User Data
Paste Special
Properties of “Untitled 1”
Recent Documents
Rulers
Scrollbars
Select
Selection Mode
Size
Spacing
Templates
Text
Toolbars
Track Changes
Zoom
```

## 25.5. Семантика leaf states и observation layer

`No outgoing edges` у submenu-ноды не означает, что состояние пустое.

Это означает:

```text
состояние достигнуто и подтверждено,
но текущая safe policy не выбрала дальнейшие macro transitions
```

Видимые элементы такого состояния остаются в A11Y snapshot и должны отображаться в observation layer agent-facing карты.

Пример:

```text
Node: Export As
Transitions:
  none

Observation:
  Export Directly as PDF
  Export as PDF...
  Export as EPUB...
  ...
```

То есть graph layer и observation layer разделены:

```text
graph / transitions:
  только выбранные macro transitions

observation / UI inventory:
  видимые элементы active_root, даже если они не являются outgoing edges

screenshot layer:
  screenshot.png для визуальной проверки состояния
```

## 25.6. Правила остановки

Для завершения второго уровня используется guard:

```text
from_depth = 0  выполнять
from_depth = 1  выполнять
from_depth = 2  остановиться
```

Если `next_edge.from_depth = 2`, следующий шаг уже начнёт третий уровень exploration.

## 25.7. Запуск с нуля

### 1. Подготовить окружение

```bash
source ~/gui-distill-venv/bin/activate
cd /mnt/repo
```

```bash
pgrep -a Xvfb || Xvfb :99 -screen 0 1280x1024x24 -ac >/tmp/xvfb99.log 2>&1 &
sleep 1
env DISPLAY=:99 xset q >/dev/null && echo "DISPLAY OK"
```

### 2. Очистить старый graph/state/tmp

```bash
mkdir -p data/maps/libreoffice_writer/checkpoints

cp data/maps/libreoffice_writer/graph.json \
   data/maps/libreoffice_writer/checkpoints/graph_before_clean_rebuild.json 2>/dev/null || true

rm -f data/maps/libreoffice_writer/graph.json
rm -rf data/maps/libreoffice_writer/states
rm -rf data/maps/libreoffice_writer/_tmp
```

### 3. Перезапустить Writer

```bash
pkill -9 -f libreoffice || true
pkill -9 -f soffice || true
sleep 2

rm -rf /tmp/lo-ui-explorer-writer-profile-clean
rm -rf ~/.config/libreoffice/4/user/backup/*
rm -f ~/.config/libreoffice/4/user/.lock 2>/dev/null || true

SAL_USE_VCLPLUGIN=gtk3 env DISPLAY=:99 libreoffice --writer --norestore --nofirststartwizard \
  -env:UserInstallation=file:///tmp/lo-ui-explorer-writer-profile-clean \
  >/tmp/libreoffice_writer.log 2>&1 &

sleep 20

env DISPLAY=:99 python scripts/list_atspi_apps.py
```

Ожидаем:

```text
name='soffice' role='application'
  child[0] name='Untitled 1 - LibreOffice Writer' role='frame'
```

Если появился `Tip of the Day`, recovery dialog или alert:

```bash
env DISPLAY=:99 xdotool key Escape
sleep 1
env DISPLAY=:99 python scripts/list_atspi_apps.py
```

### 4. Capture root

```bash
env DISPLAY=:99 python -m ui_explorer.cli.capture \
  --app libreoffice_writer \
  --display :99 \
  --timeout 30 \
  --verbose
```

Проверить root:

```bash
python -m ui_explorer.cli.active_root \
  data/maps/libreoffice_writer/_captures/a11y_tree.xml

python -m ui_explorer.cli.state_signature \
  data/maps/libreoffice_writer/_captures/a11y_tree.xml

python -m ui_explorer.cli.list_actions \
  data/maps/libreoffice_writer/_captures/a11y_tree.xml \
  --kind macro_candidate \
  --limit 80
```

Перед `init_graph` обязательно проверить:

```text
active_root.kind = main
active_root.role = frame
```

Не инициализировать graph из открытого меню, dialog или alert.

### 5. Init graph + root screenshot

```bash
env DISPLAY=:99 python -m ui_explorer.cli.init_graph \
  --app libreoffice_writer \
  --xml data/maps/libreoffice_writer/_captures/a11y_tree.xml \
  --display :99
```

Проверить, что root screenshot появился:

```bash
find data/maps/libreoffice_writer/states -name screenshot.png | head

echo "states:"
find data/maps/libreoffice_writer/states -mindepth 1 -maxdepth 1 -type d | wc -l

echo "screenshots:"
find data/maps/libreoffice_writer/states -mindepth 2 -maxdepth 2 -name screenshot.png | wc -l
```

Проверить graph:

```bash
python -m ui_explorer.cli.inspect_graph --app libreoffice_writer
python -m ui_explorer.cli.next_edge --app libreoffice_writer
```

## 25.8. Guarded soft-прогон до границы второго уровня

Для Writer предпочтительно использовать `--navigation soft`, потому hard relaunch LibreOffice иногда нестабилен и может не зарегистрироваться в AT-SPI даже за 30 секунд.

```bash
for i in $(seq 1 80); do
  echo "===== GUARDED STEP $i ====="

  DEPTH=$(python - <<'PY'
import json
import subprocess

raw = subprocess.check_output(
    ["python", "-m", "ui_explorer.cli.next_edge", "--app", "libreoffice_writer"],
    text=True,
)
data = json.loads(raw)
edge = data.get("next_edge")
if edge is None:
    print("NONE")
else:
    print(edge.get("from_depth"))
PY
)

  echo "next_edge.from_depth=$DEPTH"

  if [ "$DEPTH" = "NONE" ]; then
    echo "No pending edge. Stop."
    break
  fi

  if [ "$DEPTH" -ge 2 ]; then
    echo "Reached depth >= 2 frontier. Stop before entering depth 3."
    break
  fi

  env DISPLAY=:99 python -m ui_explorer.cli.step_edge \
    --app libreoffice_writer \
    --display :99 \
    --navigation soft \
    --hard-reset-wait 30 \
    --verbose || break

  python -m ui_explorer.cli.inspect_graph --app libreoffice_writer
  python -m ui_explorer.cli.next_edge --app libreoffice_writer
done
```

## 25.9. Проверки после остановки

### Inspect graph

```bash
python -m ui_explorer.cli.inspect_graph --app libreoffice_writer
python -m ui_explorer.cli.next_edge --app libreoffice_writer
```

Ожидаем:

```text
next_edge.from_depth = 2
```

### Проверить screenshots

```bash
echo "states:"
find data/maps/libreoffice_writer/states -mindepth 1 -maxdepth 1 -type d | wc -l

echo "screenshots:"
find data/maps/libreoffice_writer/states -mindepth 2 -maxdepth 2 -name screenshot.png | wc -l

find data/maps/libreoffice_writer/states -name screenshot.png | head
```

Ожидаем для актуального clean checkpoint:

```text
states:      39
screenshots: 39
```

### Проверить `Properties...`

```bash
python - <<'PY'
import json
from pathlib import Path

g = json.loads(Path("data/maps/libreoffice_writer/graph.json").read_text())

for e in g["edges"].values():
    a = e.get("action", {})
    if a.get("name") == "Properties...":
        n = g["nodes"].get(e.get("from_state"), {})
        print(
            "from=", n.get("label"),
            "from_depth=", n.get("depth"),
            "status=", e.get("status"),
            "to=", e.get("to_state"),
            "reason=", e.get("reason"),
        )
PY
```

Ожидаем:

```text
from= File
from_depth= 1
status= confirmed
```

Не должно быть confirmed transition:

```text
from= Table
name= Properties...
```

### Проверить labels depth-2 submenu

```bash
python - <<'PY'
import json
from pathlib import Path

g = json.loads(Path("data/maps/libreoffice_writer/graph.json").read_text())

for sid, node in sorted(
    g["nodes"].items(),
    key=lambda x: (x[1].get("depth", 0), x[1].get("label", ""), x[0]),
):
    print(
        sid,
        "depth=", node.get("depth"),
        "label=", node.get("label"),
        "active_name=", node.get("active_root", {}).get("name"),
    )
PY
```

Проверить, что nested submenu отображаются как самостоятельные состояния, например:

```text
Paste Special
Selection Mode
```

а не как повторный `Edit`.

## 25.10. Сохранить checkpoint и визуализации

```bash
mkdir -p data/maps/libreoffice_writer/checkpoints

cp data/maps/libreoffice_writer/graph.json \
   data/maps/libreoffice_writer/checkpoints/graph_depth2_with_screenshots.json
```

```bash
python -m ui_explorer.cli.visualize_graph_interactive \
  --app libreoffice_writer \
  --output data/maps/libreoffice_writer/graph_depth2_with_screenshots.html

python -m ui_explorer.cli.visualize_graph \
  --app libreoffice_writer \
  --output data/maps/libreoffice_writer/graph_depth2_with_screenshots.pdf
```

## 25.11. Текущие ограничения

1. **Dialog controls пока остаются frontier третьего уровня.**

   В clean checkpoint pending на `from_depth=2` в основном содержит:

   ```text
   check box
   OK
   Cancel
   Help
   ```

   Это ожидаемо: dialog был достигнут как depth-2 state, но его controls ещё не классифицированы как observation-only.

2. **Menu leaf states не раскрывают menu items в transitions.**

   Это сделано намеренно. Их элементы должны попадать в observation layer, а не в graph transitions.

3. **Hard reset LibreOffice нестабилен.**

   Для полного прогона Writer предпочтителен `--navigation soft`. Hard reset можно использовать точечно, но LibreOffice иногда долго не появляется в AT-SPI после relaunch.

4. **Screenshot capture best-effort.**

   Скриншоты не должны влиять на `state_id`, transition classification или completion. Если screenshot capture не сработал, exploration должен продолжаться.

## 25.12. Следующий этап: observation layer и depth 3

Перед переходом на третий уровень рекомендуется:

1. наложить observation layer на текущий graph:
   - читать `states/<state_id>/a11y.xml`;
   - извлекать видимые элементы active_root;
   - показывать их в agent-facing карте вместе с `screenshot.png`;

2. сделать dialog controls observation-only для safe map:
   - `OK`;
   - `Cancel`;
   - `Help`;
   - checkboxes в dialog states;

3. отдельно выбрать whitelist для depth-3 menu-only веток, например:
   - `Table → Insert`;
   - `Table → Select`;
   - `Table → Size`;
   - `Table → Convert`;

4. не идти автоматически по dialog controls и content-changing actions.

# 26. LibreOffice Writer: построение agent-facing карты и визуализация observation layer

Раздел фиксирует построение agent-facing карты поверх завершённого `depth=2` exploration LibreOffice Writer.

Цель этапа — не расширять graph глубже, а наложить на существующий граф слой наблюдений:

```text
graph layer:
  verified transitions между состояниями

observation layer:
  видимые элементы состояния из saved A11Y snapshot

screenshot layer:
  визуальная проверка состояния через screenshot.png
```

## 26.1. Исходный checkpoint

Карта строится поверх clean graph Writer, остановленного на границе третьего уровня.

Актуальные показатели graph:

```text
app_id = libreoffice_writer
root_state_id = 36427b830db2

nodes = 39
edges = 51

edge_status_counts:
  confirmed = 38
  pending = 13

node_depth_counts:
  0 = 1
  1 = 11
  2 = 27

completion:
  status = partial
  pending_edges = 13
  reason = pending_edges_exist
```

`pending` на `from_depth=2` — это frontier следующего уровня. Он не выполняется на этом этапе.

Актуальные screenshots:

```text
states = 39
screenshots = 39
```

То есть для каждого state сохранены:

```text
data/maps/libreoffice_writer/states/<state_id>/a11y.xml
data/maps/libreoffice_writer/states/<state_id>/screenshot.png
```

## 26.2. Назначение agent map

`agent_map.json` — это compact agent-facing представление UI-карты.

Он объединяет:

- confirmed graph states;
- verified actions;
- incoming actions;
- observed UI items;
- scoped observed items;
- delta observed items;
- state capabilities;
- artifacts состояния, включая `a11y.xml` и `screenshot.png`.

Основная семантика:

```text
verified_actions:
  действия, реально выполненные exploration и подтверждённые graph transition

observed_items:
  полный видимый A11Y inventory состояния

scoped_observed_items:
  best-effort важные элементы активного состояния

delta_observed_items:
  диагностическая разница относительно ближайшего incoming/base state

state_capabilities:
  agent-facing список, объединяющий verified actions и scoped observed items
```

Важно: `observed_item` не равен verified transition. Например `Save`, `Print`, `Exit LibreOffice` могут быть видны в меню `File`, но не являются разрешёнными/проверенными переходами.

## 26.3. Построить agent map

```bash
python -m ui_explorer.cli.build_agent_map \
  --app libreoffice_writer \
  --maps data/maps
```

Ожидаемый результат:

```text
ok = true
output = data/maps/libreoffice_writer/agent_map.json

states = 39
edges = 51
items = 381
observed_item_refs = 3434
delta_observed_item_refs = 284
scoped_observed_item_refs = 754
state_capabilities = 369
item_index = 355
verified_action_index = 37
```

## 26.4. Inspect agent map

Общий inspect:

```bash
python -m ui_explorer.cli.inspect_agent_map \
  --app libreoffice_writer \
  --maps data/maps
```

Актуальный summary:

```text
schema_version = 1.2
root_state_id = 36427b830db2

summary:
  states = 39
  edges = 51
  max_depth = 2
  pending_edges = 13

edge_status_counts:
  confirmed = 38
  pending = 13

node_depth_counts:
  0 = 1
  1 = 11
  2 = 27

items = 381
observed_item_refs = 3434
delta_observed_item_refs = 284
scoped_observed_item_refs = 754
state_capabilities = 369

item_index_size = 355
verified_action_index_size = 37
```

## 26.5. Проверить screenshots в agent map

После добавления `artifacts.screenshot` в `agent_map.json`:

```bash
python - <<'PY'
import json
from pathlib import Path

m = json.loads(Path("data/maps/libreoffice_writer/agent_map.json").read_text())

count = 0
for state in m["states"].values():
    screenshot = (state.get("artifacts") or {}).get("screenshot")
    if screenshot:
        count += 1

print("states:", len(m["states"]))
print("states_with_screenshot:", count)
PY
```

Ожидаемый результат:

```text
states: 39
states_with_screenshot: 39
```

## 26.6. Построить HTML-визуализацию agent map

```bash
python -m ui_explorer.cli.visualize_agent_map \
  --app libreoffice_writer \
  --maps data/maps \
  --output data/maps/libreoffice_writer/agent_map_depth2_with_observation_and_screenshots.html \
  --max-items-per-state 120
```

Открыть:

```bash
xdg-open data/maps/libreoffice_writer/agent_map_depth2_with_observation_and_screenshots.html
```

Если HTML лежит в `data/maps/libreoffice_writer/`, screenshot path в визуализации должен быть относительным:

```text
states/<state_id>/screenshot.png
```

Например:

```html
<img src="states/36427b830db2/screenshot.png">
```

Не использовать путь вида:

```text
data/maps/libreoffice_writer/states/<state_id>/screenshot.png
```

внутри HTML, лежащего рядом с папкой `states`, иначе браузер будет искать несуществующий вложенный путь:

```text
data/maps/libreoffice_writer/data/maps/libreoffice_writer/states/...
```

## 26.7. Проверить graph inspect

```bash
python -m ui_explorer.cli.inspect_graph --app libreoffice_writer
```

Актуальный результат:

```text
nodes = 39
edges = 51

completion:
  status = partial
  pending_edges = 13
  reason = pending_edges_exist

node_depth_counts:
  0 = 1
  1 = 11
  2 = 27

edge_status_counts:
  confirmed = 38
  pending = 13
```

Типичный next pending frontier:

```text
from_depth = 2

Properties of “Untitled 1”:
  Save preview image with this document
  Apply user data
  Help
  Cancel
  OK

Go to Page:
  Cancel
  OK

Options - LibreOffice - User Data:
  Use data for document properties
  When encrypting documents, always encrypt to self
  Help
  ...
```

Это нормально: dialog controls остаются frontier третьего уровня.

## 26.8. Проверить screenshots на диске

```bash
echo "states:"
find data/maps/libreoffice_writer/states -mindepth 1 -maxdepth 1 -type d | wc -l

echo "screenshots:"
find data/maps/libreoffice_writer/states -mindepth 2 -maxdepth 2 -name screenshot.png | wc -l
```

Ожидаемый результат:

```text
states:
39

screenshots:
39
```

## 26.9. Пример интерпретации состояния: File

Для состояния `File`:

```text
Incoming actions:
  root -- File → this confirmed
```

Verified actions:

```text
New → 19a31745f3fe confirmed
Recent Documents → 3e4dc1cffc8d confirmed
Templates → 1c6d5d3a1094 confirmed
Export As → abd09c05bb29 confirmed
Properties... → bfbd29b4b754 confirmed
```

Scoped observed items могут включать:

```text
Open...
Open Remote...
Close
Wizards
Reload
Versions...
Save
Save As...
Save Remote...
Save a Copy...
Save All
Export...
Send
Preview in Web Browser
Print...
Printer Settings...
Digital Signatures
Exit LibreOffice
```

Интерпретация:

```text
verified_action:
  проверенный переход, его можно использовать как graph navigation edge

observed_item:
  элемент виден в UI, но не проверен как safe transition
```

То есть `Save` или `Print` могут присутствовать в observation, но не являются разрешёнными переходами текущей safe policy.

## 26.10. Пример интерпретации состояния: Tools → Language

Для состояния `Language`:

```text
Tools depth=1
  └─ Language depth=2
```

Incoming action:

```text
Tools -- Language → this confirmed
```

Verified actions:

```text
none
```

Scoped observed items:

```text
For Selection
For Paragraph
For All Text
Hyphenation...
More Dictionaries Online...
```

Интерпретация:

- `Language` был достигнут проверенным переходом из `Tools`;
- элементы `For Selection`, `For Paragraph`, `For All Text`, `Hyphenation...`, `More Dictionaries Online...` видны в submenu;
- они не являются verified transitions, потому exploration остановлен на `depth=2`.

## 26.11. Что смотреть в визуализации

В правой панели state details основные секции:

```text
Primary incoming action:
  как состояние было достигнуто

State capabilities:
  agent-facing список verified actions + scoped observed items

Verified actions:
  подтверждённые переходы graph

Scoped observed items:
  важные видимые элементы активного состояния

All observed items:
  полный raw A11Y visible inventory, может быть шумным

Delta hints:
  диагностическая разница относительно base/incoming state

Incoming actions:
  все подтверждённые входящие переходы в это состояние

Screenshot:
  визуальная проверка состояния
```

Для практического анализа использовать в первую очередь:

```text
Screenshot
State capabilities
Verified actions
Scoped observed items
Primary incoming action
```

`All observed items` использовать как debug/raw слой.

## 26.12. Сохранить checkpoint карты

```bash
mkdir -p data/maps/libreoffice_writer/checkpoints

cp data/maps/libreoffice_writer/graph.json \
   data/maps/libreoffice_writer/checkpoints/graph_depth2_with_screenshots.json

cp data/maps/libreoffice_writer/agent_map.json \
   data/maps/libreoffice_writer/checkpoints/agent_map_depth2_with_observation_and_screenshots.json

cp data/maps/libreoffice_writer/agent_map_depth2_with_observation_and_screenshots.html \
   data/maps/libreoffice_writer/checkpoints/agent_map_depth2_with_observation_and_screenshots.html
```

Проверить:

```bash
ls -lh data/maps/libreoffice_writer/checkpoints | grep -E \
  'graph_depth2_with_screenshots|agent_map_depth2_with_observation'
```

## 26.13. Текущий статус

Карта построена успешно.

Итоговый статус:

```text
graph:
  states = 39
  edges = 51
  confirmed = 38
  pending = 13
  max_depth = 2

agent_map:
  schema_version = 1.2
  items = 381
  observed_item_refs = 3434
  delta_observed_item_refs = 284
  scoped_observed_item_refs = 754
  state_capabilities = 369
  item_index_size = 355
  verified_action_index_size = 37

screenshots:
  states = 39
  screenshots = 39
```

Depth-2 exploration и agent-facing карта с observation layer зафиксированы.

## 26.14. Следующий этап

Перед переходом на `depth=3` рекомендуется:

1. решить policy для dialog controls:
   - `OK`;
   - `Cancel`;
   - `Help`;
   - checkboxes;

2. выбрать whitelist для depth-3 menu-only веток;

3. не выполнять автоматически content-changing или file-system actions;

4. использовать agent map для ручной проверки candidate branches перед расширением graph.
