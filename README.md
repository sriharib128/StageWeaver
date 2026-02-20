# StageWeaver — DB Pipeline

**Author:** Srihari Bandarupalli

A parallel pipeline framework for multi-stage data processing using a **database-per-stage** coordination model. Models are loaded once per process group and shared across threads, enabling GPU-efficient multi-stage inference.

> **See [`example_flow.py`](example_flow.py) for a complete working example.**

---

## Installation

```bash
git clone https://github.com/sriharib128/StageWeaver.git
cd StageWeaver
pip install -e .
```

---

## How It Works

### Execution Flow

```
1. Ingest (parallel)           2. Process (parallel groups)
   ┌──────────────────┐           ┌──────────────────────────────┐
   │ ingest ALL stage │           │ Group 0 Process              │
   │ DBs with state=0 │  ──────►  │   Stage 0 thread  (fetch=0)  │
   │ (same image list)│           │   Stage 1 thread  (fetch=4)  │  → share one init_fn
   └──────────────────┘           ├──────────────────────────────┤
                                  │ Group 2 Process              │
                                  │   Stage 2 thread  (fetch=4)  │  → own init_fn
                                  └──────────────────────────────┘
```

1. **Ingest**: `ingest_fn` runs for **every** stage in parallel. Every stage DB is populated with the full input list at `state=0`. The same `ingest_fn` and `image_paths_source` are used across all stages.
2. **Process**: Stages run as threads inside group processes. Each stage polls its own DB for rows matching its `fetch_state`.
3. **Cross-stage handoff**: When a stage finishes an item, it marks the corresponding row in the **next stage's DB** from `state=0` → `state=4`. The downstream stage polls for `state=4` rows, so it waits on upstream naturally.
4. **Termination**: A stage exits when its DB has no more fetchable rows. When all threads in a group finish, `termination_fn` is called once.

### State Machine

```
Ingest populates all DBs:   state=0 (pending)

Stage processing:           state=0 → state=1/2 (in-progress) → state=3 (done)
                                                                      │
                                                          marks row in next_stage_db
                                                          state=0 → state=4
                                                          (unlocks downstream stage)
```

- **`fetch_state=0`** — first stage; fetches items immediately after ingest.
- **`fetch_state=4`** — downstream stage; only fetches rows unlocked by upstream.
- Last stage omits `next_stage_db_path` — no downstream to unlock.

---

## Core Concepts

### `initialization_source`

Controls which stages share a model/process. Stages pointing to the same index share one `init_fn` call and run as threads in the same process.

```python
initialization_source = [0, 0, 2]
#                         ↑  ↑  ↑
#                        S0 S1 S2
# Stage 0 → index 0: own process, init_fn called once → produces init_vars
# Stage 1 → index 0: same process as Stage 0, shares init_vars (no second init_fn call)
# Stage 2 → index 2: own separate process, own init_fn call → own init_vars
```

```
initalization_source = [0, 0, 2]

┌─────────────────────────────────┐     ┌────────────────────────┐
│  Group 0 Process                │     │  Group 2 Process       │
│  (init_source index = 0)        │     │  (init_source index=2) │
│                                 │     │                        │
│  init_fn(args) called ONCE      │     │  init_fn(args) called  │
│  └─► init_vars (e.g. VLM model) │     │  ONCE for this group   │
│         │            │          │     │  └─► init_vars         │
│  ┌──────▼───┐  ┌─────▼────┐    │     │  ┌────────────────┐    │
│  │ Stage 0  │  │ Stage 1  │    │     │  │    Stage 2     │    │
│  │ Thread   │  │ Thread   │    │     │  │    Thread      │    │
│  │fetch_s=0 │  │fetch_s=4 │    │     │  │   fetch_s=4    │    │
│  └──────────┘  └──────────┘    │     │  └────────────────┘    │
│  (shared init_vars — one model) │     │  (own init_vars)       │
└─────────────────────────────────┘     └────────────────────────┘
```

- **`init_fn`** is called **once per group** and returns an `init_vars` dict (e.g. loaded VLM, config paths).
- **`init_vars`** is passed to every thread in that group — threads share the same model object in memory (same GPU allocation).
- **`termination_fn`** is also called **once per group**, after all threads in the group finish.

**Rules**: `initialization_source[i] <= i`, length must equal number of stages.  
Default: `[0, 1, ..., n-1]` (every stage in its own process).

---

## `DbStageConfig`

```python
@dataclass
class DbStageConfig:
    name: str
    function: Callable          # Main processing loop
    args: dict                  # Must be JSON-serializable

    ingest_fn: Optional[Callable] = None       # Populate stage DB (state=0)
    init_fn: Optional[Callable] = None         # Load models/resources
    termination_fn: Optional[Callable] = None  # Release resources
```

### Required `args` keys

| Key | Purpose |
|-----|---------|
| `db_path` | Path to this stage's SQLite DB |
| `image_paths_source` | Input file/dir — used by `ingest_fn` for **all** stages |
| `ingest_batch_size` | Rows per ingest commit (SQLite max ~32000) |
| `fetch_state` | `0` for first stage; `4` for downstream stages |
| `next_stage_db_path` | Next stage's DB to unlock after processing (omit for last stage) |

All keys are passed as `SimpleNamespace(**args)` to `function` and `init_fn`.

---

## Callback Signatures

### `ingest_fn`
```python
def ingest_fn(db_path, image_paths_source, log_dir, batch_size, create_if_not_exists):
    """Populate stage DB with all items at state=0. Runs in its own process.
    Used identically for every stage — coordination is via state transitions, not selective ingestion."""
```

> **Note**: The pipeline extracts `ingest_fn` arguments directly from the stage's `args` dict. Make sure the following keys are present in `args` for every stage:
> - `db_path` — where to create/write the stage DB
> - `image_paths_source` — input file or directory
> - `ingest_batch_size` — rows per commit batch

### `init_fn`
```python
def init_fn(args: SimpleNamespace, log, config_only: bool = False) -> dict:
    """Load models/resources. Called ONCE per group. Returns init_vars shared by all threads."""
```

### `function` (stage worker)
```python
def function(args: SimpleNamespace, init_vars: dict, log_dir: str, shutdown_event: threading.Event) -> None:
    """
    Main loop: fetch by fetch_state → process → mark next_stage_db row state=4 → mark done.
    Return (don't sys.exit) when no more fetchable rows exist or shutdown_event is set.
    """
```

### `termination_fn`
```python
def termination_fn(init_vars: dict) -> None:
    """Release resources. Called once after all threads in the group finish."""
```

---

## Pipeline Setup

```python
from stageweaver import DbStagedPipeline, DbStageConfig

pipeline = DbStagedPipeline(
    stage_configs=stage_configs,
    initialization_source=[0, 0, 2],  # stages 0 & 1 share VLM; stage 2 is separate
    logger=logger,
)

pipeline.run(
    node_run_specific_log_dir="logs/node1/run001",
    should_ingest=True,   # False = skip ingest (DBs already populated)
)
```

See [`example_flow.py`](example_flow.py) for a complete 3-stage pipeline with real args and function references.

---

## Resumability

All state lives in the DB — crash recovery is free:

- Crash mid-batch → rows stay in `processing` state 
    - If the process is killed normally using ctrl+c, a shutdown event is set and threads exit gracefully. In-progress rows will be reset in this case and hence won't be "stuck" in `processing` state.
    - If the process is killed forcefully (e.g., `kill -9`), rows will remain in `processing` state. To recover, simply reset those rows to `state=0` or `state=4` manually.


---

## Multi-Node Execution

Because stages only access their own DB on shared storage, you can split stage subsets across machines:

```python
# Node A — runs stages 0 & 1
pipeline_A = DbStagedPipeline(stage_configs=[s0, s1], initialization_source=[0, 0], ...)
pipeline_A.run(...)

# Node B — stage 2's DB is pre-ingested (state=0); Node A will flip rows to state=4
pipeline_B = DbStagedPipeline(stage_configs=[s2], initialization_source=[0], ...)
pipeline_B.run(...)
```

Node B polls its DB and picks up rows as Node A marks them `state=4`. No API or coordination service needed — just a shared filesystem.

---

## Logging

- Group lifecycle: `{log_dir}/db_group_{init_source}_stages_{indices}.log`
- Stage-specific logs: `{log_dir}/{stage_idx}_{stage_name}/` (passed as `log_dir` to `function`)

---

## Common Pitfalls

| Pitfall | Fix |
|---------|-----|
| Stage exits before upstream finishes | Add a re-poll loop: sleep and retry N times when DB has no fetchable rows |
| `sys.exit` inside `function` | Use `return` — `sys.exit` kills the entire group process, skipping `termination_fn` |
| Non-serializable values in `args` | `args` crosses process boundaries — use paths/primitives only |
| Model loaded separately when sharing is intended | Set `initialization_source` so co-dependent stages share an index |
| Crash leaves rows in `processing` state | Sweep `processing` → `state=0` inside `ingest_fn` on startup |

---

> **File system based variant:** See [README.md](README.md) for `StagedPipeline` — suited for streaming pipelines with less number of files and os read/write calls are extremely fast.
