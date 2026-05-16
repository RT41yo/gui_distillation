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
