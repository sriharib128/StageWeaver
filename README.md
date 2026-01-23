# StageWeaver

**Author:** Srihari Bandarupalli

**A production-grade parallel pipeline framework for sequential multi-stage data processing**

StageWeaver solves a deceptively complex problem: how do you process thousands of items through multiple sequential stages while maintaining maximum throughput, resource efficiency, and resumability—without deadlocks, data loss, or redundant model loading?

---

## 📦 Installation

```bash
# install from source
git clone https://github.com/sriharib128/StageWeaver.git
cd StageWeaver
pip install -e .
```

**Requirements:**
- Python 3.8 or higher
- No external dependencies (pure Python stdlib!)

---

## 🚀 Quick Start

```python
from stageweaver import StagedPipeline, StageConfig

# Define your processing stages
stage_configs = [
    StageConfig(
        name="Stage 1: Preprocessing",
        function=preprocess_fn,
        args={"config": "config.yaml"},
        queue_batch_size=32,
        queue_timeout=5.0,
        init_fn=init_models,
        completion_fn=check_if_done,
        termination_fn=cleanup
    ),
    StageConfig(
        name="Stage 2: Processing",
        function=process_fn,
        args={"output_dir": "./results"},
        queue_batch_size=16,
        queue_timeout=5.0,
        init_fn=init_models,
        completion_fn=check_if_done,
        termination_fn=cleanup
    ),
]

# Create and run the pipeline
pipeline = StagedPipeline(
    data_folder="./data",
    stage_configs=stage_configs,
    queue_size=1024
)

pipeline.run(log_dir="./logs")
```

See the [examples/](examples/) directory for complete working examples.

---

## 🎯 The Problem Space

Consider a document OCR pipeline with 10 sequential stages. Traditional approaches fail:

**❌ Sequential Processing** - Process each document completely before the next. GPU idle 90% of the time.

**❌ Parallel Per-Stage** - Process all documents through stage 1, then all through stage 2. Memory explodes from holding all intermediate results. Crash at stage 7? Restart all documents from scratch.

**❌ Thread Pool Per Document** - Spawn threads for each document. 10,000 threads loading the same 70GB model independently causes OOM crashes.

**✅ StageWeaver's Approach** - Pipeline parallelism with intelligent resource sharing:
- Models loaded once per stage group, shared across all documents
- Per-item completion tracking—restart only unfinished items
- Multiprocessing for isolation, threading for resource sharing

---

## 🏗️ Core Architecture

StageWeaver implements a **hybrid multiprocessing-threading pipeline** where:

1. **Stages are organized into groups** based on shared initialization requirements
2. **Each group runs in a separate process** for fault isolation
3. **Stages within a group run as threads** sharing expensive resources (models, GPU memory)
4. **Communication between groups** happens via multiprocessing Queues with sentinel protocol
5. **Each item is tracked individually** for completion, enabling fine-grained resumability

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Pipeline Controller                            │
│  • Groups stages by initialization_source                               │
│  • Spawns one process per group                                         │
│  • Manages inter-group Queues                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
┌───────▼────────┐         ┌────────▼────────┐         ┌───────▼────────┐
│  Group 0 Proc  │         │  Group 1 Proc   │         │  Group 2 Proc  │
│ ┌────────────┐ │         │ ┌─────┐ ┌─────┐ │         │ ┌────────────┐ │
│ │  Stage 0   │ │         │ │Stg2 │ │Stg3 │ │         │ │  Stage 4   │ │
│ │  Thread    │ │         │ │Thrd │ │Thrd │ │         │ │  Thread    │ │
│ └────────────┘ │         │ └─────┘ └─────┘ │         │ └────────────┘ │
│   init_vars₀   │         │   init_vars₁    │         │   init_vars₂   │
│ (VLM Model A)  │         │ (VLM Model B)   │         │ (Light Config) │
└────────────────┘         └─────────────────┘         └────────────────┘
        │                           │                          │
    Queue[0]──────────────►Queue[1]─┴─────────────►Queue[2]────┘
```

**Why this architecture?**

- **Process isolation**: VLM crash in Group 1 doesn't kill Group 0's completed work
- **Thread efficiency**: Stages 2 & 3 share one 70GB VLM instance, not two
- **Queue depth control**: Backpressure prevents stage N from overwhelming stage N+1
- **Sentinel coordination**: Clean shutdown without polling or timeout heuristics

### The Full Lifecycle

Here's what happens end-to-end when you run a pipeline:

```
1. main.py 
   └─> Defines stage_configs (10 StageConfig objects)
   └─> Calls build_initialization_source([0,1,2,7,8,9])
       • Returns [0,1,2,3,4,5,6,7,7,9]  (stages 7,8 share init)

2. StagedPipeline.__init__
   └─> Groups stages: {0:[0], 1:[1], ..., 7:[7,8], 9:[9]}
   └─> Creates Queues[0..9]

3. pipeline.run()
   └─> Process 0: check_and_populate_queues() → fills Queue[0]
   └─> Process 1: group_worker(init_source=0, stages=[0])
       └─> Calls init_fn → init_vars
       └─> Thread: stage_thread_worker(stage=0, init_vars)
           └─> Loop: collect_batch → filter → process → check → forward
   └─> Process 2: group_worker(init_source=7, stages=[7,8])
       └─> Calls init_fn (ONCE) → shared init_vars
       └─> Thread A: stage_thread_worker(stage=7, init_vars)
       └─> Thread B: stage_thread_worker(stage=8, init_vars)
           └─> Both threads share VLM model from init_vars

4. Shutdown
   └─> Sentinel reaches Queue[0]
   └─> Stage 0 forwards to Queue[1] after completion
   └─> Cascades through all queues
   └─> Each group_worker calls termination_fn
   └─> All processes exit cleanly
```

**The elegance**: Configuration flows top-down (stage configs → groups → threads), while data flows stage-to-stage (queues). Separation of control plane and data plane.

---

## ⚡ The Initialization Source Mechanism

The most elegant piece of StageWeaver: **stages declare what they need, not how to share it**.

### The Problem

Stages 8 & 9 both need the same 70GB VLM model. Loading it twice wastes 140GB VRAM and doubles load time.

### The Solution: `initialization_source` Array

Instead of hardcoding "stages 8 and 9 share resources," you declare:

```python
initialization_source = [0, 1, 2, 3, 4, 5, 6, 7, 7, 9]
#                        ↑  ↑  ↑  ↑  ↑  ↑  ↑  ↑  ↑  ↑
#                       S0 S1 S2 S3 S4 S5 S6 S7 S8 S9
```

**Interpretation**: "Stage 8 should use Stage 7's initialization."

The pipeline automatically:
1. Groups stages: `{7: [7, 8], 0: [0], 1: [1], ...}`
2. Runs `init_fn` **once** for index 7, gets `init_vars`
3. Passes same `init_vars` to both Stage 7 and Stage 8 threads
4. Runs `termination_fn` **once** after both threads finish

---

## 🔄 Dual-Mode Initialization: The `config_only` Pattern

Real-world constraint: sometimes you want to **check if work is done without loading the 70GB model**.

### Scenario

You ran stages 0-9 yesterday. Crashed at stage 6. Today you want to:
1. ✅ Skip stages 0-5 (already complete)
2. ⚡ Resume from stage 6

**Naive approach**: Load all 10 models to check completion.
**Problem**: Waiting 10 minutes to discover "nothing to do" is absurd.

### The `config_only=True` Design

Every `init_fn` must support two modes:

| Mode | `init_vars` Contents | Use Case |
|------|---------------------|----------|
| `config_only=False` | Full resources (models, GPU tensors) | **Processing**: Run actual work |
| `config_only=True` | Lightweight config (paths, settings) | **Checking**: Validate completion |

Implementation contract (see [gr_ocr_funcs.py](gr_ocr_funcs.py)):
```python
def models_init(args, log, config_only=False):
    if config_only:
        return {"output_dir": args.output_dir}  # ~1KB
    else:
        model = load_70gb_vllm(args.model_path)
        return {"output_dir": args.output_dir, "model": model}  # ~70GB
```

The `completion_fn` unpacks accordingly:
```python
def check_output_exists(args, item, init_vars, only_config=False):
    # Works with both modes - only needs output_dir path
    return Path(init_vars["output_dir"]) / f"{item.stem}.json").exists()
```

**Key insight**: Completion checking rarely needs the actual model—just the output path convention.

---

## 🛡️ Dummy Stages: Resumability Without Reprocessing

**Problem**: 10,000 documents. Stages 0-5 complete. You want to run only stage 6-9.

**Naive approach**: 
```python
pipeline = StagedPipeline(stages=[stage6, stage7, stage8, stage9])
```
**Failure mode**: Stage 6 receives 10,000 items but has no idea stages 0-5 were already done. It processes blindly.

### The Dummy Stage Pattern

A **dummy stage** is a checker-only stage (see [`get_dummy_stage()`](src/utils.py)):
- `function` → no-op (returns immediately)
- `init_fn` → `config_only=True` mode (lightweight)
- `completion_fn` → **full validation** (checks output exists)
- **Retry buffer enabled**: Failed items re-checked in next batch—this is why retry buffer exists only for `steps_to_check`. Items must keep getting rechecked as another node may process them meanwhile.

Usage:
```python
steps_to_run = [6, 7, 8, 9]     # Heavy processing
steps_to_check = [0, 1, 2, 3, 4, 5]  # Validation only

stages = []
for i in steps_to_check:
    stages.append(get_dummy_stage(stage_configs[i]))  # Lightweight checker
for i in steps_to_run:
    stages.append(stage_configs[i])  # Full processing
```

**Execution flow for item `doc_001.png`**:
1. **Stage 0 (dummy)**: Checks if `output_dir/stage0/doc_001.json` exists
   - ✅ Exists → forward to Queue[1]
   - ❌ Missing → add to retry buffer (maybe another node is processing it)
2. **Stage 6 (real)**: Receives only items that passed all dummy checks
   - Runs actual processing
   - Writes output

### The Distributed Execution Pattern

**The real power of `steps_to_check` + dummy stages + retry buffer**: Multi-node execution without direct communication.

**Scenario**: Process 10,000 documents across 2 nodes
- **Node A**: Runs stages 0-5 (preprocessing)
- **Node B**: Runs stages 6-9 (heavy VLM inference)

**Traditional approach**: 
- ❌ Node B polls Node A's API: "Is doc_001 ready?"
- ❌ Requires network coordination, service discovery, failure handling
- ❌ Tight coupling between nodes

**StageWeaver approach**:
```python
# Node A - runs preprocessing
pipeline_A = StagedPipeline(
    stage_configs=[stage0, stage1, stage2, stage3, stage4, stage5],
    ...
)

# Node B - checks prerequisites via filesystem, runs inference
steps_to_check = [0, 1, 2, 3, 4, 5]  # Dummy stages checking Node A's outputs
steps_to_run = [6, 7, 8, 9]           # Heavy processing on Node B

stages = [
    *[get_dummy_stage(stage_configs[i]) for i in steps_to_check],
    *[stage_configs[i] for i in steps_to_run]
]
pipeline_B = StagedPipeline(stage_configs=stages, ...)
```

**How it works**:
1. Node A writes outputs to shared storage (NFS, S3, etc.)
2. Node B's dummy stages check if files exist via `completion_fn`
3. **Retry buffer is crucial**: If Node A is still writing `doc_001.json`, Node B's check fails → item goes to retry buffer
4. Next batch: Node B re-checks → file now exists → forwards to stage 6
5. **Zero network communication** between nodes

**Why this pattern matters**:
- ✅ **Decoupled execution**: Nodes don't know about each other
- ✅ **Fault tolerance**: Node A crash? Node B keeps checking, processes what's ready
- ✅ **Scalability**: Add Node C for stages 10-12 with same pattern
- ✅ **Shared storage as coordination layer**: Filesystem atomicity handles race conditions

**Key insight**: `config_only=True` means Node B can check Node A's completion status by loading only lightweight config (output paths), not the 70GB models. This makes distributed coordination nearly free.

---

## 🎯 Design Philosophy

**Separation of Concerns**: Each stage provides 4 callbacks (`init_fn`, `function`, `completion_fn`, `termination_fn`). Add new stages without touching pipeline code.

**Explicit Configuration**: `StageConfig` reveals all behavior—resumability, timeouts, resource loading—no hidden magic.

**Fail Loudly, Recover Gracefully**: Exceptions logged with full traceback. Retry buffers for transient failures. Per-item granularity means one failure doesn't block thousands of items.

**Hybrid Concurrency**: Processes for isolation, threads for resource sharing. I/O and GPU-bound work uses threads; CPU-bound uses processes.

**Resumability is Non-Negotiable**: Every stage implements `completion_fn`. Restart after crash? Pipeline auto-skips completed work.

---

## 🔧 Adapting Your Stages to StageWeaver

### Step 1: Refactor Your Processing Logic

**Before** (monolithic function):
```python
def process_documents(input_dir):
    model = load_model()  # ← Problem: loads per call
    for doc in input_dir.glob("*.pdf"):
        result = model.inference(doc)
        save_output(result, doc)
    cleanup_model(model)
```

**After** (StageWeaver-compatible):

Refer to [gr_ocr_funcs.py](gr_ocr_funcs.py) for complete implementation patterns. Your code should follow this structure:

**File: `my_stage.py`**

```python
# 1. Initialization: Load models ONCE
def models_init(args, log=None, config_only=False):
    """
    Args:
        args: SimpleNamespace with stage configuration
        log: Logger instance (None = create new)
        config_only: If True, return lightweight config only
    
    Returns:
        init_vars: Dict passed to function/completion_fn
    """
    if config_only:
        return {"output_dir": args.output_dir}
    
    model = load_model(args.model_path)
    return {"output_dir": args.output_dir, "model": model}


# 2. Batch Processing: Operate on list of items
def process_batch(args, items, init_vars):
    """
    Args:
        args: SimpleNamespace from StageConfig.args
        items: List[Path] - batch of items to process
        init_vars: Dict from models_init
    """
    model = init_vars["model"]
    for item in items:
        result = model.inference(item)
        output_path = Path(init_vars["output_dir"]) / f"{item.stem}.json"
        output_path.write_text(json.dumps(result))


# 3. Completion Check: Is this item already processed?
def check_output_exists(args, item, init_vars, only_config=False):
    """
    Args:
        args: Stage configuration
        item: Path - single item to check
        init_vars: From models_init (config-only or full)
        only_config: If True, init_vars is lightweight
    
    Returns:
        bool: True if item is complete
    """
    output_path = Path(init_vars["output_dir"]) / f"{item.stem}.json"
    return output_path.exists()


# 4. Cleanup: Release resources
def models_end(init_vars):
    """
    Args:
        init_vars: Dict from models_init
    """
    if "model" in init_vars:
        init_vars["model"].unload()
```

**Key changes from monolithic version**:
- ✅ Model loaded **once** in `models_init`, shared across all batches
- ✅ Processing operates on **batches**, not individual items (GPU efficiency)
- ✅ Completion checking **independent** of processing (resumability)
- ✅ Cleanup **guaranteed** in `models_end` (no resource leaks)

---

### Step 2: Create Your StageConfig

**File: `my_pipeline.py`**

```python
from src.datamodels import StageConfig
from my_stage import models_init, process_batch, check_output_exists, models_end

my_stage_config = StageConfig(
    name="Document Analysis",
    
    # Core processing
    function=process_batch,
    args={
        "model_path": "/models/llama-70b",
        "output_dir": "outputs/analysis",
        "batch_size": 32,
    },
    
    # Queue management
    queue_batch_size=64,      # Max items per batch
    queue_timeout=5.0,        # Seconds to wait for full batch
    
    # Lifecycle hooks
    init_fn=models_init,
    completion_fn=check_output_exists,
    termination_fn=models_end,
)
```

**Configuration guide**:

| Parameter | Meaning | Tuning Advice |
|-----------|---------|---------------|
| `queue_batch_size` | Max items per batch | ↑ for GPU efficiency, ↓ for memory limits |
| `queue_timeout` | Batch wait time (sec) | ↑ for bursty workloads, ↓ for low latency |
| `args` | Stage-specific config | Keep JSON-serializable (multiprocessing) |

---

### Step 3: Declare Initialization Dependencies

If your stages share resources:

```python
# Stage 0: Lightweight preprocessing (no model)
# Stage 1: VLM inference - stage 1
# Stage 2: VLM inference - stage 2 (same model as stage 1)
# Stage 3: Postprocessing (different model)

initialization_source = [0, 1, 1, 3]
#                        ↑  ↑  ↑  ↑
#                       S0 S1 S2 S3
#  S2 points to 1 → shares VLM with S1
```

**Rules**:
- ✅ `initialization_source[i] <= i` (can only reference earlier stages)
- ✅ Length must equal number of stages
- ✅ Default: `[0, 1, 2, ..., n-1]` (no sharing)

---

### Step 4: Run Your Pipeline

```python
from src.pipeline import StagedPipeline

pipeline = StagedPipeline(
    data_folder="/data/documents",
    stage_configs=[stage0_cfg, stage1_cfg, stage2_cfg, stage3_cfg],
    initialization_source=[0, 1, 1, 3],
    queue_size=1024,
    logger=my_logger,
)

pipeline.run(log_dir="logs/run_20260102")
```

**What happens**:
1. Pipeline scans `/data/documents/*/pages/` for images
2. Groups stages: `{0: [0], 1: [1, 2], 3: [3]}`
3. Spawns 3 processes (one per group)
4. Group 1's process runs stages 1 & 2 as threads sharing VLM
5. Items flow: `Queue[0] → Queue[1] → Queue[2] → Queue[3]`
6. Sentinel triggers clean shutdown when all items processed

---

### Step 5: Enable Resumability

```python
from stageweaver import get_dummy_stage

# Stages 0-3 already complete, run only 4-6
steps_to_check = [0, 1, 2, 3]  # Validation-only
steps_to_run = [4, 5, 6]       # Full processing

all_stages = [
    *[get_dummy_stage(configs[i]) for i in steps_to_check],
    *[configs[i] for i in steps_to_run],
]

pipeline = StagedPipeline(
    stage_configs=all_stages,
    initialization_source=[0, 1, 1, 3, 4, 5, 5],  # Adjust for combined list
    ...
)
```

**Effect**: Items pass through dummy stages 0-3 (fast completion checks), then heavy processing in stages 4-6. Items failing dummy checks go to retry buffer (maybe in-flight on another worker).

---

## 📚 API Reference

### Core Classes

**`StagedPipeline`** - Main pipeline orchestrator
- `__init__(data_folder, stage_configs, initialization_source, queue_size, logger)`
- `run(log_dir)` - Execute the pipeline

**`StageConfig`** - Stage configuration dataclass
- `name: str` - Stage name
- `function: Callable` - Processing function
- `args: dict` - Arguments for the function
- `queue_batch_size: int` - Batch size for queue reads
- `queue_timeout: float` - Timeout for queue operations
- `init_fn: Callable` - Initialization function
- `completion_fn: Callable` - Completion check function
- `termination_fn: Callable` - Cleanup function

### Utility Functions

**`get_dummy_stage(stage_cfg: StageConfig) -> StageConfig`**
- Creates a validation-only version of a stage (skips processing, only checks completion)

**`get_logger(name, log_dir, log_file, base_logger)`**
- Creates configured loggers for pipeline components

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

##  Module Reference

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| [src/datamodels.py](src/datamodels.py) | Stage contract definition | `StageConfig` dataclass |
| [src/pipeline.py](src/pipeline.py) | Orchestration logic | `StagedPipeline.run()`, `group_worker()` |
| [src/worker.py](src/worker.py) | Per-stage execution | `stage_thread_worker()`, `collect_batch()` |
| [src/utils.py](src/utils.py) | Helpers | `get_dummy_stage()`, `get_logger()` |
| [src/model_init.py](src/model_init.py) | Queue population | `check_and_populate_queues()` |
| [main.py](main.py) | Entry point | CLI parsing, pipeline invocation |
| [gr_ocr_funcs.py](gr_ocr_funcs.py) | Example implementation | 10-stage OCR pipeline |

---

## 🎓 When to Use StageWeaver

✅ **Use**: Multiple sequential stages, shared expensive resources (models), resumability matters  
❌ **Don't use**: Single-stage, real-time latency (<100ms), stages can't pipeline

### Adaptation Checklist

- [ ] Refactor stage logic into 4 callbacks: `init_fn`, `function`, `completion_fn`, `termination_fn`
- [ ] Ensure `function` operates on **batches** (lists), not individual items
- [ ] Implement `config_only=True` mode in `init_fn` for lightweight completion checks
- [ ] Make `completion_fn` **idempotent** (safe to call multiple times)
- [ ] Ensure `args` dict is **JSON-serializable** (multiprocessing requirement)
- [ ] Add comprehensive logging in all 4 callbacks (debugging production issues)
- [ ] Test crash recovery: kill process mid-batch, verify resumability

### Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| **Non-serializable args** | `PicklingError` on startup | Use paths/strings, not objects |
| **Stateful `completion_fn`** | Items re-processed after crash | Check filesystem/DB, not in-memory state |
| **Missing `only_config` check** | Completion check loads 70GB model | Implement dual-mode in `completion_fn` |
| **Exception swallowing** | Silent failures, no logs | Remove try-catch without logging |
| **Unbounded queue growth** | OOM from queue backlog | Reduce `queue_size` in `StagedPipeline` |

---

## 🚀 Conclusion

StageWeaver's design emerged from production pain: 10-stage OCR pipelines crashing at stage 7, losing days of GPU work. The architecture solves this through:

1. **Hybrid concurrency** - Processes for isolation, threads for sharing
2. **Initialization source** - Declarative resource sharing
3. **Dual-mode init** - Fast resumability without model loading
4. **Dummy stages** - Validation-only pipeline segments
5. **Sentinel protocol** - Clean shutdown without polling

The framework's elegance isn't in the algorithms (queue batching, thread pools are standard). It's in the **contracts**: by enforcing 4 simple callbacks, StageWeaver enables arbitrary stage composition without modifying pipeline internals.

**The meta-lesson**: Good abstractions don't hide complexity—they **organize** it. Each stage owns its complexity (model loading, inference, output validation). The pipeline owns orchestration (queuing, threading, shutdown). Neither leaks into the other.

Adapt your stages to this contract, and you get resumability, resource sharing, and pipeline parallelism for free.