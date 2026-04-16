# StageWeaver Examples

This directory contains example implementations showing how to use StageWeaver.

## Examples

### gr_ocr_example.py

A complete production example demonstrating a 10-stage OCR pipeline using StageWeaver.

**Features demonstrated:**
- Multiple stage configurations
- Resource sharing between stages (shared VLM models)
- Selective stage execution (run vs check modes)
- Dummy stages for validation-only processing
- Custom initialization sources for model sharing
- Logging configuration

**Usage:**
```bash
python gr_ocr_example.py \
    --root /path/to/images \
    --output_folder ./outputs \
    --log_root ./logs \
    --steps_to_run "0,1,2,3,4,5,7,8,9" \
    --steps_to_check ""
```

### gr_ocr_funcs.py

Helper functions and stage definitions for the OCR example.

**Key utilities:**
- `build_initialization_source()` - Creates initialization mapping for shared resources
- `get_functions()` - Builds complete stage configuration list

## Creating Your Own Pipeline

```python
from stageweaver import StagedPipeline, StageConfig

# 1. Define your stage configurations
stage_config = StageConfig(
    name="My Stage",
    function=my_processing_function,
    args={"param1": "value1"},
    queue_batch_size=32,
    queue_timeout=5.0,
    init_fn=initialize_models,
    completion_fn=check_completion,
    termination_fn=cleanup_resources
)

# 2. Create the pipeline
pipeline = StagedPipeline(
    data_folder="./data",
    stage_configs=[stage_config],
    queue_size=1024
)

# 3. Run it!
pipeline.run(log_dir="./logs")
```

See the main [README](../README.md) for more details.
