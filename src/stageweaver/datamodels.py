from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Any
from pathlib import Path

@dataclass
class StageConfig:
    """
    Configuration for a DB-based stage that manages its own state.
    Each stage handles DB fetch/process/update internally.
    """
    name: str

    upstream_stages: List[str]
    fan_in_policy : str # wait for "all" | "any"

    routing_fn: Callable # function which takes in llm output and then decides 
                          # which all downstream stages should be marked as 1

    function: Callable  # Function signature: function(args, init_vars) - handles DB internally
    args: dict  # Must be JSON-serializable for multiprocessing
    
    # Lifecycle hooks
    init_fn: Optional[Callable] = None    # Loads models/resources (supports config_only mode)
    termination_fn: Optional[Callable] = None  # Cleanup resources
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for multiprocessing serialization."""
        pass
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StageConfig':
        """Reconstruct from dictionary after deserialization."""
        pass

@dataclass
class Node:
    name: str
    node_type: str # 'root' | 'middle' | 'leaf'

    # all bit masks are of length = no of stages. (LSB is stage 0).

    # ---- required for middle and leaf nodes ----
    required_mask:  int # with 1 at all the upstream stages.
    wait_for: str # 'any' | 'all' of the upstream stages.
     
"""
# Example row in Database
    image path
    done_mask: int # with 1 at all stages that are done.

    # below two items will keep changing as a datapoint passes through the DAG/stages
    # ---- used with appropriately for both fan-in and delete nodes ----
    marked_for_processing_mask: int # with 1 at all stages that are ready to be processed
                                    # or corresponding state in stage specific db is marked as 4.
    
"""
