# PyAgentProlog IDE — User Guide

## 1. What This Is

An IDE for developing hybrid Prolog programs on PyAgentProlog. It lets you:

- write and check Prolog programs;
- connect Python actions from `my_actions.py`, located next to `kb.pl`;
- give actions access to external resources (LLM, DB, API) via `context`;
- enable semantic unification (comparing atoms by meaning);
- run queries with timeout, streaming, tracing, breakpoints;
- inspect the knowledge base, index, and diagnostics.

Everything runs on top of the `pyagentprolog` package (core) and `gradio` (web UI). The IDE is a separate package, `pyagentprolog-ide`; the core knows nothing about it.

---

## 2. Installation and Launch

### 2.1. Dependencies

```powershell
pip install -e D:\bfx\Repositories\pyagentprolog          # core
pip install -e D:\bfx\Repositories\pyagentprolog-ide      # IDE
```

Optional:

```powershell
pip install sentence-transformers   # for Semantic backend='st'
# ollama — separate service, see https://ollama.com
```

### 2.2. Launch

```powershell
python -m pyagentprolog_ide
# or
pyagentprolog-ide --host 127.0.0.1 --port 7860
```

The browser opens automatically at `http://127.0.0.1:7860`.

### 2.3. CLI Parameters

| Flag | Default | Purpose |
|---|---|---|
| `--host` | `127.0.0.1` | Address (for network access — `0.0.0.0`) |
| `--port` | `7860` | Port |
| `--share` | off | Public link via Gradio |

---

## 3. Interface Overview

Three columns, left to right:

```
┌──────────────┬──────────────────┬─────────────────┐
│ 1. PROJECT   │ 2. PROGRAM       │ 3. QUERY        │
│              │                  │  AND DEBUG      │
│ Path         │ Editor           │ Query           │
│ Open         │ Editor           │ Timeout ▶⏩📡⏹ │
│ Create       │ Editor           │ Result          │
│ Save         │ Editor           │ Stream          │
│ 📚           │ Editor           │ Trace + BP      │
│              │ Editor           │ Tree / steps    │
│ Context      │ Editor           │ subst           │
│ Semantic     │ ⚡ Actions       │                 │
│ Diagnostics  │ 📚 KB            │                 │
└──────────────┴──────────────────┴─────────────────┘
```

Columns scroll independently. Dark theme, all buttons compact (26px / 22px).

---

## 4. Column 1 — Project and Settings

### 4.1. What a "project" is

A **project** is a folder containing:

```
my_prolog_project\
├── kb.pl            ← Prolog program (required)
└── my_actions.py    ← Python actions (optional)
```

Everything you do in the IDE is tied to a single project folder. When you switch projects, `Agent` is recreated, and actions from the old `my_actions.py` are not carried over.

### 4.2. 📄 Drag-drop `.pl` (top)

**What it does:** takes a file, reads its contents, and **puts them into the editor** (column 2). **Does not change the project.**

⚠ **Important:** when uploading a file, Gradio always copies it into a temporary server folder (`/tmp/...`). The real path to the source file is unavailable. So even if you drag in `D:\Projects\X\kb.pl`, the IDE **will not know** that the project is `D:\Projects\X`.

**When to use:** quickly view someone else's `.pl`, compare two versions, copy a fragment.

**When NOT to use:** you want to work with a project — see 4.3/4.4.

### 4.3. 📂 Open

Opens an existing project.

**If the path field is empty** → a native **`.pl` file** picker opens (files are visible alongside subfolders, not just folders). You pick `kb.pl` (or any other `.pl`) → it loads, `project_path` is filled, the status shows:
```
✓ Project: D:\Projects\my_prolog
  kb:            kb.pl
  my_actions.py: present
```

**If the path field is not empty** → no dialog opens; it works with the entered path:
- path to a folder → looks for `kb.pl`, otherwise the first `.pl`;
- path to a `.pl` file → loads exactly that file, folder = parent directory.

**What happens under the hood:** `set_project()` + `load_kb_from_project()` → `Agent(text, context=...)` → `_load_project_actions()` (imports `my_actions.py` if present).

### 4.4. 🆕 Create

Always opens a native **folder** picker/creator.

**What it does:**
1. Creates the folder (if it doesn't exist).
2. Places a `kb.pl` with a template there, if none exists:
   ```prolog
   % New PyAgentProlog project.
   % my_actions.py next to kb.pl will be loaded automatically.
   
   start :-
       write('Hello, PyAgentProlog!'), nl.
   ```
3. Sets the project, loads `kb.pl` into the editor.

**When to use:** you're starting a new program from scratch.

### 4.5. 💾 Save

Saves the editor contents into `kb.pl` of the **current project**.

**Logic:**
- `project_path` field empty → saves to `ide.project_dir` (whatever was opened/created);
- field filled and different from current → `set_project(path)` (switches project) → saves there;
- no project at all → `✗ No project selected`.

**Important:** `Save` does **not** reload `Agent` — it's just a file write. For the new code to take effect in queries, press **🔄 Reload** (column 2), or simply run a query (editing the text automatically triggers `Agent` recreation).

### 4.6. 📚 Examples

Opens a `.pl` picker in `pyagentprolog_ide/examples/`. Inside are project subfolders:

```
examples/
├── family/kb.pl
├── factorial/kb.pl
├── lists/kb.pl
├── cut_ite/kb.pl
├── breakpoints/kb.pl
└── semantic/kb.pl
```

Pick an example → it becomes the current project (a **real** project, not a temporary copy). You can experiment and then `Save` — changes will be written into the example. To avoid damaging the examples, copy them to your own folder and open the copy.

### 4.7. 🔌 Context

Lets you put external resources (LLM client, DB, API keys) into `agent.context`. Inside actions they're accessible via `context['key']`.

**Fields:**
- **Key** — the name, e.g. `llm`, `db`, `api_key`.
- **Python expression** — code evaluated via `eval` in the global namespace; the result goes into `context[key]`.

**Buttons:**
| Button | Action |
|---|---|
| ➕ | Evaluate the expression, put it into `context` |
| 🗑️ | Delete `context[key]` |
| 🔄 Apply | Rebuild `context` (call builders) and reload `Agent` — actions will see the new value |
| 🔄 List | Show `[{key, type, repr}]` |

**Example:**
```
Key:       llm
Expression: __import__('langchain_openai').ChatOpenAI(model='gpt-4o-mini')
```
→ ➕ → 🔄 Apply.

**Note:** `eval` runs in the same process as the IDE. Do not execute code from untrusted sources. If you need builders (a client that can't be reused between reloads) — set them via the Python API (`ide.context.add_builder(fn)`), not through the UI.

### 4.8. 🧬 Semantic

Enables semantic unification — comparing atoms by meaning via embeddings. Useful for fuzzy matching: `city(moskva)` ↔ `city(moscow)`.

**Fields:**

| Field | Purpose |
|---|---|
| Backend | `st` (sentence-transformers) or `ollama` |
| Model | Model name/ID for prefix and fallback loading (e.g. `paraphrase-multilingual-mpnet`, `e5-large`) |
| Local path | Exact path to the HF model folder (e.g. `D:\hf_embedding\paraphrase-multilingual-mpnet`) |
| Local only | If the folder is missing — error instead of loading from HF |
| Threshold | Hard `cos` threshold (Layer 3) |
| Soft cos min | Lower `cos` bound for the soft corridor (Layer 2b) |
| Lev max | Maximum `lev_ratio` for the soft corridor |
| Lev typo max | Upper `lev_ratio` bound for "typos" (Layer 2a) |

**Buttons:**
| Button | Action |
|---|---|
| ✅ ON | Create `EmbeddingUnifier` with the given parameters |
| ❌ OFF | Disable (remove the unifier) |
| 🔧 Thr | Change only `threshold` on the active unifier (without reloading the model) |
| 🔄 | Refresh status |

**Status badge** above the fields: `🟢 ON` / `🔴 OFF` + backend + threshold + soft_cos_min.

**Local model logic:**

| Local path | Local only | What happens |
|---|---|---|
| Filled, folder exists | any | Load **only** from the folder, no network |
| Filled, folder missing | ☐ | Fallback: load from HF by `Model` |
| Filled, folder missing | ☑ | ✗ Error |
| Empty | ☐ | Normal mode (HF cache or download from HF) |
| Empty | ☑ | Error (`local_files_only=True` without a path) |

**🔬 Compare a pair of strings** — built-in diagnostic tool:
- enter `A` = `moskva`, `B` = `moscow` → 🔬;
- you get JSON: `cos`, `lev`, `verdict` (`exact`/`typo`/`hard`/`soft`/`NONE`), current parameters;
- if `verdict = NONE` — the `hints` block tells you exactly which sliders to adjust.

**Typical case:**
```
cos = 0.62, lev = 0.5, threshold = 0.82, soft_cos_min = 0.55, lev_max = 0.35
verdict = NONE
hints = ["cos=0.620 in the soft corridor, but lev=0.500 > lev_max=0.35 → increase Lev max to 0.55"]
```
→ move `Lev max` to 0.55 → ✅ ON → 🔬 → `verdict = soft`.

### 4.9. 🔬 Diagnostics

Shows a summary: number of rules, actions, project info, context, semantic status, Numba status, history of the last 10 queries.

---

## 5. Column 2 — Editor

### 5.1. Code editor

Prolog syntax highlighting (in Gradio 6 — `python` mode, which is nearly equivalent for Prolog: same operators, `%` comments, atoms/variables).

Type the program right here. Changes are not saved automatically — press **💾 Save** in column 1.

### 5.2. Buttons under the editor

| Button | What it does |
|---|---|
| 🔄 Reload | `load_program(text)` — recreates `Agent` **with the current text**, re-imports `my_actions.py` by mtime+size |
| ✓ Syntax | `Parser(text).parse_rules()` — parsing only, **Agent is not created** |
| 🗑️ Clear | Clears the editor (does not touch the file or project) |

**When to use which:**
- you wrote new code → **🔄 Reload** (you need `Agent` with this code);
- you want a quick syntax check before saving → **✓ Syntax**;
- you got lost → **🗑️ Clear** (don't forget to Save).

### 5.3. Editor status

Text block (`pre.status-box`) under the buttons. Shows operation results: `✓ Loaded: N rule(s); actions: M; project: D:\...`, `✗ Error ...`, `Ready. Open a project ...`.

### 5.4. ⚡ Registered Actions (accordion)

**Expands on click of the header**; data is loaded on expand (`.expand`). Shows the list of actions that `Agent` saw in `my_actions.py`:

```json
[
  {"name": "distance", "arity": 3, "description": "...", "type": "simple"},
  {"name": "log_msg", "arity": 1, "description": "...", "type": "effector"}
]
```

If empty — `my_actions.py` either doesn't exist or wasn't imported (check the editor status and the IDE console, there will be `[actions import] ...`).

### 5.5. 📚 Knowledge Base (accordion)

Also expands on click. **Rules** and **Index** (see section 13).

---

## 6. Column 3 — Query and Debug

### 6.1. Query field

Enter a Prolog query **with a period at the end**:

```prolog
parent(ivan, X).
```

No `?-` — the IDE doesn't expect it. The period is mandatory.

### 6.2. Timeout

A single numeric field. Default is 30 seconds, valid range 0.5–600.

**The semantics differ by button:**

| Button | Timeout = |
|---|---|
| ▶ Run | Total wallclock for the **entire** query |
| ⏩ First | Same |
| 📡 Stream | **Timeout for each next solution** (per-item) |
| 🔍 Trace | Total wallclock for the tracing session |

**If the field is empty/invalid** (`""`, `"abc"`, `0`, `-5`) → `30.0` is used. No `ValueError`.

**What "timeout" means:** after N seconds the IDE returns `⏱ Timeout Ns` and **stops waiting**. **The query is not killed** — the daemon thread keeps running in the background. Prolog without explicit cancellation (`CancelToken` in the core) does not support interruption. If you ran an infinite `loop :- loop.` — restart the IDE to free the thread.

### 6.3. Buttons ▶ ⏩ 📡 ⏹

Arranged **in one row under Timeout**, icon-only:

| Button | Action | What it outputs |
|---|---|---|
| ▶ | Run — all solutions | `Result` (text) + `Raw` (JSON) |
| ⏩ | First — first solution | Same |
| 📡 | Stream — one at a time via `agent.stream()` | `Stream` (cumulative) |
| ⏹ | Stop — interrupt streaming | Stops **UI updates**; the background thread runs to completion |

**Result** — human-readable text: `X = petr`, `── 3 solution(s) ──`.
**Raw (JSON)** — raw `Solver.find_solutions` response: `{"query": ..., "solution": [...], "output": ..., "count": ...}`.

### 6.4. Stream (cumulative)

Each new solution is appended as a JSON line. Useful for large results and for watching progress.

### 6.5. Tracing and breakpoints

**Breakpoints field** — comma-separated list of predicates:
```
loop, grandparent, ancestor
```

**Buttons in one row under the field:**

| Button | Action |
|---|---|
| 🔍 Trace | Run the query with tracing and breakpoints |
| ⏵ Cont | Continue after a pause |
| ⏭ Step | One step (continue to the next breakpoint) |
| ⛔ Abort | Abort tracing |
| ↺ Reset | Reset hit counter and pause |

**How it works:**
1. In breakpoints you write `loop`.
2. 🔍 Trace → execution begins.
3. On the first call to `loop` — **pause**, status `⏸ Pause: loop(...) | Hit: 1`, buttons `⏵ ⏭ ⛔` become active.
4. ⏵ Cont → continue to the next `loop`.
5. ⏭ Step → one step.
6. ⛔ Abort → abort.

**Technically:** `BreakpointTracer` overrides `ProofTracer.end_goal` and blocks the solver thread on a `threading.Event`. The UI wakes it via `controller.resume(action)`.

### 6.6. Proof tree (HTML)

After Trace — a visual tree with nested `<ul>/<li>`:

- **Green** — successful step.
- **Red** — failure.
- **Purple** — builtin (built-in predicate).
- `⇐ rule` — which rule was applied.
- `[X=petr]` — head unifications.

### 6.7. Steps (Dataframe)

A table of all steps: `id | goal | rule | ok | kind`. **Click a row** → `subst` shows `subst_before/subst_after` for that step.

### 6.8. subst (Dataframe)

`var | before | after`:
- if `ProofTracer` filled `subst_before/after` — shows the real before/after;
- otherwise falls back to `unification` (rule head bindings) — "after", "before" empty.

Full `before/after` are enabled by a patch in the core (`interpreter.py`): after `trace_step = self.tracer.start_goal(...)` add `self.tracer.set_substitutions(frame.subst, new_subst)`.

---

## 7. Project Structure

### 7.1. Minimum

```
D:\Projects\hello\
└── kb.pl
```

`kb.pl`:
```prolog
start :-
    write('Hello, PyAgentProlog!'), nl.
```

Open the folder → ▶ Run with query `start.` → in Result `Hello, PyAgentProlog!` + `── 1 solution(s) ──`.

### 7.2. With actions

```
D:\Projects\full\
├── kb.pl
└── my_actions.py
```

`my_actions.py` (see section 9):
```python
from prolog.actions import simple_action, effector_action

@simple_action('double', 2, output_arg=1)
def double(x, context):
    return x * 2

@effector_action('log_msg', 1)
def log_msg(msg, context):
    print(f"[LOG] {msg}")
```

`kb.pl`:
```prolog
run :-
    double(21, X),
    log_msg(X).
```

Query `run.` → in the IDE console `[LOG] 42`, in Result `── 1 solution(s) ──` (success without variables).

### 7.3. With an LLM

```
D:\Projects\llm_demo\
├── kb.pl
└── my_actions.py
```

`my_actions.py`:
```python
from prolog.actions import simple_action

@simple_action('ask_llm', 2, output_arg=1)
def ask_llm(prompt, context):
    llm = context.get('llm')
    if llm is None:
        return "(no llm)"
    return llm.invoke(prompt).content
```

`kb.pl`:
```prolog
ask(P, R) :- ask_llm(P, R).
```

In column 1 → 🔌 Context:
- Key: `llm`
- Expression: `__import__('langchain_openai').ChatOpenAI(model='gpt-4o-mini')`
- ➕ → 🔄 Apply.

Query: `ask('Capital of France?', R).` → in Result `R = 'Paris'` (or similar).

---

## 8. Developing Prolog Programs

### 8.1. Work cycle

1. **Write** a rule/fact in the editor.
2. **✓ Syntax** — quick parse check.
3. **🔄 Reload** — recreate `Agent` (check that all rules loaded: `✓ Loaded: N rule(s); ...`).
4. **▶ Run** with a query.
5. If something's off → **🔍 Trace** with breakpoints on suspicious predicates.
6. Refine → **💾 Save**.

### 8.2. What's supported (briefly)

**Control:** `,` `;` `->` `!` `\+` `repeat` `fail` `true`.

**Arithmetic:** `is`, `>`, `<`, `>=`, `=<`, `=:=`, `=\=`, `+`, `-`, `*`, `/`, `mod`, `div`, `abs`, `sqrt`, `sin`, `cos`, `max`, `min`, `**`, etc.

**Lists:** `member/2`, `append/3`, `length/2`, `memberchk/2`.

**Meta:** `call/1..5`, `once/1`, `ignore/1`, `forall/2`, `findall/3`, `bagof/3`, `setof/3`.

**DB:** `asserta/1`, `assertz/1`, `retract/1`, `retractall/1`, `abolish/1`, `clause/2`, `current_predicate/1`.

**Terms:** `functor/3`, `arg/3`, `=../2`, `copy_term/2`, `term_variables/2`, `numbervars/3`.

**Types:** `var/1`, `nonvar/1`, `atom/1`, `integer/1`, `float/1`, `number/1`, `atomic/1`, `compound/1`, `ground/1`, `callable/1`.

**Comparison:** `==/2`, `\==/2`, `\=/2`, `@</2`, `@>/2`, `@=</2`, `@>=/2`, `compare/3`.

**Strings:** `string_concat/3`, `atomic_list_concat/2,3`, `atom_string/2`, `term_string/2`, `number_string/2`, `split_string/4`, `sub_string/5`.

**Semantic control:** `semantic_on/0,1`, `semantic_off/0`, `semantic_threshold/1`, `semantic_status/1`.

**Not available:** modules, DCG, `catch/3`/`throw/1`, `between/3`, `sort/2`, `atom_length/2`, CLP(FD). See section 15 of the package guide.

### 8.3. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `✗ Error ...` on 🔄 | Syntax error | ✓ Syntax will show the location |
| Query returns `False` with correct code | Didn't press 🔄 after edits; or query without `.` | 🔄 + add period |
| `✗ query parse error` | Query doesn't parse | Check parentheses, period at the end |
| Rule not found | Period/comma in the head; typo in the name | Look in `📚 KB` — is the rule there? |
| `assertz` doesn't work | `assertz` is built-in but requires a **ground** term | Check that all variables are bound |
| Infinite loop | `loop :- loop.` | Timeout + restart IDE (thread is not killed) |
| `AssertionError` on 🔄 | Internal error | Check `editor_status` + IDE console |

### 8.4. Techniques

**Debugging via write:**
```prolog
debug(X) :- write('X = '), write(X), nl.
```

**Cut for determinism:**
```prolog
max(X, Y, X) :- X >= Y, !.
max(_, Y, Y).
```

**If-then-else:**
```prolog
classify(X, S) :- X > 0 -> S = positive ; S = non_positive.
```

**Collection via findall:**
```prolog
all_children(P, L) :- findall(C, parent(P, C), L).
```

**Tail recursion (TCO):**
```prolog
my_length(L, N) :- my_length_acc(L, 0, N).
my_length_acc([], Acc, Acc).
my_length_acc([_|T], Acc, N) :- A1 is Acc + 1, my_length_acc(T, A1, N).
```

---

## 9. Python Actions (`my_actions.py`)

### 9.1. What it is

`my_actions.py` is a regular Python module next to `kb.pl`. The IDE imports it automatically **when loading/reloading the program**, if the file exists. When the file changes (by `mtime_ns` + `size`) → re-import on the next 🔄.

### 9.2. Three kinds of decorators

#### simple_action — function → one solution

```python
from prolog.actions import simple_action

@simple_action('distance', 3, output_arg=2)
def distance(x, y, context):
    tx = context.get('target_x', 10.0)
    ty = context.get('target_y', 5.0)
    return ((x - tx) ** 2 + (y - ty) ** 2) ** 0.5
```

- `name='distance'`, `arity=3`: predicate `distance/3`.
- `output_arg=2`: the third Prolog argument is the output (0-based: 0, 1, 2).
- Python receives `x, y` (inputs) + `context` (not from Prolog, but from `database.context`).
- The function **returns** a value → unified with `output_arg`.

In Prolog:
```prolog
near(X, Y) :- distance(X, Y, D), D < 3.0.
```

#### effector_action — side effect, no return

```python
from prolog.actions import effector_action

@effector_action('log_msg', 1)
def log_msg(msg, context):
    print(f"[LOG] {msg}")
    # can write to a file, call an API, mutate context
```

All arguments are inputs and must be ground before the call.

```prolog
run :- log_msg('start'), do_work, log_msg('done').
```

#### generator_action — iterator → multiple solutions

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

### 9.3. What **not** to do

❌ **Do not** call `agent.register_action(...)` inside `my_actions.py`. The IDE does this itself via `agent.register_action_module(mod)`.

❌ **Do not** import `agent` from `prolog` or create `Agent()`.

❌ **Do not** use `sys.path.insert` to load from your project — the IDE has already added the project folder to `sys.path` (`register_project_dir`). Import neighboring modules freely:
```python
# my_actions.py
from my_helpers import compute  # located in the same project folder
```

### 9.4. Good practice

1. **Only decorators + functions**, no module-level side effects.
2. **`context`** is the only way to reach external resources.
3. **Exceptions inside actions** are caught in the `wrapper` and turn into `fail`. If you want an explicit error — `raise PrologError(...)`.
4. **Don't block** for long — the query timeout doesn't kill the thread.

### 9.5. About `context`

```python
@simple_action('ask_llm', 2, output_arg=1)
def ask_llm(prompt, context):
    llm = context.get('llm')
    if llm is None:
        return "(no llm configured)"
    return llm.invoke(prompt).content
```

`context` is a `dict` filled via column 1 → 🔌 Context. The IDE keeps `ContextRegistry.values` (static) + `builders` (rebuild functions) and on `Agent` recreation calls `context.apply()` → passes it to `Agent(text, context=ctx)` → `Solver → Database → database.context`.

---

## 10. Tracing and Breakpoints (Practice)

**Scenario:** the `ancestor` rule fails to find `ancestor(ivan, sergey)`.

1. **Program:**
   ```prolog
   parent(ivan, alexey).
   parent(ivan, maria).
   parent(alexey, petr).
   parent(maria, sergey).
   ancestor(X, Y) :- parent(X, Y).
   ancestor(X, Y) :- parent(X, Z), ancestor(Z, Y).
   ```

2. **Query:** `ancestor(ivan, sergey).`

3. **Trace with breakpoints** `ancestor, parent`.

4. The IDE shows:
   - `⏸ Pause: ancestor(ivan, sergey) | Hit: 1`
   - `⏵ Cont` → pause at the next `ancestor` → `⏵ Cont` → ...
   - At some point a pause at `parent(maria, sergey)` → you can see that the `parent/2` rule matches.

5. After completion — HTML tree: green `ancestor(ivan, sergey)`, nested nodes. The red branch `parent(ivan, petr)` (fail) shows that branch didn't work.

6. **"Steps" Dataframe**: click the row `ancestor(ivan, sergey)` → `subst` shows `X=ivan, Y=sergey` (or head bindings).

7. **If a rule didn't fire** — `📚 KB` → you can see the rule parsed differently (e.g. `a ; b, c` → `a ; (b, c)` — not what you expected).

---

## 11. Semantic Unification — Practice

### 11.1. Enabling

1. 🧬 Semantic → backend `st`.
2. Model: `paraphrase-multilingual-mpnet`.
3. Local path: `D:\hf_embedding\paraphrase-multilingual-mpnet` (if the model is already stored locally).
4. ✅ ON.

Badge: `🟢 ON backend=st threshold=0.82 soft_cos_min=0.55 (builtin)`.

### 11.2. Check

```prolog
city(moscow).
city(paris).
city(london).
```

Query `city(moskva).` → if `False`, open 🔬 Compare a pair of strings: `moskva` vs `moscow` → 🔬.

You'll see:
```json
{
  "cos": 0.62,
  "lev": 0.5,
  "verdict": "NONE",
  "hints": ["cos=0.620 in the soft corridor, but lev=0.500 > lev_max=0.35 → increase Lev max to 0.55"]
}
```

→ `Lev max` to 0.55 → ✅ ON → 🔬 → `verdict: soft`. Query `city(moskva).` → `True`.

### 11.3. Cyrillic is easier

```prolog
city(Москва).
```

Query `city(москва).` — the `mpnet` model will give `cos > 0.9`, it fires by `hard` even with `lev_max=0.35`. For `moskva` (Latin) — you need to adjust `Lev max`.

### 11.4. Don't forget

- `text_prefix` is determined by the **model name**. If you have E5 — the prefix `query: ` is added automatically. With a local path, specify `Model` with a name like `e5-large`, and `Local path` — the path to the folder.
- The embedding cache (`max_cache=10000`) persists between queries. 🔧 Thr changes the threshold without clearing the cache; ✅ ON creates a new unifier — the cache is lost.

---

## 12. Disabling semantic

❌ OFF → `semantic_off()` → `Agent` uses strict matching. If it's enabled — ❌ OFF before strict tests.

---

## 13. Knowledge Base and Index

Expand **📚 Knowledge Base** (column 2).

### 13.1. Rules

A list of all `agent.solver.database.rules` entries:

```json
[
  {"index": 0, "head": "parent(ivan, alexey)", "body": "", "rule": "parent(ivan, alexey)."},
  {"index": 1, "head": "grandparent(X, Z)", "body": "parent(X, Y), parent(Y, Z)", "rule": "grandparent(X, Z) :- parent(X, Y), parent(Y, Z)."}
]
```

**What to look at:**
- how the rule **parsed** (parentheses, priorities);
- rule order;
- facts (`body == ""`) vs rules.

### 13.2. Index

```json
{
  "parent/2":    {"rules": 3, "const_keys": ["ivan", "alexey"]},
  "grandparent/2": {"rules": 1, "const_keys": []}
}
```

`const_keys` — the values of the **first argument** for which fast buckets exist. If you have `parent(ivan, X)`, the engine first looks in `const['ivan']` (2 rules) instead of `all` (3). On large KBs the difference is significant.

**What to look at:**
- whether "hot" predicates have `const_keys`;
- if not, but queries with a constant first argument are frequent — consider rewriting the predicate (move the constant into the first argument).

---

## 14. Diagnostics

🔬 Diagnostics → 🔄 Refresh:

```json
{
  "agent": {"rules": 5, "actions": 2},
  "project": {"project_dir": "...", "kb": "...", "my_actions": "...", "actions_loaded": true, "sys_path_has_project": true},
  "context": [{"key": "llm", "type": "ChatOpenAI", "repr": "..."}],
  "semantic": {"enabled": true, "backend": "st", "threshold": 0.82, "soft_cos_min": 0.55},
  "numba": {"available": true, "active": true, "platform": "x86_64", ...},
  "history": [{"q": "parent(ivan, X).", "ok": true}, ...]
}
```

Useful when troubleshooting:
- `actions_loaded: false` → `my_actions.py` wasn't imported;
- `sys_path_has_project: false` → the IDE didn't add the project folder to `sys.path` (a bug in `register_project_dir`, shouldn't happen);
- `numba.active: false` → JIT disabled after an error; restart the IDE;
- `history` → last queries for reproduction.

---

## 15. Recipes

### 15.1. "Hello, World!" project

1. 🆕 → pick folder `D:\Projects\hello`.
2. A `kb.pl` is created automatically with `start :- write('Hello, PyAgentProlog!'), nl.`.
3. In column 3, query: `start.` → ▶ Run → `Hello, PyAgentProlog!`.

### 15.2. Switching between projects

1. 📂 with `project_path` = `D:\Projects\A` → A is loaded.
2. 📂 with `project_path` = `D:\Projects\B` → `unregister_project_dir(A)` + `register_project_dir(B)`, `Agent` recreated, `my_actions.py` from A is forgotten.
3. `📚 KB` — shows the rules of B.

### 15.3. Experimental edit without Save

1. Opened A.
2. Edited the code in the editor.
3. 🔄 Reload → `Agent` works with the **new** code, the file on disk is **unchanged**.
4. Didn't like it → Ctrl+Z in the editor → 🔄 again → old behavior (file untouched).
5. Liked it → 💾 Save.

### 15.4. Debug with semantic

1. ✅ ON semantic.
2. Query `city(moskva).` → `False`.
3. 🔬 compare `moskva` vs `moscow` → JSON + hints.
4. Follow the hints (`Lev max = 0.55`) → ✅ ON → 🔬 → `soft`.
5. `city(moskva).` → `True`.

### 15.5. LLM in context

1. `pip install langchain-openai`.
2. 🔌 Context: `llm` = `__import__('langchain_openai').ChatOpenAI(model='gpt-4o-mini')`.
3. ➕ → 🔄 Apply.
4. `my_actions.py`:
   ```python
   from prolog.actions import simple_action
   
   @simple_action('ask_llm', 2, output_arg=1)
   def ask_llm(prompt, context):
       return context['llm'].invoke(prompt).content
   ```
5. 🔄 Reload.
6. `ask_llm('Capital of France?', R).` → `R = 'Paris'` (or similar).

---

## 16. Known Limitations

### 16.1. Timeout doesn't kill the query

The daemon thread keeps running. Don't run `loop :- loop.` many times. True cancellation requires a core patch (`CancelToken` in `interpreter._solve_iterative`).

### 16.2. Drag-drop doesn't set the project

Gradio copies the file into a temporary folder. To work with a project — 📂 / 🆕.

### 16.3. `subst_before/after` are empty by default

`ProofTracer` doesn't fill them without a patch to `interpreter.py`. Fallback is `unification` (head bindings), which is usually enough.

### 16.4. Semantic requires installation

- `st` → `pip install sentence-transformers` + download/local model.
- `ollama` → server at `http://localhost:11434`.

Without this, ✅ ON returns `✗` with a hint.

### 16.5. Changes to `my_actions.py` require re-import

Automatic re-import only happens on `Agent` reload (🔄 or when the text changes). If you edited `my_actions.py` and want to test without reloading the program — 🔄 Reload (the editor text is the same, but `Agent` is recreated, `my_actions` re-imported).

### 16.6. `eval` in context

Runs in the IDE process. Don't use for untrusted data.

---

## 17. Hot Tips

1. **Always** keep `📚 KB` at hand — a quick sanity check of parsing.
2. **Breakpoints** — the best debugging tool; set 2–3 key predicates.
3. **🔬 compare** — don't guess why semantic didn't fire: the tool directly tells you which slider to adjust.
4. **Timeout 30s** — a reasonable default; for interactive experiments, use 5–10s.
5. **Stream** — the only way to see progress of a long query; Run/First just wait for the end.
6. **`my_actions.py`** — only decorators and functions, no registration.
7. **`context`** — the only channel to LLM/DB/API; don't try to import them directly inside `my_actions.py` if you need to reload without leaking the old client.

---

## Summary

- **Column 1** — pick a project, configure external resources, enable semantic, check diagnostics.
- **Column 2** — write Prolog, check syntax, view actions and KB.
- **Column 3** — execute a query (Run / First / Stream), debug (Trace + breakpoints + tree + subst).
- **`my_actions.py`** — Python actions, auto-loaded from the project folder.
- **`context`** — LLM, DB, API, keys.
- **Semantic** — fuzzy atom matching; `🔬 compare` — threshold diagnostics.

Everything else derives from these six concepts. Start with the `family` example (📚), then add `my_actions.py`, then `context`, then semantic — and you'll have covered the entire IDE.