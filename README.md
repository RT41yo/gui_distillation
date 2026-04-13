# A11Y-first GUI Trajectory Agent (gui2mcp)

Агент для автоматического сбора траекторий взаимодействия с GUI-приложениями.
Управляет реальными десктопными приложениями через дерево доступности AT-SPI2 (первичный локатор) и VLM-модель (параллельно, для метрики IoU).
Результаты экспортируются в DART-подобном формате для последующего обучения моделей.

---

## Поддерживаемые приложения

| app_id | Приложение | Категории задач |
|---|---|---|
| `calc` | GNOME Calculator | арифметика, научный режим, программирование |
| `writer` | LibreOffice Writer | ввод текста, сохранение файла |
| `gedit` | gedit | ввод текста, сохранение файла |

---

## Установка зависимостей

```bash
pip install pyautogui pyatspi pydantic openai python-dotenv matplotlib Pillow pyyaml
```

Создайте файл `.env` в корне репозитория:

```
OPENAI_API_KEY=sk-...
```

---

## Запуск

### Режим реального дисплея (`:0`)

Используется когда есть активная графическая сессия. Окна приложений будут открываться на экране — удобно для отладки.

```bash
python -m src.cli.gui2mcp_agent_runner \
  --app calc \
  --task-id calc_001 \
  --max-steps 15 \
  --display :0 \
  --screen-width 1920 \
  --screen-height 1080 \
  --output results/ \
  --dart-output data/ \
  --verbose
```

### Режим виртуального дисплея Xvfb (`:99`)

Используется для headless-запуска (сервер, CI, без монитора). Окна открываются в виртуальном буфере, на экране ничего не отображается.

```bash
# 1. Запустить виртуальный дисплей (однократно)
Xvfb :99 -screen 0 1280x1024x24 -ac &
sleep 1

# 2. Запустить агента
DISPLAY=:99 python -m src.cli.gui2mcp_agent_runner \
  --app calc \
  --task-id calc_001 \
  --max-steps 15 \
  --display :99 \
  --screen-width 1280 \
  --screen-height 1024 \
  --output results/ \
  --dart-output data/ \
  --verbose
```

### Случайная задача

Если не указать `--task-id`, агент выберет задачу случайно из корзины для указанного приложения:

```bash
python -m src.cli.gui2mcp_agent_runner \
  --app writer \
  --max-steps 20 \
  --display :0 \
  --output results/ \
  --dart-output data/
```

### Все параметры CLI

| Параметр | По умолчанию | Описание |
|---|---|---|
| `--app` | обязательный | ID приложения: `calc`, `writer`, `gedit` |
| `--task-id` | случайная | ID задачи из `task_basket.yaml` |
| `--max-steps` | `20` | Максимальное число шагов на эпизод |
| `--display` | `:99` | X11 дисплей |
| `--screen-width` | `1280` | Ширина экрана в пикселях |
| `--screen-height` | `1024` | Высота экрана в пикселях |
| `--output` | `results/` | Папка для внутренних артефактов |
| `--dart-output` | `data/` | Корень DART-экспорта |
| `--settings` | `config/settings.yaml` | Путь к настройкам |
| `--startup-wait` | `3.0` | Секунд ожидания после запуска приложения |
| `--verbose` / `-v` | выключен | Подробное логирование |

---

## Структура результатов

После запуска создаются две директории:

```
results/<uuid>/                           # внутренние артефакты эпизода
  step_0000.png                           # скриншот шага
  a11y_step_0000.xml                      # дерево доступности (XML)
  a11y_step_0000.txt                      # краткий список элементов
  steps/step_0000.json                    # данные шага (action, IoU, dHash)
  ...
  episode.json                            # полная запись эпизода со score
  hamming_chart.png                       # график изменений экрана по шагам

data/pyautogui/screenshot/gui2mcp_agent/  # DART-подобный экспорт
  <app_id>/<uuid>/
    step_N_<timestamp>.png
    traj.jsonl                            # траектория в формате JSONL
    result.txt                            # score и success
  all_result.json                         # сводка по всем эпизодам
  summary/results.json
```

---

## Как работает агент

```
Старт эпизода
  │
  ├── сброс состояния: закрыть приложение → перезапустить
  │
  └── цикл шагов (до max_steps):
        │
        ├── 1. Скриншот текущего экрана
        ├── 2. Захват дерева доступности AT-SPI2 (XML + TXT)
        ├── 3. LLM-планировщик → следующее действие + флаг done
        ├── 4. A11Y-локатор → координаты элемента (основной)
        ├── 5. VLM-локатор → координаты элемента (всегда, для IoU)
        ├── 6. Вычисление IoU (A11Y = ground truth, VLM = prediction)
        ├── 7. Выполнение действия (click / type / hotkey / scroll)
        ├── 8. dHash — хэш изменения экрана между шагами
        │
        └── если done=true или шаги исчерпаны → выход из цикла
  │
  ├── Evaluator проверяет финальное состояние → score 0.0 или 1.0
  └── DART-экспорт траектории
```

**Оценка результата** выполняется программно (не LLM):
- `calc`: читает последнее числовое значение из A11Y XML → сравнивает с ожидаемым
- `writer` / `gedit`: ищет ожидаемый текст в атрибутах A11Y XML

---

## Задачи калькулятора

12 многошаговых задач трёх категорий:

| Задачи | Режим | Примеры |
|---|---|---|
| `calc_001–004` | Basic (арифметика) | `(17+25)×3−18 = 108`, `50% от 240 + 37 = 157` |
| `calc_005–008` | Scientific | `2^10 = 1024`, `√225+15 = 30`, `5! = 120`, `log(1000)×100 = 300` |
| `calc_009` | Basic → Scientific | `9×9=81`, затем `√81 = 9` |
| `calc_010–012` | Programming | `255 → ff (hex)`, `60 AND 15 = 12`, `15 XOR 9 + 1 = 7` |

---

## Тесты

```bash
pytest tests/unit/test_gui2mcp.py -v
```

---

## Конфигурация

| Файл | Назначение |
|---|---|
| `config/app_basket.yaml` | Список приложений |
| `config/task_basket.yaml` | Корзина задач |
| `config/settings.yaml` | Профиль окружения и параметры API |
| `config/llm/planner_gpt-5.4-mini.yaml` | Настройки LLM планировщика |
| `config/llm/locator_gpt-5.4-mini.yaml` | Настройки LLM локатора |
| `config/prompts/planner_task_v1.md` | Промпт планировщика |
| `config/prompts/locator_vlm_v1.md` | Промпт VLM-локатора |
