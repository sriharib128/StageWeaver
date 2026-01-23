"""
StageWeaver - A production-grade parallel pipeline framework for sequential multi-stage data processing

StageWeaver solves the challenge of processing thousands of items through multiple sequential
stages while maintaining maximum throughput, resource efficiency, and resumability.

Key features:
- Hybrid multiprocessing-threading architecture
- Resource sharing across stages (e.g., shared model loading)
- Per-item completion tracking for resumability
- Queue-based backpressure control

Example usage:
    from stageweaver import StagedPipeline, StageConfig
    
    stage_configs = [
        StageConfig(name="stage1", function=process_fn, ...),
        StageConfig(name="stage2", function=another_fn, ...),
    ]
    
    pipeline = StagedPipeline(
        data_folder="./data",
        stage_configs=stage_configs
    )
    pipeline.run()
"""

from .pipeline import StagedPipeline
from .datamodels import StageConfig
from .utils import get_dummy_stage, get_logger

__version__ = "0.1.0"
__all__ = ["StagedPipeline", "StageConfig", "get_dummy_stage", "get_logger"]
