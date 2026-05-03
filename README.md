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
- BFS scheduler;
- выполнение одного pending edge;
- reset к root-состоянию для root-level exploration;
- построение полного первого слоя графа `depth 0 → depth 1`.

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

На каждом шаге происходит:

1. загрузка `graph.json`;
2. выбор следующего pending edge;
3. reset к root, если edge начинается из root;
4. выполнение одного действия;
5. захват A11Y после действия;
6. сравнение before/after;
7. обновление edge status;
8. добавление нового state, если найден новый macro state;
9. seed новых pending edges из active root нового состояния.

---

## 14. Root-level exploration workflow

После `init_graph` можно закрыть первый слой графа:

```bash
python -m ui_explorer.cli.next_edge --app calc
```

Если вывод содержит:

```json
"from_depth": 0
```

запустить:

```bash
DISPLAY=:99 python -m ui_explorer.cli.step_edge \
  --app calc \
  --display :99 \
  --verbose
```

Затем снова проверить:

```bash
python -m ui_explorer.cli.inspect_graph --app calc
python -m ui_explorer.cli.next_edge --app calc
```

Повторять, пока `next_edge` не покажет:

```json
"from_depth": 1
```

Это означает, что root-level exploration завершён.

---

## 15. Текущий подтверждённый результат для GNOME Calculator

После закрытия слоя `depth 0 → depth 1` был получен граф:

```text
nodes: 11
edges: 86
node_depth_counts:
  0: 1
  1: 10
edge_status_counts:
  confirmed: 10
  pending: 76
```

Root state:

```text
8251e16b481b
```

Подтверждённые root-level transitions:

```text
Mode selection       -> confirmed -> 9b23b16931c9
Primary menu         -> confirmed -> 23853b9028a4
Decimal              -> confirmed -> c5cd52807589
Word Size            -> confirmed -> 5bb1aebc2e55
Store                -> confirmed -> 08fc8d736660
Insert Character     -> confirmed -> de52c438ef75
Shift Right          -> confirmed -> 5b7204416d87
Shift Left           -> confirmed -> 8bc0cc3597e6
Superscript          -> confirmed -> 9ace005e22ae
Subscript            -> confirmed -> 67f6d130a995
```

После этого exploration нужно остановить до реализации replay-path navigation для `depth > 0`.

---

## 16. Важное ограничение текущей версии

Сейчас реализован reset к root для root-level exploration.

Replay path для состояний глубины больше 0 пока не реализован.

Поэтому если:

```bash
python -m ui_explorer.cli.next_edge --app calc
```

показывает:

```json
"from_depth": 1
```

не нужно продолжать запускать `step_edge`, пока не будет реализован navigation:

```text
reset_to_root
replay confirmed path root -> target from_state
verify state
execute action
```

---

## 17. Тесты

Запустить unit tests:

```bash
pytest -q
```

Ожидаемый текущий результат:

```text
24 passed
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
- state signature;
- graph models and store;
- strict BFS scheduler;
- one-edge execution;
- reset-to-root navigation for root edges;
- root-level exploration checkpoint.

Not implemented yet:

- replay path navigation for `depth > 0`;
- full autonomous exploration loop;
- advanced transition classification;
- semantic state labels;
- graph visualization;
- LLM annotations.
