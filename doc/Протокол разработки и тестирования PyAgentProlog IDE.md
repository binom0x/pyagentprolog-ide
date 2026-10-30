
*Документ для передачи в новый диалог. Содержит весь контекст, который нужен, чтобы продолжить разработку без пересказа.*

---

## 0. Краткое резюме

**Проект:** Web-IDE для Prolog-движка PyAgentProlog. Отдельный пакет `pyagentprolog-ide`, зависит от `pyagentprolog` (ядро) и `gradio`. Всё — на Python 3.9+, Gradio 4/5/6.

**Состояние:** работает. Три колонки (проект / редактор / запрос), тёмная тема, компактные кнопки. Авто-подхват `my_actions.py`, `context`, semantic с локальными HF-моделями, tracing + breakpoints, streaming, сессии, таймауты.

**Ключевой принцип:** IDE использует **только публичный API** ядра. Никаких правок в `prolog/*` при разработке IDE — кроме одного опционального патча (см. §6.5).

**При любом изменении — пройдите smoke-тест (§5.1) и регрессию (§5.3).**

---

## 1. Карта проекта

### 1.1. Два пакета

```
D:\bfx\Repositories\
├── pyagentprolog\               ← ядро (Pro-log engine)
│   └── prolog\
│       ├── terms.py
│       ├── parser.py
│       ├── interpreter.py
│       ├── predicates.py
│       ├── solver.py
│       ├── agent.py
│       ├── actions.py
│       ├── bridge.py
│       ├── tracer.py
│       ├── arith_numba.py
│       ├── embedding_unify.py
│       ├── prologchain.py
│       ├── proagent_gradio.py
│       └── __init__.py
│
└── pyagentprolog-ide\           ← IDE (этот пакет)
    ├── pyproject.toml
    ├── README.md
    └── pyagentprolog_ide\
        ├── __init__.py          # экспорт: PrologIDE, build_ui, launch
        ├── __main__.py          # CLI: python -m pyagentprolog_ide
        ├── _gradio_compat.py    # совместимость Gradio 4/5/6, тёмная тема
        ├── actions_ctx.py       # ContextRegistry
        ├── app.py               # ⚠ ГЛАВНЫЙ ФАЙЛ (всё в одном)
        ├── breakpoints.py       # BreakpointController + BreakpointTracer
        ├── examples/
        │   ├── family/kb.pl
        │   ├── factorial/kb.pl
        │   ├── lists/kb.pl
        │   ├── cut_ite/kb.pl
        │   ├── breakpoints/kb.pl
        │   └── semantic/kb.pl
        ├── project.py           # работа с папкой проекта
        ├── sessions.py          # LRU-реестр сессий (100)
        ├── streaming.py         # stream_with_timeout
        └── tree_view.py         # рендер HTML-дерева + хелперы DataFrame
```

### 1.2. Где что менять

| Задача | Файл |
|---|---|
| Новая кнопка / UI-элемент | `app.py` (build_ui + wiring) |
| Новый хендлер | `app.py` (секция «UI handlers») |
| Метод `PrologIDE` | `app.py` (секция «PrologIDE») |
| CSS/стили | `app.py` → `_GLOBAL_CSS` |
| Работа с папкой проекта | `project.py` |
| Context builders | `actions_ctx.py` |
| Точки останова | `breakpoints.py` |
| HTML-дерево | `tree_view.py` |
| Стриминг | `streaming.py` |
| Совместимость Gradio | `_gradio_compat.py` |
| Примеры | `examples/<name>/kb.pl` |

**Не трогать без необходимости:** `sessions.py`, `__init__.py`, `__main__.py`.

---

## 2. Окружение и команды

### 2.1. Установка (один раз)

```powershell
cd D:\bfx\Repositories\pyagentprolog
pip install -e .

cd D:\bfx\Repositories\pyagentprolog-ide
pip install -e .
```

Опционально:

```powershell
pip install sentence-transformers   # для backend='st'
# ollama — отдельный сервис на http://localhost:11434
```

### 2.2. Запуск

```powershell
python -m pyagentprolog_ide
# или
pyagentprolog-ide --host 127.0.0.1 --port 7860
```

Открывается `http://127.0.0.1:7860` (inbrowser=True).

### 2.3. Проверка версий (первое, что нужно сделать)

```powershell
python -c "import gradio; print('gradio', gradio.__version__)"
python -c "import prolog; print('prolog', prolog.__version__)"
python -c "from pyagentprolog_ide import __version__; print('ide', __version__)"
```

Зафиксируйте результат — он влияет на выбор API (например, `theme` в `Blocks()` vs `launch()`, `cancels=` в `.click()`).

---

## 3. Архитектура и обязанности

### 3.1. Поток данных

```
Пользователь
   │
   ├─ 📂 Открыть ─→ handle_open_project
   │                 ├─ _pick_pl_file (tkinter)
   │                 ├─ ide.set_project(path)
   │                 ├─ ide.load_kb_from_project()
   │                 └─ ide.load_program(text)
   │                       └─ _ensure_agent(text)
   │                             ├─ Agent(text, context=...)
   │                             └─ _load_project_actions()
   │                                    └─ import my_actions → register_action_module
   │
   ├─ ▶ Run ─────→ handle_run
   │                 └─ ide.run_query(text, query, _to_timeout(timeout))
   │                       └─ _run_with_timeout(agent.query, timeout)
   │
   ├─ 🔍 Trace ──→ handle_trace (generator)
   │                 └─ ide.run_traced(text, query, timeout, bp)
   │                       ├─ BreakpointTracer(controller)
   │                       ├─ worker thread → agent.query(with_explanation=True)
   │                       └─ UI polling loop (0.05s)
   │
   └─ 🧬 Semantic ON ──→ handle_sem_enable
                          └─ ide.semantic_enable(...)
                                └─ prolog.embedding_unify.semantic_on(...)
```

### 3.2. Ключевые объекты

**`PrologIDE`** (в `app.py`) — состояние сессии:
- `agent: Agent | None`
- `project_dir: str | None`
- `_kb_file_hint: str | None` — конкретный `.pl`, если открыт через диалог
- `_actions_module_name = "my_actions"`
- `_actions_sig: (mtime_ns, size) | None`
- `_signature: str | None` — подпись текущего текста (для детекта изменений)
- `context: ContextRegistry`
- `controller: BreakpointController`
- `history: list[dict]`

**`ContextRegistry`** (`actions_ctx.py`):
- `values: dict` — статика (llm, db, api_key)
- `builders: list[callable]` — функции пересборки
- `apply() → dict` — новый context для пересоздания `Agent`

**`BreakpointController`** (`breakpoints.py`):
- `breakpoints: set[str]` — имена предикатов
- `paused: bool`, `current_step: ProofStep | None`, `hit_count: int`
- `resume(action: "continue" | "step" | "abort")`
- `reset()`, `set_breakpoints(predicates)`

**`BreakpointTracer`** — подменяет `ProofTracer.end_goal`, вызывает `controller.on_end_goal(step)`, который блокируется на `threading.Event` при попадании в breakpoint.

### 3.3. Контракт с ядром (только публичный API)

```python
from prolog.agent import Agent
from prolog.parser import Parser
from prolog.tracer import ProofTracer, ProofStep
from prolog.predicates import PrologError, arith_numba_status
from prolog.actions import simple_action, effector_action, generator_action
from prolog.embedding_unify import (
    semantic_on, semantic_off, semantic_status,
    semantic_set_threshold, semantic_get_unifier,
    detect_text_prefix, resolve_model_id,
    _normalize_text, _lev_ratio,   # ⚠ приватные, но нужны для 🔬 compare
)
```

**Не импортировать:** `interpreter.*` (внутреннее), `Database._solve` (используется только в `Agent.stream`).

---

## 4. Рабочий процесс

### 4.1. Добавление фичи

1. **Сначала read-only диагностика.** Не менять код, пока не понятна причина/дизайн.
2. **Определить точку расширения:**
   - Метод `PrologIDE` → добавьте в класс.
   - UI-элемент → добавьте в `build_ui`.
   - Wiring → добавьте в секцию `# ================ Wiring ================`.
   - Хендлер → добавьте в секцию «UI handlers».
3. **Минимальный патч.** Одна фича — один diff. Не рефакторить попутно.
4. **Smoke-тест** (§5.1).
5. **Feature-тест** (§5.2).
6. **Регрессия** (§5.3).

### 4.2. Исправление бага

1. **Воспроизвести.** Зафиксируйте: путь, запрос, ожидаемое поведение, фактическое.
2. **Найти минимальный воспроизводящий пример.** Часто достаточно 3 строк Prolog.
3. **Понять причину.** Не лечить симптом. Если непонятно — добавьте `print` или временный статус, но не угадывайте.
4. **Патч.**
5. **Проверить, что баг ушёл + smoke-тест + регрессия.**

### 4.3. Правки в `my_actions.py` пользователя

- IDE реимпортирует `my_actions.py` **только** когда `Agent` пересоздаётся (изменение текста в редакторе или нажатие 🔄).
- Детект по `(mtime_ns, size)`. Если файл меняется быстрее одной секунды — реимпорт может не сработать, но это граничный случай.
- **`agent.register_action(...)` внутри `my_actions.py` — запрещён**, регистрация автоматическая.

### 4.4. Правки в примерах (`examples/*/kb.pl`)

- Примеры — **настоящие проекты**. Их можно редактировать и сохранять (💾 Save пишет туда).
- Если меняете дефолтный контент примера — обновите `README.md` в разделе «Examples».

---

## 5. Протокол тестирования

### 5.1. Smoke-тест (обязателен после любого изменения, 2–3 мин)

**Окружение:**

- [ ] `python -m pyagentprolog_ide` стартует без ошибок в консоли.
- [ ] `http://127.0.0.1:7860` открывается.
- [ ] Тёмная тема, три колонки.
- [ ] В консоли нет `Traceback`.

**Колонка 1:**

- [ ] 📚 → выбрать `family/kb.pl` → редактор заполняется, `project_status` показывает `✓ Проект: ...`, `kb: kb.pl`, `my_actions.py: —`.
- [ ] Поле `project_path` заполнено.
- [ ] Status: `✓ Загружено: 8 правил(о); действий: 0; проект: ...`.

**Колонка 2:**

- [ ] Редактор показывает содержимое `family/kb.pl`.
- [ ] `✓ Синтаксис` → `✓ Синтаксис OK: 8 правил(о)`.
- [ ] Раскрыть `⚡ Зарегистрированные действия` → пусто (`[]`), т.к. `my_actions.py` нет.
- [ ] Раскрыть `📚 База знаний` → `Правила` показывает 8 правил, `Индекс` показывает `parent/2`, `grandparent/2`, `ancestor/2`.

**Колонка 3:**

- [ ] Запрос `grandparent(ivan, X).` → ▶ Run → результат содержит `X = petr`, `X = anna`, `X = sergey`.
- [ ] `⏩ First` → `X = petr`.
- [ ] `📡 Stream` → те же три решения, накопительно.
- [ ] `🔍 Trace` (breakpoints пустой) → `✓ Готово. BP hit: 0`, HTML-дерево отрисовано.
- [ ] Клик по строке `Шаги` → `subst` заполняется.

**Консоль:**

- [ ] Нет `[actions import] ...` (нет `my_actions.py`).
- [ ] Нет предупреждений о темах/языке.

### 5.2. Feature-тест (по изменённой области)

#### 5.2.1. Project

- [ ] 📂 с пустым полем → диалог выбора **`.pl` файла** (файлы видны, не только папки).
- [ ] 📂 с полем = путь к папке → открывает папку без диалога.
- [ ] 📂 с полем = путь к `.pl` файлу → открывает именно его, папка = родительская.
- [ ] 🆕 → диалог выбора **папки** → новый проект с `kb.pl`-шаблоном.
- [ ] 💾 Save → сохраняет в `kb.pl` текущего проекта (или в `project_path`, если он отличается).
- [ ] 💾 Save с пустым полем и без проекта → `✗ Проект не выбран`.
- [ ] Переключение между проектами A и B: `sys.path` обновляется, `my_actions.py` A забывается, `my_actions.py` B подхватывается.
- [ ] Drag-drop `.pl` в поле сверху → содержимое в редакторе, статус **предупреждает** про временную папку Gradio, проект **не меняется**.

#### 5.2.2. Actions (`my_actions.py`)

Создать тестовый проект:

```
test_project/
├── kb.pl
└── my_actions.py
```

`my_actions.py`:
```python
from prolog.actions import simple_action, effector_action, generator_action

@simple_action('double', 2, output_arg=1)
def double(x, context):
    return x * 2

@effector_action('log_msg', 1)
def log_msg(msg, context):
    print(f"[LOG] {msg}")

@generator_action('count_to', 2, output_arg=1)
def count_to(n, context):
    for i in range(1, n + 1):
        yield i
```

`kb.pl`:
```prolog
run :- double(21, X), log_msg(X), count_to(3, Y), log_msg(Y), fail.
run.
```

- [ ] 📂 открыть `test_project` → `✓ Загружено: 1 правил(о); действий: 3; ...`.
- [ ] Раскрыть `⚡ Зарегистрированные действия` → 3 записи: `double/2` (simple), `log_msg/1` (effector), `count_to/2` (generator).
- [ ] `double(21, X).` → `X = 42`.
- [ ] `count_to(3, Y).` → `Y = 1`, `Y = 2`, `Y = 3` (три решения).
- [ ] `run.` → в консоли `[LOG] 42`, `[LOG] 1`, `[LOG] 2`, `[LOG] 3` (4 строки), в результате `── 1 решение(й) ──` (успех без переменных).
- [ ] Отредактировать `my_actions.py` (поменять `x * 2` на `x * 3`), нажать 🔄 Перезагрузить → `double(21, X).` → `X = 63`.
- [ ] Удалить `my_actions.py` → 🔄 → `⚡ Зарегистрированные действия` пусто, `double(21, X).` → `False`.

#### 5.2.3. Context

- [ ] 🔌 Контекст: ключ `target_x`, значение `12.0` → ➕ → `✓ context['target_x'] = float`.
- [ ] 🔄 Применить → `✓ context применён; ключей: 1`.
- [ ] 🔄 Список → `[{"key": "target_x", "type": "float", "repr": "12.0"}]`.
- [ ] 🗑️ по ключу `target_x` → `✓ context['target_x'] удалён`.
- [ ] 🔄 Список → `[]`.

#### 5.2.4. Semantic

- [ ] Открыть `semantic/kb.pl` (📚).
- [ ] 🧬 Semantic: backend `st`, model `paraphrase-multilingual-mpnet`, local path = ваш путь, local only = ☐ → ✅ ON.
- [ ] Бейдж: `🟢 ON backend=st threshold=0.82 soft_cos_min=0.55 (builtin)`.
- [ ] `sem_msg`: `✓ Semantic: st (local)` или `✓ Semantic: st (HF fallback)`.
- [ ] `sem_status_json`: `{"enabled": true, ...}`.
- [ ] Запрос `city(moscow).` → `True`.
- [ ] Запрос `city(moskva).` → с дефолтным `lev_max=0.55` → `True`.
- [ ] 🔬 compare `moskva` / `moscow` → JSON с `cos`, `lev`, `verdict` = `soft`.
- [ ] `❌ OFF` → `city(moskva).` → `False`.
- [ ] Local path = `D:\nonexistent` + local_only ☑ → ✅ ON → `✗ Локальная папка модели не найдена`.
- [ ] Local path = `D:\nonexistent` + local_only ☐ → ✅ ON → `✓ Semantic: st (HF fallback)` + предупреждение.
- [ ] `🔧 Thr` при выключенном semantic → `✗ Semantic не включён`.

#### 5.2.5. Timeouts

- [ ] Поле timeout пусто → ▶ Run на быстром запросе → работает (fallback 30).
- [ ] Поле = `abc` → ▶ Run → работает (fallback 30).
- [ ] Поле = `0` → fallback 30.
- [ ] Поле = `2` + бесконечный запрос (`loop :- loop.`) → `⏱ Таймаут 2.0s`. **Не зависает.**
- [ ] В консоли не растут потоки после нескольких таймаутов (диагностика: `threading.active_count()`, добавить в `diagnostics` при необходимости).

#### 5.2.6. Trace + Breakpoints

- [ ] Открыть `breakpoints/kb.pl`.
- [ ] Breakpoints = `loop`, запрос `run_loop.` → 🔍 Trace.
- [ ] Пауза: `⏸ Пауза: loop(...) | Hit: 1`. Кнопки `⏵ ⏭ ⛔` активны.
- [ ] ⏵ Cont → продолжает до следующей паузы.
- [ ] ⏭ Step → один шаг.
- [ ] ⛔ Abort → `⛔ Aborted`.
- [ ] ↺ Reset → `Сброшено`, счётчик `Hit` сбрасывается.
- [ ] HTML-дерево: зелёные ok, красные fail, фиолетовые builtin.
- [ ] Клик по строке в `Шаги` → `subst` показывает `unification` (fallback).

#### 5.2.7. Sessions

- [ ] Открыть IDE в двух вкладках. В каждой — свой проект (A в первой, B во второй).
- [ ] Изменения в A не влияют на B.
- [ ] Перезагрузка страницы — новая сессия (старая уходит из LRU при переполнении).

### 5.3. Регрессия (после любого изменения, 5 мин)

**Ядро не должно пострадать:**

- [ ] `python -c "from prolog.solver import Solver; s=Solver('a(1). b(2).'); print(s.find_solutions('a(X).'))"` → `[{'X': 1}]`.
- [ ] `python -c "from prolog.embedding_unify import semantic_status; print(semantic_status())"` → без ошибок.

**IDE не должна сломаться:**

- [ ] `python -c "from pyagentprolog_ide import build_ui; ui = build_ui(); print('ok')"` → `ok`.
- [ ] Три примера (`family`, `factorial`, `lists`) открываются, запросы работают.
- [ ] `📚 База знаний` и `⚡ Зарегистрированные действия` раскрываются и заполняются.

**Кнопки не сломались:**

- [ ] Все кнопки в колонке 1 (`📂 🆕 💾 📚`) нажимаются, ничего не виснет.
- [ ] Все icon-only кнопки (`▶ ⏩ 📡 ⏹ 🔍 ⏵ ⏭ ⛔ ↺`) нажимаются, меняют состояние.
- [ ] Все `🔄` внутри accordion'ов (`Context`, `Semantic`, `Diagnostics`) работают.

**Не должно появиться:**

- [ ] `ValueError: Language prolog not supported` (в Gradio 6 → fallback на `python`).
- [ ] `UserWarning: theme` (в Gradio 6 → theme в `launch()`, не в `Blocks()`).
- [ ] `AttributeError: 'NoneType' has no attribute 'unify'` — значит, `Agent` не создан, а запрос идёт.

### 5.4. Тестирование «на глаз» в консоли

При ошибках сразу смотреть консоль IDE:

| Симптом в консоли | Что искать |
|---|---|
| `[actions import] ...` | Ошибка импорта `my_actions.py` (синтаксис/ImportError) |
| `Traceback` | Неперехваченное исключение — баг |
| `ValueError` / `TypeError` | Несовпадение сигнатуры (например, Gradio API) |
| `RecursionError` | Бесконечный Prolog-запрос, не защищённый timeout |
| `RuntimeError: dictionary changed size` | Мутация `context`/`rules` во время итерации |

---

## 6. Известные особенности и неочевидные решения

### 6.1. Timeout не убивает запрос

`_run_with_timeout` использует `daemon=True` + `t.join(timeout)`. После таймаута `TimeoutError` бросается, но **worker продолжает крутиться**. Это ограничение ядра (`interpreter._solve_iterative` не поддерживает отмену).

**Что делать:**
- При повторных таймаутах — перезапустить IDE.
- Для настоящей отмены нужен `CancelToken` в ядре (§6.5).

### 6.2. Drag-drop `.pl` не устанавливает проект

Gradio всегда копирует загруженный файл во временную папку (`/tmp/...`). Оригинальный путь теряется. Поэтому **drag-drop = «загрузить в редактор»**, а не «открыть проект».

**Что делать:** для работы с проектом — 📂 или 🆕. Предупреждение в статусе объясняет это пользователю.

### 6.3. `subst_before/after` пусты по умолчанию

`ProofTracer` не заполняет их без патча `interpreter.py`. Fallback — `unification` (bindings головы правила) — обычно достаточно.

**Опциональный патч** (см. §6.5).

### 6.4. Реимпорт `my_actions.py` — по `mtime_ns + size`

Если файл меняется дважды в одну наносекунду (крайне редко) — реимпорт может не сработать. В этом случае помогает 🔄 Перезагрузить в редакторе.

### 6.5. Опциональные патчи в ядре (не обязательны)

**`subst_before/after`:** в `interpreter.py` после `trace_step = self.tracer.start_goal(...)` добавить:

```python
self.tracer.set_substitutions(frame.subst, new_subst)
```

**`CancelToken`:** требует изменения `_solve_iterative` + `Agent.query/stream`. ~80 строк. Пока не реализовано.

### 6.6. Локальные HF-модели

`semantic_enable` использует `detect_text_prefix(resolve_model_id(model))` для префикса, `model=local_path` — для загрузки. Если `local_path` заполнен и папка есть — `st_local_files_only=True`. Иначе fallback на `model` (HF Hub).

**Проверка:** `🔬 compare` после ✅ ON покажет реальный `cos`.

### 6.7. Gradio 4 / 5 / 6

`_gradio_compat.py` возвращает:
- `code_language()` → `python` в Gradio 6, `prolog` в 4/5, если доступен.
- `blocks_kwargs()` → `{"theme": dark_theme()}` в 4/5, без theme в 6.
- `launch_kwargs()` → `{"theme": dark_theme()}` в 6, пусто в 4/5.

**Не менять логику версий без явного запроса** — иначе сломается на другой версии.

### 6.8. `eval` в `context_set`

`context_set` использует `eval` в глобальном namespace. Это **принятое решение** для локальной IDE. Для продакшна — не использовать без песочницы.

### 6.9. LRU сессий — 100

`sessions.py` — `_MAX_SESSIONS = 100`. При переполнении вытесняется самая старая. Если нужно больше — увеличить (осторожно с памятью).

### 6.10. Компактные CSS-классы

| Класс | Высота | Шрифт | Где |
|---|---|---|---|
| `compact-btn` | 26px | 12px | Обычные кнопки |
| `tiny-btn` | 22px | 11px | Icon-only кнопки |
| `compact-tb` | min 26px | 12px | Textbox |
| `compact-lbl` | — | 11px | Label |
| `tiny-row` | — | — | Ряд для icon-only |

Добавляйте новые кнопки с `elem_classes=["compact-btn"]` или `["tiny-btn"]`.

---

## 7. Как передать в новый диалог

### 7.1. Что приложить

**Обязательно:**
- Все файлы `pyagentprolog_ide/*.py` (7 файлов).
- Этот протокол.

**Желательно:**
- `pyproject.toml`.
- Версия `gradio` и `prolog` (`pip show`).
- Скриншот проблемной области (если есть).

**Не нужно:**
- Файлы ядра `prolog/*` — IDE их не меняет, они стабильны.
- `README.md` — он производный, восстанавливается по коду.
- Примеры — они тривиальны.

### 7.2. Как задать задачу

Шаблон сообщения в новый диалог:

```
Контекст: см. приложенный протокол (PROTOCOL.md).
Версии: gradio X.Y.Z, pyagentprolog A.B.C, Python 3.11.
Задача: <что нужно сделать>.
Ожидаемое поведение: <что должно быть>.
Фактическое поведение: <что есть>.
Сценарий воспроизведения: <шаги>.
```

### 7.3. Как зафиксировать изменение

После получения патча:

1. Применить.
2. **Smoke-тест** §5.1 — обязательно.
3. **Feature-тест** §5.2 по изменённой области.
4. **Регрессия** §5.3 — обязательно.
5. Если что-то сломалось — вернуть предыдущий патч, сообщить ассистенту с деталями.

### 7.4. Чек-лист приёмки фичи

- [ ] Патч применён.
- [ ] Smoke-тест пройден.
- [ ] Feature-тест по новой области пройден.
- [ ] Регрессия пройдена.
- [ ] В консоли IDE нет новых `Traceback`/`Warning`.
- [ ] README и/или протокол обновлены, если фича меняет пользовательские сценарии.
- [ ] Версия `__version__` в `pyagentprolog_ide/__init__.py` повышена (patch/minor).

---

## 8. Приложение A: API класса `PrologIDE`

| Метод | Назначение |
|---|---|
| `_ensure_agent(text) → Agent` | Создать/пересоздать `Agent` при изменении текста |
| `_load_project_actions()` | Импорт/реимпорт `my_actions.py` |
| `set_project(inp) → str` | Установить проект (папка/файл), обновить `sys.path` |
| `get_project_info() → dict` | `{project_dir, kb, my_actions, actions_loaded, sys_path_has_project}` |
| `load_kb_from_project() → (text, msg)` | Прочитать `kb.pl` + `load_program` |
| `save_project(text) → str` | Записать `kb.pl` |
| `new_project(path) → (text, msg)` | Создать папку + шаблон `kb.pl` |
| `load_program(text) → str` | Пересоздать `Agent` с новым текстом |
| `check_program(text) → str` | Только `Parser.parse_rules` |
| `run_query(text, query, timeout) → (res, out)` | Все решения |
| `run_first(text, query, timeout) → (res, out)` | Первое решение |
| `run_stream(text, query, per_item_timeout)` | Generator решений |
| `run_traced(text, query, timeout, bp)` | Generator состояний trace |
| `get_kb(text) → list[dict]` | Правила |
| `get_index(text) → dict` | Индекс |
| `get_actions() → list[dict]` | Список действий |
| `context_set(key, expr) → str` | `eval` + `context[key]` |
| `context_delete(key) → str` | Удалить ключ |
| `context_list() → list[dict]` | `[{key, type, repr}]` |
| `context_apply(text) → str` | Пересоздать `Agent` с новым context |
| `semantic_status() → dict` | Статус unifier |
| `semantic_enable(...) → (msg, status)` | Включить |
| `semantic_disable() → (msg, status)` | Отключить |
| `semantic_set_threshold(v) → (msg, status)` | Только порог |
| `semantic_compare(a, b) → dict` | Диагностика пары |
| `diagnostics() → dict` | Снимок состояния |

---

## 9. Приложение B: Константы

| Константа | Где | Значение | Назначение |
|---|---|---|---|
| `KB_FILENAME` | `project.py` | `"kb.pl"` | Имя основного файла |
| `ACTIONS_FILENAME` | `project.py` | `"my_actions.py"` | Имя файла действий |
| `_MAX_SESSIONS` | `sessions.py` | `100` | LRU |
| `_to_timeout` default | `app.py` | `30.0` | Fallback таймаута |
| `timeout_input min/max` | `app.py` | `0.5 / 600.0` | Диапазон поля |
| `_TREE_CSS` max-height | `tree_view.py` | `420px` | Высота дерева |
| `sem_threshold` | `app.py` | `0.82` | Дефолт (слайдер) |
| `sem_soft` | `app.py` | `0.55` | Soft cos min |
| `sem_lev_max` | `app.py` | `0.55` | Lev max (поднято с 0.35) |
| `sem_lev_typo` | `app.py` | `0.20` | Lev typo max |
| `sem_model` | `app.py` | `paraphrase-multilingual-mpnet` | Дефолтная модель |
| `sem_local_path` | `app.py` | `D:\hf_embedding\paraphrase-multilingual-mpnet` | Дефолтный путь |

---

## 10. Приложение C: CSS-классы

```css
.compact-btn   /* 26px, 12px шрифт */
.compact-tb    /* min 26px, 12px */
.compact-lbl   /* label 11px, серый */
.tiny-btn      /* 22px, 11px, min-width 24px, flex: 0 0 auto */
.tiny-row      /* gap 2px, flex-wrap: nowrap */
.status-box    /* pre: моно, 11px, max-height 100px */
.proj-info     /* div: 11px, серый, word-break */
.col-head      /* заголовок колонки: 14px, 600 */
```

---

## 11. Приложение D: Быстрая диагностика

**«Не открывается проект»:**
1. Смотрим `project_status`: `✗ Папка не найдена` или `✓ Проект: ...`.
2. Если `✗` — путь не существует или это не папка.
3. Если `✓` — смотрим `kb: ...`. Если `—` — в папке нет `.pl`.

**«Действия не работают»:**
1. `📚 База знаний` → смотрим правила — есть ли `run :- ...`.
2. `⚡ Зарегистрированные действия` → пусто?
3. `my_actions.py` есть рядом с `kb.pl`?
4. В консоли IDE — `[actions import] ...` (значит, ошибка импорта)?
5. Нажать 🔄 Перезагрузить.

**«Semantic не включается»:**
1. Бейдж: 🔴 OFF → смотрим `sem_msg`.
2. `requires sentence-transformers` → `pip install`.
3. `ConnectionError` → Ollama не запущен.
4. `local path not found` → проверить `Local path`.

**«Запрос зависает»:**
1. Поле `Timeout` пусто или `0`? → ставим `5`.
2. Запрос возвращает много решений без конца? → `⏩ First` вместо `▶ Run`.
3. `loop :- loop.`? → перезапуск IDE.

**«Ошибка в консоли после старта»:**
1. `ValueError: Language prolog not supported` → Gradio 6, fallback на `python` (должно быть автоматически).
2. `UserWarning: theme` → Gradio 6, theme в `launch()` (должно быть автоматически).
3. Если что-то ещё — смотреть traceback, обычно `_gradio_compat.py` требует обновления.

---

## 12. Итоговый чек-лист приёмки

Перед закрытием задачи:

- [ ] Smoke-тест §5.1 пройден.
- [ ] Feature-тест §5.2 по изменённой области пройден.
- [ ] Регрессия §5.3 пройдена.
- [ ] `__version__` обновлён (patch: bug fix, minor: new feature).
- [ ] `README.md` обновлён (если меняются пользовательские сценарии).
- [ ] Этот протокол обновлён (если меняется архитектура, добавляется файл, меняется контракт с ядром).
- [ ] Примеры (если затронуты) проверены.
- [ ] В консоли нет новых `Traceback`/`Warning`.

---

*© 2026 Andrey Vorfolomeev. Protocol v1.0.*

*Для передачи в новый диалог: скопируйте этот документ целиком + приложите `pyagentprolog_ide/*.py` + `pyproject.toml`. Ассистенту достаточно этих данных, чтобы продолжить разработку без пересказа.*