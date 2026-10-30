
*Документ фиксирует все решения, ошибки и исправления в порядке их появления. Может использоваться как отправная точка для нового диалога и как источник «почему так сделано».*

---

## Фаза 0. Постановка задачи

**Исходная задача:** разработать IDE для PyAgentProlog — Prolog-движка на Python с агентами, трассировкой и семантической унификацией.

**Контекст:** ядро `pyagentprolog` уже существует; IDE должна быть надстройкой, использующей его публичный API.

---

## Фаза 1. Ключевое архитектурное решение — где жить IDE

### 1.1. Первый вариант (отвергнут)

Первоначально я предложил положить всё в `prolog/ide.py` — монолитный файл в пакете ядра.

**Проблемы этого варианта (выявлены при обсуждении):**

| Проблема | Следствие |
|---|---|
| `gradio` (~200 MB) попадёт в `install_requires` ядра | Ядро нельзя поставить без Gradio |
| IDE меняется каждый день, ядро — раз в месяц | Связывание версий ломает совместимость |
| `exec(user_code)` в IDE | Ядро не должно **импортировать** код, выполняющий произвольный Python |
| Тесты ядра потянут headless-браузер | CI раздувается |
| Альтернативные фронтенды (TUI, Electron, VS Code) | Все вынуждены зависеть от `prolog/ide.py` |

### 1.2. Решение: отдельный пакет (`Вариант A`)

**Структура:**

```
D:\bfx\Repositories\
├── pyagentprolog\           ← ядро (не трогаем)
└── pyagentprolog-ide\       ← IDE (отдельный пакет)
    ├── pyproject.toml
    └── pyagentprolog_ide\
        ├── app.py           ← главный файл
        ├── _gradio_compat.py
        ├── actions_ctx.py
        ├── breakpoints.py
        ├── project.py
        ├── sessions.py
        ├── streaming.py
        ├── tree_view.py
        └── examples/
```

**Контракт:** IDE зависит от `pyagentprolog` и `gradio`. Ядро не знает об IDE. Односторонняя зависимость.

**Зафиксировано.** Это решение больше не пересматривалось.

---

## Фаза 2. Функциональные требования

Из обсуждения выявлены 5 обязательных расширений (изначально предложены в одном из ответов):

1. **HTML-дерево доказательства** вместо plain text.
2. **Клик по шагу → просмотр subst**.
3. **Breakpoints** через подмену `ProofTracer.end_goal`.
4. **Множественные сессии** через `gr.State` + LRU-реестр.
5. **Асинхронный стриминг** решений через `agent.stream()`.

Плюс базовые элементы: редактор, проект, context, semantic, диагностика.

---

## Фаза 3. Первый запуск и Gradio-совместимость

### 3.1. Ошибка №1 — `Language prolog not supported`

**Симптом:**
```
ValueError: Language prolog not supported.
  editor = gr.Code(language="prolog", ...)
```

**Причина:** Gradio 6 валидирует `gr.Code.language` по белому списку; `prolog` в нём отсутствует. Gradio 4/5 — поддерживал через CodeMirror legacy modes.

**Решение:** создать `_gradio_compat.py` с функцией `code_language()`, которая:
1. Проверяет `_GRADIO_MAJOR`.
2. В 6.x — сразу возвращает `"python"` (ближайший по подсветке операторов и переменных).
3. В 4/5 — ищет `SUPPORTED_LANGUAGES` / `CODE_LANGUAGES` / `LANGUAGES` на `gradio.components.code`.
4. Если список найден — `prolog`, если есть; иначе `python`.
5. Кеширует результат в `_lang_cache`.

**Урок:** любая валидация в Gradio 6 может упасть — всегда через fallback.

### 3.2. Ошибка №2 — `theme` в `Blocks()`

**Симптом:**
```
UserWarning: The parameters have been moved from the Blocks constructor
to the launch() method in Gradio 6.0: theme.
```

**Причина:** в Gradio 6 `theme` переехал из `gr.Blocks()` в `ui.launch()`.

**Решение:** функции `blocks_kwargs()` / `launch_kwargs()` в `_gradio_compat.py`, которые раскладывают аргументы по версии:

```python
def blocks_kwargs(css="", head=""):
    d = {"title": "PyAgentProlog IDE"}
    if _GRADIO_MAJOR < 6:
        d["theme"] = dark_theme()
        if css: d["css"] = css
        if head: d["head"] = head
    return d

def launch_kwargs(css="", head=""):
    d = {}
    if _GRADIO_MAJOR >= 6:
        d["theme"] = dark_theme()
        if css: d["css"] = css
        if head: d["head"] = head
    return d
```

### 3.3. Ошибка №3 — `css` тоже переехал

**Симптом:**
```
UserWarning: The parameters have been moved from the Blocks constructor
to the launch() method in Gradio 6.0: css.
```

**Причина:** то же, что с `theme`, но выяснилось позже.

**Решение:** тот же `blocks_kwargs(css=...)` / `launch_kwargs(css=...)`.

### 3.4. Ошибка №4 — `TypeError: 'dict' object is not callable`

**Симптом:**
```
File "app.py", line 1584, in launch
    **launch_kwargs(),
TypeError: 'dict' object is not callable
```

**Причина:** в теле `launch()` была строка `launch_kwargs = dict(...)`, которая **перекрыла** импортированную функцию `launch_kwargs` из `_gradio_compat`. Классический Python-shadowing.

Плюс были **дубли аргументов** (`share=`, `server_name=`, `server_port=` передавались и через `**launch_kwargs()`, и явно), и `kwargs` тоже дублировался.

**Решение — полная переработка `launch()`:**

```python
def launch(share=False, host="127.0.0.1", port=7860, **kwargs):
    ui = build_ui()
    kw = dict(share=share, server_name=host, server_port=port, inbrowser=True)
    favicon = _ensure_favicon()
    if favicon:
        kw["favicon_path"] = favicon
    kw.update(launch_kwargs(_GLOBAL_CSS, _HEAD_DARK))
    kw.update(kwargs)
    ui.launch(**kw)
```

Локальная переменная называется `kw`, никакого shadowing. Все аргументы собираются в один dict и передаются один раз.

**Урок:** не называть локальные переменные так же, как импортированные функции. Использовать `kw`, `opts`, `params`, а не `kwargs`/`launch_kwargs`/`blocks_kwargs` в телах функций.

---

## Фаза 4. Favicon

### 4.1. Задача

Пользователь хотел favicon в браузерной вкладке.

### 4.2. Решение

Функция `_ensure_favicon()`:

1. Ищет `favicon.{png,ico,svg}` в корне пакета или `assets/`.
2. Если файла нет — **генерирует дефолтный SVG** (индиго-квадрат с белой «P») и сохраняет в `pyagentprolog_ide/favicon.svg`.
3. Возвращает путь.

В `launch()`:
```python
favicon = _ensure_favicon()
if favicon:
    kw["favicon_path"] = favicon
```

**Урок:** не полагаться на внешние ресурсы — генерировать дефолт при отсутствии.

---

## Фаза 5. Тёмная тема и компактная вёрстка

### 5.1. Тёмная тема

**Задача:** заменить светлую тему на тёмную.

**Решение:** `dark_theme()` в `_gradio_compat.py` на базе `gr.themes.Soft()` с явными `.set(...)`:
- `body_background_fill="#0f1115"`
- `background_fill_primary="#161a20"`
- `button_primary_background_fill="#4f46e5"` (индиго)
- и т.д.

Работает во всех ветках Gradio 4/5/6 (с поправкой на место передачи).

### 5.2. Компактные CSS-классы

**Задача:** кнопки и поля занимают слишком много места.

**Решение — CSS-классы:**

| Класс | Применение | Высота | Шрифт |
|---|---|---|---|
| `compact-btn` | Обычные кнопки | 26px | 12px |
| `tiny-btn` | Icon-only | 22px | 11px |
| `compact-tb` | Textbox | min 26px | 12px |
| `compact-lbl` | Label | — | 11px |
| `tiny-row` | Ряд для icon-only | gap 2px, nowrap | — |
| `col-head` | Заголовок колонки | — | 14px, 600 |
| `proj-info` | Инфо-блок проекта | — | 11px, серый |

### 5.3. Раскладка в 3 колонки

**Было:** вкладки `📁 Проект`, `📝 Редактор`, `📚 KB`, `⚡ Действия`, `🔎 Запрос`, `🧬 Semantic`, `🔬 Диагностика` + верхняя панель с `Load/Check/Clear/Status`.

**Проблема:** верхняя панель и вкладки занимали ~200px по вертикали, из-за чего рабочее поле было маленьким.

**Решение:**

- **Колонка 1** — проект + настройки (Context, Semantic, Диагностика — в `gr.Accordion`, закрыты по умолчанию).
- **Колонка 2** — редактор + Действия + KB (в accordion).
- **Колонка 3** — запрос + результаты + трассировка + breakpoints.
- Верхняя панель **удалена** — все кнопки распределены по колонкам.

### 5.4. Icon-only кнопки в один ряд

**Было:** `▶ Run`, `⏩ First`, `📡 Stream`, `⏹ Stop` — 4 кнопки в одном ряду с полем `Timeout`. Не помещались.

**Решение:**

1. Поле `Timeout` — отдельным рядом сверху.
2. Кнопки — отдельным рядом под полем, только иконки: `▶ ⏩ 📡 ⏹`.
3. Аналогично для трассировки: `🔍 ⏵ ⏭ ⛔ ↺`.
4. CSS: `.tiny-btn` (22px, 11px шрифт, min-width 24px, `flex: 0 0 auto`), `.tiny-row` (`gap: 2px`, `flex-wrap: nowrap`).

**Урок:** в тесной колонке — только иконки + tooltip в подписи (или `Markdown` рядом).

### 5.5. Dataframe — светлый, не поддался

**Проблема:** `gr.Dataframe` (шаги, subst) рендерится **вне** темы Gradio. Стандартные `--body-background-fill` и прочие переменные **не применяются** к ячейкам таблицы.

**Первая попытка:** правила для `.gradio-dataframe td` / `[role="gridcell"]`. **Не сработало.**

**Причина:** в Gradio 6 DOM Dataframe переписан; классы/ARIA-роли не совпадают с ожидаемыми.

**Вторая попытка:** бланкет `.gradio-dataframe *` + CSS-переменные `--table-odd-background-fill` и т.д. через `<style>` в `head=` (а не в `css=`). **Частично сработало.**

**Третья попытка (рекомендация, не подтверждена):** `elem_id="steps_df"` / `elem_id="subst_df"` + правила `#steps_df *`, `#subst_df *`.

**Итог (на момент завершения диалога):** проблема **не закрыта окончательно**. Требуется либо:

1. Проверить в DevTools, какой элемент реально белый (какой класс/тег).
2. Прислать имя класса/`data-testid` в ответе.

**Урок:** Gradio может иметь компоненты, которые игнорируют тему. Всегда проверять в DevTools, а не угадывать.

---

## Фаза 6. Работа с проектами

### 6.1. Модель проекта

**Решение:** проект = папка с `kb.pl` (обязательно) и `my_actions.py` (опционально).

Функции в `project.py`:
- `resolve_project_dir(inp)` — путь к папке из строки/файла.
- `register_project_dir(dir)` / `unregister_project_dir(dir)` — `sys.path`.
- `find_kb(dir)` — найти `kb.pl` или первый `.pl`.
- `actions_module_path(dir)` — путь к `my_actions.py`.
- `actions_signature(path)` — `(mtime_ns, size)` для детекта изменений.

### 6.2. Ошибка — кнопки Открыть/Создать/Сохранить не работали

**Проблема:** `handle_save_project` не использовал поле `project_path`, `handle_open_project` не обновлял его, диалог выбора папки показывал только папки.

**Решение:**

1. **📂 Открыть** → `_pick_pl_file()` (диалог выбора **файла** с фильтром `*.pl`), не `_pick_folder`. Файлы видны рядом с папками.
2. **🆕 Создать** → `_pick_folder()` (диалог выбора **папки** — тут логично).
3. **💾 Сохранить** → сначала `set_project(path)` если путь отличается, потом `save_project`.
4. Все три обновляют `project_path` и `project_status`.

**Зафиксировано:** `Открыть` — файл, `Создать` — папка.

### 6.3. Ошибка — drag-drop `.pl` не устанавливал проект

**Причина:** Gradio всегда копирует загруженный файл во временную папку (`/tmp/...`). Оригинальный путь теряется, IDE не может определить папку проекта.

**Решение:**

1. Переименовать кнопку/поле: `📄 Бросить .pl в редактор (не меняет проект)`.
2. `handle_drop_pl` — только читает содержимое и кладёт в редактор.
3. Статус **явно** предупреждает: «Drag-drop всегда копирует файл во временную папку Gradio. Папка проекта не определена автоматически».

**Урок:** нельзя совмещать «загрузить файл» и «установить проект» — Gradio этого не позволяет.

### 6.4. Примеры — из dropdown в отдельные проекты

**Было:** dropdown `Пример` со списком строк из `examples.py` (`EXAMPLES` dict).

**Задача:** сделать примеры настоящими проектами (`examples/<name>/kb.pl`).

**Решение:**

1. Удалён `examples.py`, удалён dropdown.
2. Создано 6 подпапок в `pyagentprolog_ide/examples/`: `family/`, `factorial/`, `lists/`, `cut_ite/`, `breakpoints/`, `semantic/`.
3. Кнопка `📚` → диалог выбора `.pl` в `examples_root()`, выбирает `kb.pl` из подпапки.
4. `examples_root()` добавлен в `project.py`.

**Урок:** примеры должны быть полноценными проектами (с возможностью добавить `my_actions.py`), а не строками.

---

## Фаза 7. Python-действия и Context

### 7.1. Модель действий

**Задача:** подключать Python-предикаты, лежащие рядом с `kb.pl`.

**Решение (финальное):**

1. `my_actions.py` — обычный Python-модуль с `@simple_action`/`@effector_action`/`@generator_action`.
2. IDE импортирует его **автоматически** в `_load_project_actions()` при (пере)создании `Agent`.
3. `importlib.reload` если `(mtime_ns, size)` изменился.
4. **Не нужно** вызывать `agent.register_action` вручную — IDE делает `agent.register_action_module(mod)`.

### 7.2. «Способы 3 и 4» — отказ от inline и module-by-name

**Было:** вкладка «⚡ Действия» с inline-кодом и полем для имени модуля.

**Проблема:** пользователю приходилось дважды кликать (кнопка + открыть accordion), данные не отображались, потому что accordion был закрыт.

**Решение:**

1. **Удалены** `register_python_actions`, `register_module`, `unregister_module`, `reset_actions`.
2. Вкладка заменена на **📁 Проект** с полями `project_path`, `my_actions.py` подхватывается автоматически.
3. **Context** (внешние ресурсы) — оставлен отдельной вкладкой `🔌 Контекст`:
   - `context_set(key, expr)` через `eval`.
   - `context_delete(key)`.
   - `context_apply(text)` — пересоздаёт `Agent` с новым context.
   - `context_list()`.

**Урок:** чем меньше ручных шагов — тем лучше. Автоматическая регистрация действий снижает вероятность ошибок.

### 7.3. ContextRegistry

**Задача:** сохранять внешние ресурсы (LLM, БД) между перезагрузками `Agent`.

**Решение:** класс `ContextRegistry` в `actions_ctx.py`:

- `values: dict` — статические значения.
- `builders: list[callable]` — функции пересборки (если ресурс одноразовый).
- `apply() → dict` — новый context для `Agent(text, context=ctx)`.

**Урок:** статика + builders лучше, чем только `dict` — позволяет пересоздавать клиенты при смене проекта.

---

## Фаза 8. Семантическая унификация

### 8.1. Ошибка — `sem_status_json` не менялся с false на true

**Симптом:** пользователь нажимает `✅ ON`, `sem_msg` показывает успех, но `sem_status_json` остаётся `{"enabled": false}`.

**Причина:** `sem_status_json` обновлялся только при нажатии `🔄`. Кнопки `✅`/`❌`/`🔧` пишут результат только в `sem_msg`.

**Решение:**

1. `semantic_enable` / `semantic_disable` / `semantic_set_threshold` теперь возвращают `(msg, status)`.
2. Wiring: `.click(..., outputs=[sem_msg, sem_status_json])`, затем `.then(handle_sem_status_html, ..., [sem_badge])`.
3. Добавлен **визуальный бейдж** `_sem_badge_html`: `🟢 ON` / `🔴 OFF` + backend + threshold + soft_cos_min.
4. `custom` убран из dropdown — без `embed_fn` он всегда падал.
5. Понятные ошибки: `requires sentence-transformers`, `ollama: сервер на ...`.

**Урок:** каждое действие должно само обновлять все зависимые компоненты; пользователь не должен знать про «нажмите ещё и 🔄».

### 8.2. Ошибка — `city(moskva)` не матчится с `city(moscow)`

**Симптом:** включён semantic, но запрос возвращает `False`.

**Причина:** `lev("moskva", "moscow") = 0.5`, `cos ≈ 0.55–0.70`. С дефолтными `threshold=0.82, soft_cos_min=0.55, lev_max=0.35` — soft-коридор не срабатывает (lev = 0.5 > 0.35), hard — не хватает (cos < 0.82).

**Решение:**

1. **🔬 Compare pair** — диагностический инструмент: вводит `A` и `B`, возвращает JSON с `cos`, `lev`, `verdict`, `hints`.
2. `hints` — конкретные рекомендации: «увеличьте Lev max до 0.55», «уменьшите Soft cos min до 0.50».
3. `sem_lev_max` дефолт поднят с `0.35` до `0.55`.

**Пример вывода Compare:**
```json
{
  "cos": 0.62, "lev": 0.5, "verdict": "NONE",
  "hints": ["cos=0.620 в soft-коридоре, но lev=0.500 > lev_max=0.35 → увеличьте Lev max до 0.55"]
}
```

**Урок:** когда ML-порог не срабатывает, инструмент должен **объяснить**, почему. Не «не работает», а «вот cos, lev, вердикт, вот что крутить».

### 8.3. Локальные HF-модели

**Задача:** использовать `D:\hf_embedding\paraphrase-multilingual-mpnet` без обращения к HF Hub.

**Решение:**

1. Добавлено поле `Local path` в UI.
2. В `semantic_enable`:
   - Если `local_path` существует → `semantic_on(model=local_path, st_local_files_only=True)`.
   - `text_prefix` вычисляется через `detect_text_prefix(resolve_model_id(model))` — по **имени**, не по пути (иначе E5/nomic потеряют префикс).
   - Если папки нет и `local_only=False` → fallback на HF (`model=model`).
   - Если папки нет и `local_only=True` → ошибка.
3. Чекбокс `Только локально (не скачивать с HF)`.

**Урок:** путь к модели и имя модели — разные сущности. Имя для префикса, путь для загрузки.

---

## Фаза 9. Timeout

### 9.1. Ошибка — `ValueError` при пустом/невалидном поле

**Причина:** `float(timeout)` падал на `""`, `"abc"`, `0`, `-5`.

**Решение:** `_to_timeout(v, default=30.0)`:

```python
def _to_timeout(v, default=30.0):
    try:
        x = float(v)
        return x if x > 0 else default
    except (TypeError, ValueError):
        return default
```

Все хендлеры (`handle_run`, `handle_first`, `handle_stream`, `handle_trace`) прогоняют timeout через `_to_timeout`.

### 9.2. Честное объяснение семантики

**Зафиксировано:** Timeout **не убивает запрос**. Это защита от зависания UI, а не отмена. Daemon-поток продолжает работать. Для настоящей отмены нужен `CancelToken` в ядре (не реализовано).

**Урок:** честно документировать ограничения; не выдавать желаемое за действительное.

---

## Фаза 10. Тестирование и баг в `ParseSolution`

### 10.1. Тест с медицинской диагностикой

**Источник:** https://nweb42.com/books/prolog/primery-prilozheniy-dlya-ii/

**Программа:** симптомы → грипп/мигрень/бронхит.

**Ожидаемые результаты:**

| Запрос | Правильный ответ |
|---|---|
| `симптом(кашель, X).` | `X = грипп`, `X = бронхит` |
| `симптом(температура, X).` | `X = грипп` (одно) |
| `симптом(кашель,X), симптом(температура,X).` | `X = грипп` (одно) |

### 10.2. Обнаруженные баги

**Баг 1 — фантомный `true`:**

`симптом(температура, X).` → `['X = грипп', 'true']`, `count = 1`.

**Причина:** `ParseSolution` фильтровал `solutions_list` от `None`, но **не** фильтровал `outputs`. Оба списка рассинхронизировались: `solutions_list = [{"X": "грипп"}]`, `outputs = ["X = грипп", "true"]`.

Откуда в raw решениях второй элемент `{}` — отдельный вопрос (см. ниже).

**Баг 2 — compound-запрос давал 3 решения:**

`симптом(кашель,X), симптом(температура,X).` → `X=грипп, X=грипп, X=бронхит`.

**Диагностика:** `PROLOG_DEBUG_SOLUTIONS=1` показал, что **одиночные** запросы возвращают корректное число raw-решений:

```
[find_solutions] 'симптом(кашель, X).' → 2 raw
[find_solutions] 'симптом(температура, X).' → 1 raw
```

То есть solver для одиночных запросов работает. Compound-расхождение было следствием того же display-бага + возможной старой версии PyPI.

### 10.3. Исправление

**Фикс `ParseSolution`** (в `prolog/solver.py`) — параллельная фильтрация:

```python
pairs = [(s, o) for s, o in zip(solutions_list, outputs) if s is not None]
solutions_list = [s for s, _ in pairs]
outputs = [o for _, o in pairs]
```

Плюс проверка `if not solutions_list: result["output"] = "No solution"`.

**Результат после фикса:**

| Запрос | Было | Стало |
|---|---|---|
| `симптом(температура, X).` | `['X = грипп', 'true']`, count=1 | `X = грипп`, count=1 |
| `симптом(кашель,X), симптом(температура,X).` | 3 решения | **1 решение** `X = грипп` |
| `симптом(головная_боль,X), симптом(тошнота,X).` | 3 решения | **1 решение** `X = мигрень` |

**Зафиксировано:** источник (nweb42) был прав. Баг был в `ParseSolution`.

### 10.4. Уроки

1. **`ParseSolution` — критический слой.** Рассинхрон `solutions_list` / `outputs` даёт фантомные `true` и неверный `count`.
2. **Debug-вывод в `find_solutions`** — быстрый способ понять, баг в solver или в display.
3. **Проверка версии** — установленный из PyPI `pyagentprolog` мог отличаться от репозитория; переустановка `pip install -e . --force-reinstall` гарантирует соответствие.

---

## Сводная таблица решений

| Фаза | Решение | Обоснование |
|---|---|---|
| 1 | Отдельный пакет `pyagentprolog-ide` | Однонаправленная зависимость от ядра |
| 3 | `_gradio_compat.py` с `code_language` / `blocks_kwargs` / `launch_kwargs` | Gradio 4/5/6 имеют разные API |
| 4 | `_ensure_favicon` с автогенерацией SVG | Не зависеть от внешних файлов |
| 5 | `dark_theme()` + `compact-btn`/`tiny-btn` + CSS | Компактная тёмная вёрстка |
| 5 | Icon-only кнопки в один ряд | Экономия места в колонке 3 |
| 5 | Dataframe: бланкет + `head=` + `elem_id` | Проблема не закрыта окончательно |
| 6 | Проект = папка с `kb.pl` + `my_actions.py` | Стандарт структуры |
| 6 | `Открыть` — файл, `Создать` — папка | Логика: не создавать папку через файл-диалог |
| 6 | Drag-drop только в редактор, не в проект | Gradio копирует в temp |
| 6 | Примеры — подпапки, не dropdown | Полноценные проекты |
| 7 | `my_actions.py` авто-подхват, без ручной регистрации | Меньше шагов |
| 7 | `ContextRegistry` (values + builders) | Ресурсы пересоздаются при reload |
| 8 | `sem_status_json` обновляется всеми кнопками | Не требовать `🔄` после каждой операции |
| 8 | 🔬 Compare с `hints` | Объяснить, что крутить |
| 8 | `local_path` + `local_only` | Локальные HF-модели без сети |
| 9 | `_to_timeout` с fallback | Не падать на невалидном вводе |
| 10 | Параллельная фильтрация `solutions_list` / `outputs` | Убрать фантомный `true` |

---

## Ключевые файлы и их назначение

| Файл | Назначение | Приоритет |
|---|---|---|
| `app.py` | Всё: `PrologIDE`, `build_ui`, хендлеры, `launch` | ⭐⭐⭐ |
| `_gradio_compat.py` | Совместимость Gradio 4/5/6, тема | ⭐⭐⭐ |
| `project.py` | Работа с папкой проекта | ⭐⭐⭐ |
| `actions_ctx.py` | `ContextRegistry` | ⭐⭐ |
| `breakpoints.py` | `BreakpointController` / `Tracer` | ⭐⭐ |
| `tree_view.py` | HTML-дерево, хелперы DataFrame | ⭐⭐ |
| `streaming.py` | `stream_with_timeout` | ⭐⭐ |
| `sessions.py` | LRU-реестр (100) | ⭐ |
| `examples/*/kb.pl` | Примеры | ⭐ |

---

## Открытые вопросы на момент завершения

1. **Dataframe не тёмный** — требует DevTools-инспекции (имя класса/тега белого элемента).
2. **PyPI vs repo** — пользователь работает с `D:\bfx\bfx\Lib\site-packages\prolog`, а не из репозитория. Если репозиторий новее — нужен `pip install -e . --force-reinstall`.
3. **`CancelToken`** — для настоящей отмены запросов нужен патч в `prolog/interpreter.py` + `prolog/agent.py` (не реализовано).
4. **`subst_before/after`** — пусты без патча `interpreter.py` (`self.tracer.set_substitutions(frame.subst, new_subst)`). Fallback на `unification` работает.

---

## Итог

IDE прошла путь от «одного файла в ядре» до «отдельного пакета с тремя колонками, авто-подхватом действий, локальным semantic, диагностическим Compare и тёмной темой». Все ключевые ошибки (Gradio 6 API, shadowing `launch_kwargs`, светлый Dataframe, `false→true` в semantic, фантомный `true` в `ParseSolution`) исправлены или задокументированы.

**Главный урок:** IDE — это UI поверх ядра. Нельзя менять ядро при разработке UI, кроме явно согласованных патчей (например, `ParseSolution`). Все баги UI ловятся через `PROLOG_DEBUG_SOLUTIONS=1` + DevTools + минимальные воспроизводящие примеры.