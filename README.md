## Методология дистилляции GUI-навыков из мультимодальных языковых моделей в набор специализированных, компактных моделей, предоставляемых в виде MCP-tools (GUI Distillation)

![Methodology Pipeline](https://github.com/RT41yo/gui_distillation/blob/phase_1/assets/methodology_pipeline.png)

![Workflow](https://github.com/RT41yo/gui_distillation/blob/phase_1/assets/workflow.png)

## Phase 0: инфраструктура GUI и формализация навыков

Фаза 0 создает детерминированную, воспроизводимую инфраструктуру для автоматизации GUI и формально определяет контракты четырех навыков системы.

Что реализовано:  

- Детерминированная X11-среда (Xvfb)  
- Ядро GUI-автоматизации  
- Калиброванные координаты кнопок  
- Формализованные Pydantic-схемы навыков  
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

Используется для калибровки координат кнопок.

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
export DISPLAY=:99
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

Если всё корректно:  
```
🎉 ALL TESTS PASSED! Infrastructure is ready.
```

### Unit-тесты схем

Проверка формальных контрактов навыков:  

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


## Phase 1: текущий рабочий протокол запуска (пока пайплайн раздельный)

На текущем этапе Phase 1 пайплайн состоит из **двух отдельных частей**:

1. **Execution / data collection** — automation запускает приложение в виртуальном дисплее, выполняет действия и сохраняет шаги траектории (`before.png`, `after.png`, `action.json`, `metadata.json`).
2. **Semantic annotation** — отдельный запуск annotator/LLM-модуля, который по уже собранным шагам формирует `observation.json` и `delta.json`.

### Важно
- `gnome-calculator` **не запускать вручную** перед `automation`.
- `Xvfb` нужно поднимать **только если он ещё не запущен**.
- `DISPLAY` должен быть выставлен в `:99`.

---

### Часть 1. Сбор шагов через automation

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

Пример запуска automation на 5 шагах:  
```bash
python -m src.core.automation --random-buttons --steps 5 \
  --settings config/settings.yaml \
  --app-config config/apps/calculator.yaml \
  --output data/exploration/phase_1_debug
```

### Часть 2. Аннотирование собранных шагов

После того как шаги собраны в `data/exploration/phase_1_debug`, запускается annotator:  

```bash
python -m src.exploration.teacher_debug_runner \
  --steps-root data/exploration/phase_1_debug \
  --settings config/settings.yaml \
  --teacher-config config/teachers/openai_gpt.yaml \
  --max-steps 5
```

Для каждого шага:  
- `before.png`
- `after.png`
- `action.json`
- `metadata.json`
- `observation.json`
- `delta.json`

В корне run-директории:
- `teacher_debug_report.json`

















