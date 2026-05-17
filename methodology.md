# Методология A11Y-first UI Exploration

## 1. Цель подхода

Цель проекта — автоматически строить карту пользовательского интерфейса GUI-приложения на основе дерева доступности. Под картой понимается граф, где:

```text
state = состояние интерфейса
edge  = действие пользователя, переводящее UI из одного состояния в другое
```

Например:

```text
Calculator root
→ нажать Mode selection
→ получить popover выбора режима

Calculator root
→ нажать Primary menu
→ получить меню приложения

Programming mode
→ нажать Binary combo box
→ получить меню выбора системы счисления
```

Ключевой принцип: **источник истины — A11Y Tree**, а не скриншот и не заранее известная логика приложения.

В Linux/GTK-среде дерево доступности отдаётся через AT-SPI. Оно содержит структурированное описание UI:

```text
role
name
description
states
bbox
parent_path
children
```

Скриншоты могут использоваться для ручной проверки человеком, но exploration, построение графа, извлечение действий и формирование карты должны опираться на A11Y.

---

## 2. Pipeline данных

Текущий pipeline состоит из двух уровней:

```text
A11Y capture
→ graph.json
→ agent_map.json
→ визуализация / инспекция / будущий agent runtime
```

Где:

```text
graph.json
  внутренний source of truth exploration;
  хранит состояния, confirmed/same_state edges, pending frontier, completion.

states/<state_id>/a11y.xml
  сохранённый A11Y snapshot каждого состояния.

agent_map.json
  agent-facing карта поверх graph.json и A11Y snapshots;
  хранит проверенные переходы, видимые UI-элементы, capabilities и индексы поиска.
```

`graph.json` нужен для воспроизводимого exploration.  
`agent_map.json` нужен, чтобы агенту было проще понимать интерфейс и планировать действия.

---

## 3. Захват и нормализация A11Y Tree

Захват дерева доступности выполняет `A11YCapture`.

Он:

```text
1. ищет приложение в AT-SPI registry;
2. получает текущее дерево доступности;
3. сохраняет его в XML;
4. дальше XML парсится в нормализованные Python-объекты.
```

Каждый A11Y node содержит:

```text
role
name
description
states
bbox
parent_path
depth
children
```

Пример полезного элемента:

```json
{
  "role": "toggle button",
  "name": "Primary menu",
  "states": ["enabled", "sensitive", "showing", "visible"],
  "bbox": [517, 4, 36, 46]
}
```

A11Y позволяет отличать элементы не по картинке, а по структуре. Это важно для универсальности: один и тот же подход можно применять к Calculator, gedit и другим приложениям, если они отдают полноценное accessibility tree.

---

## 4. State signature

Каждый A11Y snapshot превращается в подпись состояния.

Состояние — это не картинка, а структурное описание текущего UI-контекста.

Для состояния вычисляются:

```text
state_id
macro_hash
content_hash
active_root
macro_action_count
visible_node_count
```

`state_id` — короткий идентификатор состояния.  
`macro_hash` — подпись структуры UI-контекста.  
`content_hash` — более чувствительная подпись видимого содержимого.  
`active_root` — активная область взаимодействия.

Интуитивно:

```text
macro_hash:
  изменился ли UI-контекст?

content_hash:
  изменилось ли содержимое внутри похожего UI-контекста?
```

Например, открытие меню меняет `macro_hash`.  
Ввод цифры в калькулятор может оставить `macro_hash` прежним, но изменить `content_hash`.

---

## 5. Active root

A11Y Tree часто содержит больше элементов, чем реально относятся к текущему действию.

Например, когда открыт popover, дерево может одновременно содержать:

```text
основное окно приложения
+
элементы открытого popover/menu
```

Если извлекать действия из всего дерева, граф загрязнится: в состоянии “меню открыто” появятся фоновые действия основного окна.

Поэтому сначала определяется `active_root`.

`active_root` — это активная область взаимодействия, из которой извлекаются macro actions.

Примеры:

```json
{
  "kind": "main",
  "role": "frame",
  "name": "Calculator"
}
```

```json
{
  "kind": "window_overlay",
  "role": "filler",
  "name": ""
}
```

```json
{
  "kind": "menu",
  "role": "menu",
  "name": "Currency"
}
```

Важно различать:

```text
role
  сырая A11Y-роль элемента: frame, menu, filler, panel, push button.

kind
  наша внутренняя интерпретация: main, menu, dialog, alert, window_overlay.
```

`window_overlay` — не стандартная A11Y-роль. Это наша классификация для временных UI-слоёв, которые toolkit отдаёт как `filler` или `panel`, но по смыслу они являются popover/menu-like областью.

---

## 6. Извлечение действий

После определения `active_root` система извлекает интерактивные элементы.

Действиями считаются видимые элементы с ролями вроде:

```text
push button
toggle button
radio button
check box
combo box
menu item
tab
tree item
link
spin button
entry
editbar
```

Каждое действие получает:

```text
role
name
description
states
bbox
parent_path
action_key
```

`action_key` — стабильный хэш locator-данных элемента:

```text
role
name
description
states
bbox
parent_path
```

Он нужен, потому что имя само по себе не уникально. Например `Degrees` может быть combo box, menu item или пунктом вложенного меню.

---

## 7. Macro и micro actions

Raw A11Y extraction может находить десятки или сотни интерактивных элементов. В Calculator это не только меню и переключатели, но и цифры, операторы, битовые ячейки, математические функции.

Для построения графа UI-состояний используется rule-based policy:

```text
macro_candidate
micro_candidate
input_candidate
ignored
```

`macro_candidate` — действие, которое может открыть новый UI-контекст или изменить структуру интерфейса.

Примеры:

```text
Mode selection
Primary menu
Decimal
Word Size
Store
Insert Character
Superscript
Subscript
```

`micro_candidate` — действие, которое скорее меняет значение или содержимое, но не структуру UI.

Примеры:

```text
цифры
арифметические операторы
битовые ячейки
```

На текущем этапе exploration строит граф по macro actions. Micro actions при этом не исчезают полностью: многие из них позже попадают в `agent_map.json` как observed/capability элементы.

---

## 8. Graph model

Граф хранится в:

```text
data/maps/<app>/graph.json
```

Он содержит:

```text
nodes
edges
root_state_id
completion
```

State node хранит:

```text
state_id
label
depth
active_root
xml_path
```

Edge хранит:

```text
from_state
action
status
to_state
created_order
reason
```

Статусы edge:

```text
pending
confirmed
same_state
content_changed
focus_changed
selection_changed
failed_click
failed_navigation
```

Главные статусы для построения agent-facing карты:

```text
confirmed
same_state
content_changed
focus_changed
selection_changed
```

Они считаются execution-verified, потому действие реально выполнялось.

---

## 9. Один exploration step

Один шаг exploration — это один контролируемый эксперимент:

```text
1. загрузить graph.json;
2. выбрать следующий pending edge;
3. восстановить from_state;
4. выполнить ровно одно действие;
5. снять новый A11Y snapshot;
6. посчитать state signature;
7. классифицировать результат;
8. обновить graph.json.
```

Выполнение действия сейчас основано на bbox-click:

```text
bbox → центр элемента → клик
```

Перед кликом окно активируется, чтобы снизить риск клика в неправильное место.

После клика система ждёт стабилизации A11Y Tree. Состояние считается стабильным, когда подпись перестаёт меняться.

---

## 10. Hard reset и replay confirmed path

Текущая основная стратегия навигации — **hard reset + replay confirmed path**.

Перед выполнением edge система не полагается на текущее случайное состояние приложения. Вместо этого:

```text
1. перезапускает приложение;
2. проверяет root_state_id;
3. воспроизводит confirmed path от root до edge.from_state;
4. проверяет, что from_state достигнут;
5. выполняет исследуемое действие.
```

Это делает exploration воспроизводимым.

Причина: GUI-состояния бывают persistent. Escape не всегда возвращает приложение в root. Например, Calculator может оставаться в Binary/Keyboard/unit-conversion режиме. Поэтому soft reset через Escape недостаточно надёжен.

Hard reset использует launcher из `config/apps.yaml`, поэтому стратегия не должна быть захардкожена под Calculator.

Soft navigation может оставаться полезной для отладки, но основной режим — hard reset.

---

## 11. Strict BFS

Scheduler использует strict BFS.

Порядок выбора pending edges:

```text
from_state.depth ASC
priority ASC
attempts ASC
created_order ASC
```

Это означает:

```text
сначала закрыть root frontier,
потом depth 1,
потом depth 2,
и так далее.
```

Преимущество strict BFS: карта развивается равномерно и не уходит слишком глубоко в одну ветку интерфейса.

---

## 12. Текущий результат Calculator graph

Для GNOME Calculator текущий граф завершён в рамках текущей macro-action policy.

Актуальный checkpoint:

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

Это означает:

```text
frontier закрыт;
pending edges нет;
все выбранные macro actions исследованы;
navigation replay работает без failed_navigation.
```

Граф содержит разные типы состояний:

```text
main frame states
window_overlay popovers
menus
dialogs
same_state toggles
mode states
combo box menus
```

---

## 13. Agent-facing UI map

`graph.json` полезен как source of truth exploration, но он слишком технический для агента.

Поэтому строится отдельный файл:

```text
data/maps/<app>/agent_map.json
```

Он строится из:

```text
graph.json
states/*/a11y.xml
```

Цель `agent_map.json` — дать агенту компактное понимание:

```text
куда можно перейти;
какие элементы видимы;
как состояние было открыто;
какие возможности есть в состоянии;
какие элементы подтверждены exploration, а какие только observed.
```

---

## 14. verified_actions

`verified_actions` — проверенные действия из текущего состояния.

Пример:

```json
{
  "role": "toggle button",
  "name": "Primary menu",
  "status": "verified",
  "method": "bbox_click",
  "edge_status": "confirmed",
  "to_state": "3b4bc848561d",
  "bbox": [517, 4, 36, 46]
}
```

Смысл:

```text
из этого состояния можно нажать Primary menu
и перейти в state 3b4bc848561d
```

Это самый надёжный слой карты.

---

## 15. incoming_actions и primary_incoming_action

`incoming_actions` — все проверенные действия из других состояний, которые ведут в текущее.

`primary_incoming_action` — один выбранный основной вход в состояние.

Пример:

```text
e14ee107e46f -- Primary menu → 3b4bc848561d confirmed
```

Читается так:

```text
из root state e14ee107e46f нажали Primary menu
и открыли текущее состояние 3b4bc848561d
```

Важно: `primary_incoming_action` — это локальное объяснение входа в state, а не глобально лучший маршрут от root.

Для реального агента маршрут должен вычисляться runtime-планировщиком от текущего live-state до цели по `verified_actions`.

---

## 16. items и observed_items refs

В `agent_map.json` есть верхнеуровневый каталог:

```text
items
```

Это дедуплицированные observed UI-элементы.

Внутри каждого state вместо полного копирования item используется ref:

```json
"observed_items": [
  {
    "ref": "a29449dcc97c1216",
    "role": "menu",
    "name": "Currency",
    "description": ""
  }
]
```

Полное описание лежит в:

```json
"items": {
  "a29449dcc97c1216": {
    "role": "menu",
    "name": "Currency",
    "status": "observed_unverified",
    "states": ["enabled", "sensitive", "showing", "visible"],
    "parent_path_tail": ["panel", "filler", "combo box/Degrees", "menu"]
  }
}
```

Такой формат уменьшает размер карты и позволяет строить индексы.

---

## 17. observed_items

`observed_items` — полный видимый A11Y-контекст конкретного состояния.

Для main state это часто полезно и соответствует основному экрану.

Для overlay/menu state `observed_items` может быть шумным, потому A11Y snapshot содержит:

```text
фон основного окна
+
открытый overlay/menu
```

Пример для Word Size overlay:

```text
observed_items:
  Undo
  Mode selection
  Primary menu
  Decimal
  ...
  64-bit
  32-bit
  16-bit
  8-bit
```

Поэтому `observed_items` не должен быть главным agent-facing слоем для overlay.

---

## 18. delta_observed_items

`delta_observed_items` — диагностическая разница между текущим state и ближайшим base state.

Base обычно выбирается через `primary_incoming_action`.

Пример Word Size:

```text
base: root
current: root + Word Size overlay
delta:
  64-bit
  32-bit
  16-bit
  8-bit
```

Пример Primary menu:

```text
base: root
delta:
  New Window
  Preferences
  Keyboard Shortcuts
  Help
  About Calculator
```

Важно: delta — это hint, а не полное содержимое состояния.

Для overlay/menu delta часто полезна.  
Для полноценных режимов вроде Basic или Programming delta может быть неполной и не должна считаться “смыслом” состояния.

---

## 19. scoped_observed_items

`scoped_observed_items` — best-effort слой важных observed elements для текущего состояния.

Цель:

```text
показать не весь A11Y snapshot,
а элементы, относящиеся к активной части состояния.
```

Логика текущей версии:

```text
main state:
  scoped = observed_items
  confidence = high

overlay/menu state с delta:
  scoped = delta_observed_items
  confidence = medium

если точное выделение невозможно:
  scoped = fallback observed_items
  confidence = low
```

Пример Word Size:

```text
scoped:
  64-bit
  32-bit
  16-bit
  8-bit
```

Пример Primary menu:

```text
scoped:
  New Window
  Preferences
  Keyboard Shortcuts
  Help
  About Calculator
```

Пример low-confidence menu state:

```text
scoped_source = fallback_observed_items
scoped_confidence = low
```

В таком случае scoped считается диагностическим и не должен автоматически попадать в capabilities.

---

## 20. state_capabilities

`state_capabilities` — главный agent-facing слой состояния.

Он объединяет:

```text
verified_actions
+
trusted scoped_observed_items
```

Правило безопасности:

```text
если scoped_observed_confidence == low,
fallback observed items не добавляются в state_capabilities
```

В таком случае в capabilities остаются verified actions и, если есть, delta hints.

Это нужно, чтобы агент не путался в фоне.

Пример Mode selection:

```text
capabilities:
  Basic
  Advanced
  Financial
  Programming
  Keyboard
```

Хотя raw observed может содержать много фоновых элементов.

Пример Word Size:

```text
capabilities:
  64-bit
  32-bit
  16-bit
  8-bit
```

Пример Programming/Binary main state:

```text
capabilities:
  Mode selection
  Primary menu
  Binary combo box
  Word Size
  Store
  Insert Character
  Shift Left / Shift Right
  Superscript / Subscript
  AND / OR / XOR / NOT
  A-F
  bit grid 0-63
  arithmetic controls
```

Для main states список capabilities может быть большим. Это нормально: агент должен искать нужные capability по имени/описанию, а не читать всё подряд.

---

## 21. Интерпретация verified vs observed

Карта различает:

```text
verified_action
  действие было выполнено exploration;
  известен edge_status;
  часто известен to_state;
  bbox считается проверенным в контексте from_state.

observed_item
  элемент был видим в A11Y snapshot;
  он полезен как знание об UI;
  но exploration не подтверждал, куда приведёт клик.
```

Пример gedit menu:

```text
Menu → confirmed overlay state

Внутри overlay observed-only:
  Preferences
  Find…
  Save As…
  Print…
```

Это значит:

```text
агент знает, что пункт Preferences виден;
но карта заранее не знает, какой state получится после клика.
```

Для live-agent это всё равно полезно: он может открыть меню и кликнуть видимый пункт.

---

## 22. Визуализация agent map

Интерактивная визуализация строится командой:

```bash
python -m ui_explorer.cli.visualize_agent_map --app calc
```

Результат:

```text
data/maps/<app>/agent_map.html
```

Верхние переключатели:

```text
verified actions
  показывает проверенные state → state переходы.

scoped items
  показывает state → scoped observed item связи.

all observed
  показывает state → all observed item связи.
  Это самый полный, но самый шумный слой.

delta hints
  показывает диагностическую разницу относительно base state.
```

Рекомендуемый режим чтения:

```text
verified actions: ON
scoped items: ON
all observed: OFF
delta hints: OFF
```

Правая панель выбранного состояния показывает:

```text
Primary incoming action
State capabilities
Verified actions
Scoped observed items
All observed items
Delta hints
Incoming actions
```

Главный блок для агента:

```text
State capabilities
```

`All observed` и `Delta hints` нужны в основном для диагностики.

---

## 23. Пример: Word Size overlay

State:

```text
4a701cc0ad96
active_root: window_overlay / filler
primary: root -- Word Size → this confirmed
```

Raw observed:

```text
123 elements
```

Но scoped/capabilities:

```text
64-bit
32-bit
16-bit
8-bit
```

Интерпретация:

```text
это overlay выбора word size;
открывается кнопкой Word Size;
внутри доступны варианты 64-bit, 32-bit, 16-bit, 8-bit.
```

---

## 24. Пример: Primary menu

State:

```text
3b4bc848561d
active_root: window_overlay / filler
primary: root -- Primary menu → this confirmed
```

Verified actions:

```text
Number format
Automatic
Fixed
Scientific
Engineering
```

Scoped observed items:

```text
New Window
Preferences
Keyboard Shortcuts
Help
About Calculator
```

Capabilities:

```text
verified number-format actions
+
observed menu items
```

Интерпретация:

```text
из root можно открыть Primary menu;
внутри подтверждены переключатели формата числа;
также видны дополнительные пункты меню.
```

---

## 25. Пример: глубокое menu state

State `ac0a3bafea3c`:

```text
active_root: menu
primary: Gradians combo box → this
verified actions:
  Degrees
  Radians
  Gradians
scoped_confidence: low
state_capabilities:
  Degrees
  Radians
  Gradians
```

Здесь scoped observed оказался low-confidence и содержит фоновые элементы, но capabilities остаются чистыми за счёт verified actions.

Интерпретация:

```text
это открытое меню выбора angular unit;
агенту надо использовать state_capabilities,
а не low-confidence scoped observed.
```

---

## 26. Пример: Programming/Binary main state

State `f7fcc6f359d2`:

```text
active_root: main / frame / Calculator
primary: Binary menu item → this
scoped_confidence: high
capabilities: 119
```

Это полноценный main state, поэтому scoped = observed.

Capabilities большие, потому Programming/Binary interface действительно содержит много controls:

```text
bit grid 0-63
A-F
AND / OR / XOR / NOT
ones / twos
arithmetic operations
number base combo box
Word Size
Shift Left / Shift Right
```

Важно: путь через `primary_incoming_action` не должен восприниматься как оптимальный маршрут от root. Для реального агента маршрут должен вычисляться от текущего live-state.

---

## 27. Проверка на gedit

gedit показал, зачем нужен agent-facing слой.

Graph для gedit маленький:

```text
nodes: 3
edges: 4
```

Но agent_map извлёк:

```text
items: 26
observed_item_refs: 36
delta_observed_item_refs: 19
scoped_observed_item_refs: 29
state_capabilities: 33
```

Особенно полезен overlay меню:

```text
root -- Menu → menu overlay
```

Capabilities меню:

```text
Reload
Print…
Fullscreen
New Window
Save As…
Save All
Find…
Find and Replace…
Clear Highlight
Go to Line…
View
Tools
Preferences
Keyboard Shortcuts
Help
About Text Editor
```

Это хороший результат: даже при скромном graph агент получает понимание возможностей интерфейса.

---

## 28. Известные ограничения

### 28.1. Active root / label resolver

Иногда graph metadata может назвать menu state неидеально.

Пример Calculator:

```text
primary: Degrees combo box → menu
active_root.name: Currency
contents: Angle, Length, Speed, ..., Currency
```

По скриншотам видно, что это меню категорий единиц измерения, открытое из combo box `Degrees`, а `Currency` — пункт внутри меню, не название всего состояния.

Это значит, что active_root resolver иногда выбирает не root открытого menu, а один из вложенных menu nodes.

Будущее улучшение:

```text
сохранять точный active_root selector/path/bbox в graph.json;
улучшить выбор root menu/submenu;
не полагаться только на role/name.
```

### 28.2. Scoped observed is best-effort

`scoped_observed_items` пока строится без точного active-root subtree selector. Поэтому confidence может быть:

```text
high
medium
low
```

Low-confidence scoped не должен использоваться как основной источник для агента.

### 28.3. Observed-only не равен verified

Если item observed-only, карта знает, что он виден, но не знает проверенный результат клика.

Это нормально для agent-facing подсказки, но runtime-agent должен уметь действовать осторожно:

```text
открыть нужное состояние;
найти observed item в live UI;
кликнуть;
снять новый A11Y snapshot;
обновить своё понимание.
```

### 28.4. Runtime routing

Карта не должна хранить один “лучший путь от root” для каждого состояния.

Агент находится в текущем live-state, поэтому маршрут должен вычисляться динамически:

```text
current_state → target_state
```

по `verified_actions`.

---

## 29. Текущий статус методологии

Текущая система уже умеет:

```text
- захватывать A11Y Tree;
- строить state signatures;
- определять active_root;
- извлекать и классифицировать macro actions;
- строить graph.json;
- выполнять strict BFS exploration;
- использовать hard reset + replay confirmed path;
- завершать Calculator graph в рамках macro policy;
- строить agent_map.json поверх graph + A11Y snapshots;
- дедуплицировать observed items через items + refs;
- строить incoming_actions и primary_incoming_action;
- строить delta_observed_items;
- строить scoped_observed_items с confidence;
- строить state_capabilities;
- инспектировать и визуализировать agent-facing карту;
- показывать пользу подхода на gedit.
```

Главные следующие направления:

```text
1. улучшить active_root resolver и сохранять точный active_root selector в graph.json;
2. развить runtime pathfinding от текущего live-state;
3. научить agent runtime безопасно использовать observed-only capabilities;
4. расширить exploration policy для отдельных классов push buttons;
5. проверить подход на других приложениях с полноценным A11Y Tree.
```
