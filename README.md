# PyAgentProlog IDE
> Web-based IDE for [PyAgentProlog](https://github.com/…/pyagentprolog) — a
> pure-Python Prolog engine with agents, tracing and semantic unification.

The IDE is a **separate package** (`pyagentprolog-ide`) that depends on the
core `pyagentprolog` and `gradio`. The core library knows nothing about the
IDE; the dependency is strictly one-way.

## Features

- **Project-based workflow** — one folder per program, containing `kb.pl`
  (Prolog source) and an optional `my_actions.py` (Python actions).
- **Dark three-column layout** — project & settings / editor / query & debug,
  all controls compact and icon-driven.
- **Auto-loaded Python actions** — `my_actions.py` is imported automatically
  on program reload; edits are detected by `mtime_ns + size` and trigger
  re-import without a restart.
- **External context registry** — LLM clients, DBs and API keys reach actions
  via `context['key']`, surviving program reloads.
- **Semantic unification** — match atoms by meaning (embeddings), with
  support for **locally stored Hugging Face models** (`local_files_only=True`)
  and optional fallback to HF Hub.
- **Semantic comparison tool** — one-click diagnostic for a pair of strings:
  shows `cos`, `lev`, current thresholds and actionable hints.
- **Timeouts per operation** — total for Run/First/Trace, per-item for
  Stream; user input is sanitised and falls back to 30 s.
- **Streaming** — incremental solutions via `agent.stream()` with a
  Stop button.
- **Tracing with breakpoints** — pause execution on selected predicates,
  inspect the proof tree (HTML), browse steps and substitutions.
- **Multiple sessions** — `gr.State` per browser tab, LRU registry of 100
  `PrologIDE` instances.
- **Built-in examples** — separate project folders under
  `pyagentprolog_ide/examples/`.

## Requirements

- Python 3.9+
- Core `pyagentprolog` (installed separately)
- `gradio >= 4.0`

Optional:

| Feature | Package |
|---|---|
| Semantic backend `st` | `sentence-transformers` |
| Semantic backend `ollama` | running `ollama` server on `http://localhost:11434` |
| Numba-accelerated arithmetic (inherited from core) | `numpy`, `numba` |

## Installation

```bash
# 1. Core library
pip install -e /path/to/pyagentprolog

# 2. IDE
pip install -e /path/to/pyagentprolog-ide

# with semantic extras:
pip install -e "/path/to/pyagentprolog-ide[semantic]"
```

## Running

```bash
python -m pyagentprolog_ide
# or
pyagentprolog-ide --host 0.0.0.0 --port 7860
```

CLI flags:

| Flag | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `7860` | Port |
| `--share` | off | Gradio public tunnel |

The UI opens at `http://127.0.0.1:7860`.

---

## Project structure

A **project** is a folder:

```
my_prolog_project/
├── kb.pl            # Prolog source (required)
└── my_actions.py    # Python actions (optional)
```

- `kb.pl` is loaded into the editor and parsed into the knowledge base.
- `my_actions.py` is imported when the program is (re)loaded and every
  function decorated with `@simple_action` / `@effector_action` /
  `@generator_action` is registered as a Prolog predicate.
- The project folder is added to `sys.path`, so `my_actions.py` may import
  sibling modules freely.
- Switching to another project removes the previous folder from `sys.path`
  and recreates the `Agent`.

---

## UI overview

Three independent columns, all compact, dark theme.

```
┌────────────────┬─────────────────────┬───────────────────────┐
│ 1. PROJECT     │ 2. PROGRAM          │ 3. QUERY & DEBUG      │
│                │                     │                       │
│ Drag-drop .pl  │ gr.Code editor      │ Query input           │
│ Path           │ Reload / Check /    │ Timeout + ▶ ⏩ 📡 ⏹   │
│ Open / New /   │ Clear               │ Result / Stream       │
│ Save / 📚      │ Status line         │ Breakpoints + 🔍 ⏵⏭⛔↺│
│ Context        │ ⚡ Actions (acc.)   │ Proof tree (HTML)     │
│ Semantic       │ 📚 KB (acc.)        │ Steps / subst tables  │
│ Diagnostics    │                     │                       │
└────────────────┴─────────────────────┴───────────────────────┘
```

### Column 1 — Project & settings

#### Drag-drop `.pl`

Reads the file and **loads its contents into the editor**. The project is
**not** changed — Gradio always copies uploads to a temporary directory, so
the original folder is unknown.

Use it to peek at an unrelated `.pl`, not to open a project. To work with a
project use **📂 Open** or **🆕 New**.

#### 📂 Open

- If the path field is **empty** → opens a native *file* dialog filtered to
  `*.pl` / `*.prolog`. You can see `.pl` files next to folders, pick
  `kb.pl` (or any other `.pl`) and the folder becomes the project.
- If the path field is **set** → opens that path directly:
  - a folder → picks `kb.pl`, otherwise the first `.pl`;
  - a `.pl` file → uses exactly that file, project = its parent folder.

On success the editor fills with the file, the path field is updated, and
`project_status` shows:
```
✓ Project: D:\Projects\my_prolog
  kb:            kb.pl
  my_actions.py: present
```

#### 🆕 New

Always opens a native *folder* dialog (creating a folder there is allowed).
Then:
1. Creates the folder if it does not exist.
2. Writes a `kb.pl` template if none exists.
3. Sets it as the current project and loads it into the editor.

#### 💾 Save

Writes the editor contents to the project's `kb.pl`.

- If the path field is set and differs from the current project → the
  project is switched first, then saved there.
- If no project is set → error.

**Save does not reload the `Agent`.** To make the new code active, press
**🔄 Reload** in column 2 (or simply change the editor text — `_ensure_agent`
recreates the `Agent` on any text change).

#### 📚 Examples

Opens a `.pl` file dialog inside `pyagentprolog_ide/examples/`, which
contains several ready-made projects:

```
examples/
├── family/kb.pl
├── factorial/kb.pl
├── lists/kb.pl
├── cut_ite/kb.pl
├── breakpoints/kb.pl
└── semantic/kb.pl
```

Selecting one makes it the **current project** (real project, not a
temporary copy). Copy the folder first if you want to experiment without
touching the bundled examples.

#### 🔌 Context (context)

Populates `agent.context`, which is available to Python actions as
`context['key']`.

| Control | Action |
|---|---|
| Key | `llm`, `db`, `api_key`, … |
| Expression | A Python expression evaluated with `eval` in the global namespace |
| ➕ | Evaluate and store into `context[key]` |
| 🗑️ | Delete `context[key]` |
| 🔄 Apply | Rebuild context (running builders) and recreate the `Agent` |
| 🔄 List | Show `[{key, type, repr}]` |

Example:
```
Key:        llm
Expression: __import__('langchain_openai').ChatOpenAI(model='gpt-4o-mini')
```
→ ➕ → 🔄 Apply.

> ⚠ `eval` runs in the IDE process. Do not use with untrusted input. For
> resources that must be re-created on every reload, register a builder via
> the Python API: `ide.context.add_builder(fn)`.

#### 🧬 Semantic

Enables embedding-based matching (`city(moskva)` ↔ `city(moscow)`).

| Field | Purpose |
|---|---|
| Backend | `st` (sentence-transformers) or `ollama` |
| Model | Name/ID used for prefix detection and HF fallback |
| Local path | Absolute path to a locally stored HF model folder |
| Local only | If the folder is missing — fail, do not download |
| Threshold | Hard cosine threshold (Layer 3) |
| Soft cos min | Lower cosine bound for the soft corridor (Layer 2b) |
| Lev max | Max `lev_ratio` inside the soft corridor |
| Lev typo max | Max `lev_ratio` for typos (Layer 2a) |

| Button | Action |
|---|---|
| ✅ ON | Create `EmbeddingUnifier` with the current parameters |
| ❌ OFF | Disable (uninstall the unifier) |
| 🔧 Thr | Change **only** the threshold on the running unifier (no model reload, cache preserved) |
| 🔄 | Refresh status badge |

A status badge above the controls shows `🟢 ON backend=… threshold=… soft_cos_min=…` or `🔴 OFF` with the last error.

**Local model behaviour:**

| Local path | Local only | Result |
|---|---|---|
| Set, folder exists | any | Load from the folder with `local_files_only=True` |
| Set, folder missing | ☐ | Fallback to HF (`Model`) |
| Set, folder missing | ☑ | Error |
| Empty | ☐ | Standard mode (HF cache or download) |
| Empty | ☑ | Error (`local_files_only=True` without a path) |

**🔬 Compare pair** — a diagnostic tool:

- Inputs `A` / `B` → click 🔬
- JSON output: `cos`, `lev`, `verdict` (`exact` / `typo` / `hard` / `soft` /
  `NONE`), current parameters, and a `hints` array suggesting which slider
  to move.

Example:
```json
{
  "cos": 0.62, "lev": 0.5, "verdict": "NONE",
  "hints": ["cos=0.620 in soft corridor but lev=0.500 > lev_max=0.35 → raise Lev max to 0.55"]
}
```

#### 🔬 Diagnostics

Snapshot of `agent`, `project`, `context`, `semantic`, `numba`, and the
last 10 queries.

### Column 2 — Program

- `gr.Code` editor (Prolog). In Gradio 6 the language is `python`, which is
  visually close enough for Prolog (`%` comments, operators, atoms).
- Buttons under the editor:
  - **🔄 Reload** — `load_program(text)`; recreates the `Agent` from the
    current editor text and re-imports `my_actions.py` if `mtime_ns + size`
    changed.
  - **✓ Syntax** — `Parser(text).parse_rules()` only; the `Agent` is not
    created.
  - **🗑️ Clear** — clears the editor (does not touch the file or project).
- Status line (`pre.status-box`) shows the outcome of the last operation.
- **⚡ Actions** accordion — click the header to expand; the list is fetched
  via `.expand()`, so it always reflects the current `Agent`.
- **📚 KB** accordion — click the header to expand; shows the parsed rules
  and the rule index (see *Knowledge base and index* below).

### Column 3 — Query & debug

#### Query input

Enter a Prolog query **ending with a period**:

```prolog
parent(ivan, X).
```

The `?-` prefix is not used.

#### Timeout

A single numeric field; default `30.0`, allowed `0.5 – 600`.

Semantics differ per button:

| Button | Timeout applies to |
|---|---|
| ▶ Run | Total wall-clock for the whole query |
| ⏩ First | Total wall-clock for the whole query |
| 📡 Stream | **Per-item**: waiting time between two consecutive solutions |
| 🔍 Trace | Total wall-clock for the tracing session |

Empty / invalid input (`""`, `"abc"`, `0`, `-5`) falls back to `30.0` —
no `ValueError`.

> **Timeout does not kill the query.** After the timeout fires, the daemon
> thread continues to run. PyAgentProlog does not support cancellation from
> the outside (no `CancelToken` in the core), so `loop :- loop.` will keep
> one CPU core busy until the IDE process is restarted. Use timeouts as a
> UI-fuse, not as a hard cancel.

#### ▶ ⏩ 📡 ⏹

Compact icon-only buttons, one row under the timeout field.

| Button | Action |
|---|---|
| ▶ | Run — all solutions. Output in **Result** (text) and **Raw** (JSON). |
| ⏩ | First — first solution only. |
| 📡 | Stream — incremental; each new solution is appended to the **Stream** box. |
| ⏹ | Stop — stops UI updates only; the background thread still runs to completion. |

#### Trace & breakpoints

- **Breakpoints** field — comma-separated predicate names:
  `loop, grandparent, ancestor`.
- Buttons (one row):
  - **🔍 Trace** — run the query with tracing and breakpoints.
  - **⏵ Cont** — continue after a pause.
  - **⏭ Step** — one step (continue to the next breakpoint).
  - **⛔ Abort** — cancel tracing.
  - **↺ Reset** — reset the hit counter and pause state.

Behaviour:
1. Query runs; on each `end_goal` of a breakpoint predicate the solver
   thread blocks on `threading.Event`.
2. UI shows `⏸ Paused: loop(...) | Hit: 1`, and `⏵ ⏭ ⛔` become active.
3. `⏵` continues to the next breakpoint; `⏭` resumes with a single step;
   `⛔` raises `AbortException` inside the worker.

Implementation: `BreakpointTracer` subclasses `ProofTracer` and calls
`controller.on_end_goal(step)` after every `end_goal`.

#### Proof tree

Rendered as nested `<ul>/<li>` HTML:

- **green** — succeeded step;
- **red** — failed step;
- **purple** — builtin predicate;
- `⇐ rule` — the rule that was applied;
- `[X=petr]` — head bindings.

#### Steps (Dataframe)

Every step as `id | goal | rule | ok | kind`. **Click a row** to populate
the `subst` table.

#### subst (Dataframe)

`var | before | after`:
- If `ProofTracer` has `subst_before/after` — real before/after;
- Otherwise the fallback uses `unification` (head bindings) as `after`.

To fill full `subst_before/after`, add one line in the core
(`prolog/interpreter.py`) after `trace_step = self.tracer.start_goal(...)`:

```python
self.tracer.set_substitutions(frame.subst, new_subst)
```

---

## Python actions (`my_actions.py`)

`my_actions.py` is a regular Python module next to `kb.pl`. The IDE imports
it automatically on program (re)load; if the file's `mtime_ns + size`
changes, it is re-imported on the next reload.

### Three decorator kinds

**`simple_action` — one result**

```python
from prolog.actions import simple_action

@simple_action('distance', 3, output_arg=2)
def distance(x, y, context):
    tx = context.get('target_x', 10.0)
    ty = context.get('target_y', 5.0)
    return ((x - tx) ** 2 + (y - ty) ** 2) ** 0.5
```

```prolog
near(X, Y) :- distance(X, Y, D), D < 3.0.
```

**`effector_action` — side effect only**

```python
from prolog.actions import effector_action

@effector_action('log_msg', 1)
def log_msg(msg, context):
    print(f"[LOG] {msg}")
```

```prolog
run :- log_msg('start'), do_work, log_msg('done').
```

**`generator_action` — iterator → many solutions**

```python
from prolog.actions import generator_action

@generator_action('count_to', 2, output_arg=1)
def count_to(n, context):
    for i in range(1, n + 1):
        yield i
```

```prolog
?- count_to(3, X).
X = 1 ; X = 2 ; X = 3.
```

### What **not** to do

- Do **not** call `agent.register_action(...)` inside `my_actions.py` — the
  IDE registers your module with `agent.register_action_module(mod)`
  automatically.
- Do **not** import `Agent` or call `sys.path.insert` — the project folder
  is already added to `sys.path`, sibling imports work out of the box.

### Accessing external resources

Use `context['key']`:

```python
@simple_action('ask_llm', 2, output_arg=1)
def ask_llm(prompt, context):
    llm = context.get('llm')
    if llm is None:
        return "(no llm configured)"
    return llm.invoke(prompt).content
```

`context` is the same dict that the IDE populates from the **Context** panel
(see *Column 1 → 🔌 Context*). It is rebuilt via `ContextRegistry.apply()`
every time the `Agent` is recreated.

Exceptions raised inside actions are caught by the decorator wrapper and
converted to a Prolog fail. To raise an explicit error, raise
`PrologError(...)` from `prolog.predicates`.

---

## Semantic unification

### Layers

1. **Layer 1** — normalise (`strip`, drop paired quotes, `lower()`).
2. **Layer 2a** — near-identical strings (`lev_ratio ≤ lev_typo_max`) → match
   without the model.
3. **Layer 3** — hard match: `cos ≥ threshold`.
4. **Layer 2b** — soft corridor: `cos ≥ soft_cos_min` **and**
   `lev_ratio ≤ lev_max`.

### Typical workflow

1. Open the **🧬 Semantic** accordion.
2. Pick backend `st`, set `Model` and, if available, `Local path`.
3. ✅ ON → status badge turns 🟢.
4. Run a query. If it returns `False` but you expect a match, use
   **🔬 Compare pair**.
5. Follow the `hints` in the JSON output — e.g. increase `Lev max` — then
   ✅ ON again.

### Why `moskva` may not match `moscow` by default

```
lev("moskva", "moscow") = 0.5
cos ≈ 0.55–0.70 (mpnet-base)
```

With the defaults `threshold=0.82`, `soft_cos_min=0.55`, `lev_max=0.35`:

- `cos` is in the soft corridor, but `lev = 0.5 > lev_max = 0.35` → **NONE**.

Set `Lev max = 0.55` and press ✅ ON — the pair lands in the **soft** branch.
Cross-script matches like `Москва` ↔ `москва` are usually solved by the
**hard** branch without touching `lev_max`.

### Local HF models

Point **Local path** at a directory containing a full HF model
(`config.json`, `tokenizer.json`, `model.safetensors`, …):

```
D:\hf_embedding\paraphrase-multilingual-mpnet
```

The IDE calls `semantic_on(..., model=local_path, st_local_files_only=True)`,
which makes `sentence-transformers` load the model **without touching the
network**. Prefix detection still uses `Model` (not the path) so `e5-*` /
`nomic-*` prefixes keep working.

---

## Tracing, breakpoints, and the `subst` view

- **Breakpoints** pause the solver whenever a predicate from the list is
  about to `end_goal`. Hitting `⛔ Abort` raises `AbortException` inside the
  solver and unwinds the trace.
- **Proof tree** is rendered as HTML with per-step status colours. `data-step-id`
  is attached to each `<li>` for potential future JS integration.
- **Steps dataframe** lists every flattened step; **clicking a row** loads
  `subst` for that step.
- **subst dataframe** shows `var / before / after`, falling back to the
  `unification` bindings when `subst_before/after` are not populated.

---

## Knowledge base and index

Expand **📚 KB** in column 2.

**Rules** — flat list of parsed rules:

```json
[
  {"index": 0, "head": "parent(ivan, alexey)", "body": "", "rule": "parent(ivan, alexey)."},
  {"index": 1, "head": "grandparent(X, Z)", "body": "parent(X, Y), parent(Y, Z)",
   "rule": "grandparent(X, Z) :- parent(X, Y), parent(Y, Z)."}
]
```

Use it to check how a rule **parsed** (operator precedence, cuts, `->`).

**Index** — the rule index:

```json
{
  "parent/2":    {"rules": 3, "const_keys": ["ivan", "alexey"]},
  "grandparent/2": {"rules": 1, "const_keys": []}
}
```

`const_keys` lists constant first-argument values for which the engine
built a fast bucket. If a hot predicate has empty `const_keys`, consider
moving a constant to the first argument.

---

## Sessions

Every browser tab receives its own `PrologIDE` instance through
`gr.State`; a global LRU registry (`sessions.py`) keeps up to 100 of them.
Tab A and Tab B are fully independent: different projects, contexts,
semantic settings and breakpoints.

---

## Timeouts and cancellation

| Behaviour | Value |
|---|---|
| Default | 30 s |
| Range | 0.5 – 600 s |
| Invalid input | Silently falls back to 30 s |
| Cancels the query? | **No.** The worker is a `daemon` thread; a timed-out query keeps running until it finishes or hits `RecursionError` |

Per button:

- **Run / First / Trace** — total wall-clock timeout;
- **Stream** — per-item timeout between consecutive solutions.

To hard-cancel, patches to `prolog/interpreter.py` and `prolog/agent.py`
would be required (`CancelToken` checked inside the `_solve_iterative`
loop). Not implemented yet.

---

## Dependencies

**Required**

- `pyagentprolog >= 1.0.1`
- `gradio >= 4.0`
- `tkinter` (usually bundled with Python; needed for native dialogs).

**Optional**

- `sentence-transformers` (backend `st`)
- `ollama` (backend `ollama`)
- `numpy`, `numba` — inherited from the core for arithmetic acceleration.

## Package layout

```
pyagentprolog-ide/
├── pyproject.toml
├── README.md
└── pyagentprolog_ide/
    ├── __init__.py
    ├── __main__.py
    ├── _gradio_compat.py
    ├── actions_ctx.py
    ├── app.py
    ├── breakpoints.py
    ├── examples/
    │   ├── family/kb.pl
    │   ├── factorial/kb.pl
    │   ├── lists/kb.pl
    │   ├── cut_ite/kb.pl
    │   ├── breakpoints/kb.pl
    │   └── semantic/kb.pl
    ├── project.py
    ├── sessions.py
    ├── streaming.py
    └── tree_view.py
```

## Known limitations

- **Timeout does not stop the query.** See *Timeouts*.
- **Drag-drop `.pl` does not set the project.** Gradio always copies
  uploads to a temporary directory; use **📂 Open** for real projects.
- **`subst_before/after` are empty by default.** Requires a one-line patch
  in `prolog/interpreter.py` (see *subst* section).
- **`eval` in Context.** Code from the Context panel runs in the IDE
  process; do not use with untrusted input.
- **`my_actions.py` edits require a reload** (either 🔄 Reload or any edit
  to the editor text) — re-import is driven by `mtime_ns + size`.
- **Semantic backends need setup** — `pip install sentence-transformers`
  for `st`, or a running Ollama server for `ollama`. The ✅ ON button
  reports the exact error otherwise.
- **Gradio 6 code language** — `prolog` is not in the supported list; the
  editor falls back to `python`, which highlights operators, atoms,
  variables and `%` comments well enough.

## Development

The IDE only depends on the public API of `pyagentprolog`:

- `prolog.agent.Agent` — program loading, queries, actions, context.
- `prolog.parser.Parser` — syntax check.
- `prolog.tracer.ProofTracer / ProofStep` — tracing.
- `prolog.embedding_unify` — `semantic_on`, `semantic_off`,
  `semantic_status`, `semantic_set_threshold`,
  `semantic_get_unifier`, `detect_text_prefix`, `resolve_model_id`,
  `_normalize_text`, `_lev_ratio`.

No core modifications are required. Adding IDE features should stay inside
`pyagentprolog_ide/`.

## License

MIT