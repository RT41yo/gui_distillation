## Методология дистилляции GUI-навыков из мультимодальных языковых моделей в набор специализированных, компактных моделей, предоставляемых в виде MCP-tools (GUI Distillation)

![Methodology Pipeline](https://github.com/RT41yo/gui_distillation/blob/phase_1/assets/methodology_pipeline.png)

![Workflow](https://github.com/RT41yo/gui_distillation/blob/phase_1/assets/workflow.png)


## Phase 0: инфраструктура GUI и формализация навыков

Фаза 0 создает детерминированную, воспроизводимую инфраструктуру для автоматизации GUI exploration.

Что реализовано:  

- Детерминированная X11-среда (Xvfb)  
- Ядро GUI-автоматизации  
- Калиброванные координаты центров кнопок  
- Формализованные Pydantic-схемы  
- Полностью воспроизводимый тестовый пайплайн  


### Структура скриптов  

**setup_vm.sh**  

Подготовка виртуальной машины:  

```
sudo bash scripts/setup/setup_vm.sh
```

Устанавливает: python3, pip, venv, git, build-essential, базовые системные зависимости  

**install_apps.sh**  

Установка GUI-приложения (GNOME Calculator):  

```
sudo bash scripts/setup/install_apps.sh
```

**setup_xvfb.sh**  

Установка Xvfb и X11-инструментов:  

```
sudo bash scripts/setup/setup_xvfb.sh
```

**reset_display.sh**  

Очистка и перезапуск виртуального дисплея. Рекомендуется запускать перед тестами.   

```
bash scripts/setup/reset_display.sh
```

Скрипт:  
- убивает старый Xvfb  
- снимает lock-файл  
- очищает DISPLAY  
- запускает новый Xvfb :99  
- проверяет доступность

Это официальный способ подготовки среды.  


### Инструменты (scripts/tools)  

**find_coordinates.py**  

Используется для калибровки координат центров кнопок.

```
config/apps/calculator.yaml
```

В большинстве случаев повторная калибровка не требуется. Калибровка нужна только если:  
- изменилось разрешение  
- изменился размер/позиция окна  
- используется другая версия калькулятора  
- тест “digit_5” не проходит  

Запуск:  
```
export DISPLAY=:0
gnome-calculator &
python scripts/tools/find_coordinates.py --output config/apps/calculator.yaml
```

**test_automation.py**  

Полный тест инфраструктуры GUI.  

Проверяет:  
- доступность дисплея  
- запуск приложения  
- создание скриншотов  
- выполнение кликов  
- before/after артефакты  
- клик по digit_5 (если есть координаты)  

Запуск:  
```
python scripts/tools/test_automation.py --display :99 --app gnome-calculator -v
```

Если все корректно:  
```
🎉 ALL TESTS PASSED! Infrastructure is ready.
```


### Unit-тесты схем

Проверка формальных контрактов:  

```
pytest -q tests/unit/test_schemas.py
```

Минимальный сценарий запуска “с нуля”  

```
git clone <repo>
cd <repo>

sudo bash scripts/setup/setup_vm.sh
sudo bash scripts/setup/install_apps.sh
sudo bash scripts/setup/setup_xvfb.sh

bash scripts/setup/reset_display.sh

pytest -q tests/unit/test_schemas.py
python scripts/tools/test_automation.py --display :99 --app gnome-calculator -v
```

**Если тесты проходят — Фаза 0 завершена.**


## Phase 1: текущий рабочий протокол запуска (пока пайплайн раздельный - human in the loop)

На текущем этапе Phase 1 пайплайн состоит из **двух отдельных частей**:

1. **Execution / data collection** — `/src/core/automation.py` запускает приложение в виртуальном дисплее, выполняет действия в приложении (рандомные) и сохраняет шаги траектории: скриншот интерфейса до действия, скриншот интерфейса после действия, действие (рандомное), метаинформацию (`before.png`, `after.png`, `action.json`, `metadata.json`).
2. **Semantic annotation** — отдельный запуск annotator/LLM-модуля, который по уже собранным шагам траектории формирует `observation.json` (описание элементов интерфейса) и `delta.json` (описание изменений состояния интерфейса).


### Важно
- `gnome-calculator` **не запускать вручную** перед `/src/core/automation.py`.
- `Xvfb` нужно поднимать **только если он еще не запущен**.
- `DISPLAY` должен быть выставлен в `:99`.

---


### Часть 1. Сбор шагов траекторий через `/src/core/automation.py`

Если Xvfb еще не запущен:  
```bash
Xvfb :99 -screen 0 1280x1024x24 -ac &
export DISPLAY=:99
xdpyinfo | grep dimensions
```

Перед новым прогоном (рекомендуется):  
```bash
pkill -f gnome-calculator
```

Пример запуска `/src/core/automation.py` на 5 шагах:  
```bash
python -m src.core.automation --random-buttons --steps 5 \
  --settings config/settings.yaml \
  --app-config config/apps/calculator.yaml \
  --output data/exploration/phase_1_debug
```


### Часть 2. Аннотирование шагов траекторий

После того как шаги траектории собраны в `data/exploration/phase_1_debug`, запускается annotator:  

```bash
python -m src.exploration.teacher_debug_runner \
  --steps-root data/exploration/phase_1_debug \
  --settings config/settings.yaml \
  --teacher-config config/teachers/openai_gpt.yaml \
  --max-steps 5
```

Для каждого шага набор аннотаций:  
- `before.png`
- `after.png`
- `action.json`
- `metadata.json`
- `observation.json`
- `delta.json`

В корне run-директории создается сводный отчет:
- `teacher_debug_report.json`


### Часть 3. Эксперимент с `observation_grounded` (bbox через MLLM): сравнение совпадения центров элементов UI

Добавлен второй промпт для MLLM - вернуть не только семантическое описание элементов, но и их bbox в абсолютных координатах: `config/prompts/observation_grounded_v1.md`.

В промпте зафиксированы:  
- полный размер входного скриншота (1280x1024);  
- требование, чтобы все bbox лежали внутри границ экрана;  
- `element_id`;  
- контролируемый список элементов UI.  

При включенном флаге:
```
features:
  phase_1:
    use_grounded_observation: true
```

annotator формирует дополнительный файл: `observation_grounded.json` командой:


```bash
python -m src.exploration.teacher_debug_runner \
  --steps-root data/exploration/phase_1_debug \
  --settings config/settings.yaml \
  --teacher-config config/teachers/openai_gpt.yaml \
  --max-steps 2
```

Для первичной оценки качества bbox реализован скрипт `src/exploration/evaluate_bbox.py`.  
Он сравнивает центры bbox, полученных от MLLM с откалиброванными `click points` из `config/apps/calculator.yaml`.

```bash
python -m src.exploration.evaluate_bbox \
  --calculator-yaml config/apps/calculator.yaml \
  --observation-grounded data/exploration/phase_1_debug/step_0001/observation_grounded.json
```


#### Результаты (для 0000 и 0001 шагов траектории):  
MLLM стабильно возвращает:  
- корректный `screen = 1280x1024`;  
- контролируемый список элементов UI;  
- bbox.  

Однако количественная проверка показала, что точность bbox пока недостаточна для прямой замены откалиброванных координат в `executor`, поэтому на текущем этапе `calculator.yaml` остается основным источником координат, а `observation_grounded` используется как дополнительная расширенная аннотация.

1. `mean_center_error` = 40–44 px - средняя ошибка положения центра bbox, который дала MLLM, относительно откалиброванной точки кнопки из `calculator.yaml`, то есть в среднем центр кнопки, оцененный MLLM через bbox, смещен от калиброванной точки примерно на 40–44 пикселя.
2. `point_in_bbox_hit_rate` = 0.18–0.41 - это доля кнопок, для которых откалиброванная точка из `calculator.yaml` попала внутрь bbox, предсказанного MLLM.


### Часть 4. Эксперимент с `observation_grounded` (bbox через MLLM): расчет IoU-метрики

С помощью скрипта `scripts/tools/find_coordinates_bboxes.py` выполнена калибровка bboxes для элементов UI.

Команда запуска:  

```bash
export DISPLAY=:0
gnome-calculator &
python scripts/tools/find_coordinates_bboxes.py --output config/apps/calculator_bboxes.yaml
```

Таким образом создается `config/apps/calculator_bboxes.yaml` - gold standard.

`src/exploration/evaluate_iou.py` выполняет расчет IoU-метрики.

Команда запуска:  

```bash
python -m src.exploration.evaluate_iou \
  --gold-bboxes config/apps/calculator_bboxes.yaml \
  --predicted data/exploration/phase_1_debug/step_0000/observation_grounded.json
```

#### Результаты (для 0000 шага траектории):

- `mean_iou` = 0.1791 - это низкое среднее совпадение bbox от MLLM с вручную размеченными bbox.
- `iou_at_0_5` = 0.0556 - только примерно 5.6% элементов имеют IoU не меньше 0.5 (то есть из 18 совпавших элементов фактически только 1 элемент локализован на приемлемом уровне).
- `iou_at_0_75` = 0.0 - очень точных bbox нет вообще.
- `mean_center_error` = 41.75 - то согласуется с предыдущими измерениями: центры bbox от MLLM в среднем смещены примерно на 42 пикселя относительно gold-разметки.

MLLM-grounded observation корректно восстанавливает топологию интерфейса и основные элементы, однако качество локализации bbox относительно вручную размеченного gold standard остается низким (`mean_iou` - 0.18, `IoU@0.5` - 0.056), поэтому на текущем этапе такие bbox следует рассматривать как weak grounding, а не как точную геометрическую разметку.


##№ Часть 5. Task Runner

`src/exploration/task_runner.py` — LLM-управляемый агент, который выполняет задачи непосредственно во время работы приложения - на каждом шаге получает скриншот текущего состояния, решает какую кнопку нажать, выполняет действие и переходит к следующему шагу.

### Принцип работы

```
скриншот → LLM (промпт + история + скриншот) → button_id
    → координаты из calculator.yaml → run_step() → артефакты
    → новый скриншот → ...
```

LLM получает только символьные идентификаторы кнопок (`digit_3`, `plus`, `equals` и т.д.) и выбирает следующую. Координаты подставляются детерминированно из `calculator.yaml` - модель не угадывает пиксели. Артефакты каждого шага идентичны формату случайного exploration: `before.png`, `after.png`, `action.json`, `metadata.json`.


#### Режим 1: выполнение конкретной задачи

LLM выполняет одну задачу, заданную на естественном языке. Останавливается когда задача выполнена (`task_complete: true`) или исчерпан лимит шагов.

```bash
Xvfb :99 -screen 0 1280x1024x24 -ac &
export DISPLAY=:99

python -m src.exploration.task_runner \
  --task "add 3 and 5, then subtract 2" \
  --max-steps 20 \
  --settings config/settings.yaml \
  --app-config config/apps/calculator.yaml \
  --teacher-config config/teachers/openai_gpt.yaml \
  --output data/exploration/task_runs/run_001
```

Промпт-шаблон: `config/prompts/action_task_v1.md`

JSON-ответ LLM на каждом шаге:
```json
{
  "button_id": "digit_3",
  "rationale": "enter first number",
  "task_complete": false
}
```


#### Режим 2: автономный exploration (`--exploration`)

LLM самостоятельно планирует и выполняет серию подзадач, покрывая разные операции. Каждая завершенная подзадача архивируется, история сбрасывается, LLM выбирает новую цель. Работает до исчерпания лимита шагов.

```bash
python -m src.exploration.task_runner \
  --exploration \
  --task "Explore GNOME Calculator by solving diverse calculations. Cover addition, subtraction, multiplication, division, multi-step expressions, and edge cases." \
  --max-steps 50 \
  --settings config/settings.yaml \
  --app-config config/apps/calculator.yaml \
  --teacher-config config/teachers/openai_gpt.yaml \
  --output data/exploration/task_runs/explore_001
```

Промпт-шаблон: `config/prompts/action_task_exploration_v1.md`

JSON-ответ LLM на каждом шаге:
```json
{
  "current_goal": "compute 7 × 6 to test multiplication",
  "button_id": "digit_7",
  "rationale": "enter first operand",
  "goal_complete": false,
  "task_complete": false
}
```

При `goal_complete: true` или `button_id: "__done__"` текущая подзадача фиксируется в `completed_goals`, история обнуляется и LLM начинает новую цель.

Пример результата за 20 шагов — 4 завершенные подзадачи:
- `7 + 5 = 12`
- `9 - 4 = 5`
- `5 × 6 = 30`
- `30 ÷ 6 = 5`
- начат `(8 + 2) × 3` (лимит шагов исчерпан)


#### Артефакты запуска

В `--output` директории:
```
step_0000/before.png, after.png, action.json, metadata.json
step_0001/...
...
task_run_report.json # сводный отчет по всему запуску
```

`task_run_report.json` содержит для каждого шага: `button_id`, `rationale`, `latency_s`, `usage` (токены), `current_goal` / `goal_complete` (в exploration-режиме). В exploration-режиме в корне отчета — `completed_goals` и `goals_completed`.

После запуска task runner можно прогнать офлайн-аннотирование поверх собранных шагов стандартной командой `teacher_debug_runner`.











