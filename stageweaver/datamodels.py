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
    termination_fn: Callable


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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for multiprocessing serialization."""
        return {
            'name': self.name,
            'function': self.function,
            'args': self.args,
            'ingest_fn': self.ingest_fn,
            'init_fn': self.init_fn,
            'termination_fn': self.termination_fn
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DbStageConfig':
        """Reconstruct from dictionary after deserialization."""
        return cls(
            name=data['name'],
            function=data['function'],
            args=data['args'],
            ingest_fn=data.get('ingest_fn'),
            init_fn=data.get('init_fn'),
            termination_fn=data.get('termination_fn')
        )
