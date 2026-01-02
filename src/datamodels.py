from dataclasses import dataclass
from typing import Callable, Dict
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
    termination_fn: Callable[[Dict]]