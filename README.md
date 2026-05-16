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
32 passed
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

## 23. Использование graph.json как карты для Computer-use агента

`graph.json` рассматривается как статическая карта GUI-состояний приложения. Он строится один раз во время exploration, а затем может использоваться Computer-use агентом как внешняя навигационная память.

Рекомендуемая архитектура:

```text
graph.json
  ↓
Graph Memory / MCP-tool API
  ↓
Computer-use agent
```

Модель не должна читать весь `graph.json` как prompt. Вместо этого graph-tool должен отдавать компактные и точные ответы:

```text
inspect_graph(app)
identify_state(current_a11y_xml)
get_state(state_id)
get_actions(state_id)
find_path(from_state, to_state)
next_step(current_state, goal)
get_frontier(depth)
```

Для управления GUI важно выполнять не semantic search по всему JSON, а детерминированную навигацию по confirmed edges:

```text
current A11Y snapshot → state_id → confirmed path → live action lookup → click → verify expected state
```

RAG может использоваться только как дополнительный semantic layer для поиска целей по человеческим описаниям, например `binary mode`, `hexadecimal`, `unit conversion`. После выбора цели путь должен строиться строго по графу.
