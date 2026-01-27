from dataclasses import dataclass
from typing import Callable, Dict, Optional, Any
from pathlib import Path

@dataclass
class StageConfig:
    name: str
    function: Callable
    args: dict
    queue_batch_size: int
    queue_timeout: float
    init_fn: Callable
    completion_fn: Callable[[Dict, Path], bool]
    termination_fn: Callable[[Dict], None]


@dataclass
class DbStageConfig:
    """
    Configuration for a DB-based stage that manages its own state.
    Each stage handles DB fetch/process/update internally.
    """
    name: str
    function: Callable  # Function signature: function(args, init_vars) - handles DB internally
    args: dict  # Must be JSON-serializable for multiprocessing
    
    # Lifecycle hooks
    ingest_fn: Optional[Callable] = None  # Called before init_fn to initialize stage DB
    init_fn: Optional[Callable] = None    # Loads models/resources (supports config_only mode)
    termination_fn: Optional[Callable] = None  # Cleanup resources