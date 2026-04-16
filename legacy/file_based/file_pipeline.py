import json, os 
import multiprocessing as mp
from threading import Thread
from multiprocessing import Queue, Process
from types import SimpleNamespace
from pathlib import Path
from typing import Callable, List, Dict, Any, Optional

from .datamodels import StageConfig
from .model_init import check_and_populate_queues
from .worker import stage_thread_worker
from .utils import get_logger

# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)


class StagedPipeline:
    """
    A multi-stage pipeline that processes data sequentially, with each stage
    running in a parallel process. Stages can share initialization by running
    as threads within the same process.
    """
    def __init__(
        self,
        data_folder: Path,
        stage_configs: List[StageConfig],
        initialization_source: List[int] = None,
        queue_size: int = 1000,
        logger = None
    ):
        """
        Initialize the pipeline.

        Args:
            data_folder: Path to folder containing input data.
            stage_configs: A list of StageConfig objects, one for each stage.
            initialization_source: Array where each index represents which stage's
                                  initialization to use. Default [0,1,2,...,n-1].
                                  Example: [0,1,2,3,3,5] means stage 4 shares init with stage 3.
            queue_size: Maximum size of each inter-stage queue.
        """
        mp.set_start_method('spawn')
        self.data_folder = Path(data_folder)
        self.stage_configs = stage_configs
        self.num_stages = len(stage_configs)
        self.logger = logger
        self.sentinel = "SENTINEL"
        
        # Initialize initialization_source with default values if not provided
        if initialization_source is None:
            self.initialization_source = list(range(self.num_stages))
        else:
            if len(initialization_source) != self.num_stages:
                raise ValueError(f"initialization_source length ({len(initialization_source)}) "
                               f"must match number of stages ({self.num_stages})")
            self.initialization_source = initialization_source
    
        # Unpack stage_configs into separate lists for easier access
        self.functions = [c.function for c in stage_configs]
        self.function_args = [c.args for c in stage_configs]
        self.batch_sizes = [c.queue_batch_size for c in stage_configs]
        self.batch_timeouts = [c.queue_timeout for c in stage_configs]
        self.completion_check_functions = [c.completion_fn for c in stage_configs]
        self.initialization_functions = [c.init_fn for c in stage_configs]
        self.termination_functions = [c.termination_fn for c in stage_configs]

        # Create multiprocessing resources
        self.queues = [Queue(maxsize=queue_size) for _ in range(self.num_stages)]
        self.processes = []

        self._log_stage_configs()

        # Group stages by their initialization source
        self.stage_groups = self._group_stages_by_init_source(self.initialization_source, self.logger)

    def _log_stage_configs(self):
        """Log the stage configurations for debugging."""

        # Log full stage configuration at initialization
        self.logger.info("Logging stage configurations...")
        for idx, cfg in enumerate(self.stage_configs):

            args_str = json.dumps(cfg.args, indent=2, ensure_ascii=False)

            self.logger.info(
                f"[Stage {idx}] {cfg.name}\n"
                f"  • function        : {cfg.function.__name__}\n"
                f"  • args            :\n{args_str}\n"
                f"  • batch_size      : {cfg.queue_batch_size}\n"
                f"  • timeout         : {cfg.queue_timeout}\n"
                f"  • init_fn         : {cfg.init_fn.__name__ if cfg.init_fn else None}\n"
                f"  • completion_fn   : {cfg.completion_fn.__name__ if cfg.completion_fn else None}\n"
                f"  • termination_fn  : {cfg.termination_fn.__name__ if cfg.termination_fn else None}"
            )

    @staticmethod
    def _group_stages_by_init_source(initialization_source: List[int], logger) -> Dict[int, List[int]]:
        """
        Group stage indices by their initialization source.
        Returns: Dict mapping init_source -> list of stage indices that use it
        
        Example: initialization_source = [0,1,2,3,3,5]
        Returns: {0: [0], 1: [1], 2: [2], 3: [3, 4], 5: [5]}
        """
        groups = {}
        for stage_idx, init_source in enumerate(initialization_source):
            if init_source not in groups:
                groups[init_source] = []
            groups[init_source].append(stage_idx)
        
        logger.info(f"Stage grouping by initialization source: {groups}")
        return groups
    
    def run(self, log_dir=None):
        """
        Start all stages and wait for completion.
        """
        self.logger.info("Starting pipeline...")
        self.logger.info(f"Initialization sources: {self.initialization_source}")
        
        # Launch queue population in a separate process (non-blocking)
        self.logger.info("Launching non-blocking queue population for resumability...")
        populate_proc = Process(
            target=check_and_populate_queues,
            args=(
                self.data_folder,
                self.queues,
                self.sentinel,
                self.logger,
            ),
            name="Queue-Populator",
        )
        populate_proc.start()
        
        # Start one process per initialization group
        for init_source, stage_indices in self.stage_groups.items():
            self._start_group_process(init_source, stage_indices, log_dir)
        
        # Wait for all processes to complete
        for proc in self.processes:
            proc.join()
        
        self.logger.info("Pipeline completed!")
    
    def _start_group_process(self, init_source: int, stage_indices: List[int], log_dir: str = None):
        """
        Start a process for a group of stages (can be single or multiple stages).
        Each stage in the group will run as a thread within this process.
        """
        worker_process = Process(
            target=self.group_worker,
            args=(
                init_source,
                stage_indices,
                [self.functions[i] for i in stage_indices],
                [self.function_args[i] for i in stage_indices],
                [self.batch_sizes[i] for i in stage_indices],
                [self.batch_timeouts[i] for i in stage_indices],
                [self.queues[i] for i in stage_indices],
                [self.queues[i + 1] if i + 1 < self.num_stages else None for i in stage_indices],
                self.initialization_functions[init_source],
                self.termination_functions[init_source],
                [self.completion_check_functions[i] for i in stage_indices],
                self.sentinel,
                None,
                log_dir
            ),
            name=f"Group-{init_source}-Stages-{stage_indices}"
        )
        worker_process.start()
        self.processes.append(worker_process)
        
        group_type = "single-stage" if len(stage_indices) == 1 else f"multi-stage ({len(stage_indices)} stages)"
        self.logger.info(f"Started {group_type} process for stages {stage_indices} (init source: {init_source})")
    
    def group_worker(self,
        init_source: int,
        stage_indices: List[int],
        functions: List[Callable],
        func_kwargs_list: List[Dict[str, Any]],
        batch_sizes: List[int],
        timeouts: List[float],
        input_queues: List[Queue],
        output_queues: List[Optional[Queue]],
        init_func: Callable,
        termination_func: Callable,
        completion_funcs: List[Callable],
        sentinel: str,
        logger,
        log_dir: str = None
    ):
        """
        Unified worker process that runs one or more stages as threads, sharing initialization.
        Works for both single-stage groups and multi-stage groups.
        """
        # Set up process-level logging
        logger = get_logger(
            name=f"group_{init_source}",
            log_dir=log_dir,
            log_file=f"group_{init_source}_stages_{stage_indices}.log" if log_dir else None,
            base_logger=logger
        )
        
        logger.info(f"Group process started for stages {stage_indices} (PID: {os.getpid()})")
        
        init_vars = None
        try:
            # Initialize once using the init_source stage's configuration
            args = SimpleNamespace(**func_kwargs_list[0])
            init_vars = init_func(args=args, log=None)
            logger.info(f"Initialization complete for stages {stage_indices} (init source: {init_source})")
            
            # Start a thread for each stage in the group
            threads = []
            for idx, stage_idx in enumerate(stage_indices):
                thread = Thread(
                    target=stage_thread_worker,
                    args=(
                        stage_idx,
                        functions[idx],
                        func_kwargs_list[idx],
                        batch_sizes[idx],
                        timeouts[idx],
                        input_queues[idx],
                        output_queues[idx],
                        completion_funcs[idx],
                        init_vars,  # Shared init_vars across all threads in this group
                        sentinel,
                        logger,
                        log_dir if len(stage_indices) > 1 else None  # Log dir only for multi-stage groups
                    ),
                    name=f"Stage-{stage_idx}-Thread"
                )
                thread.start()
                threads.append(thread)
                logger.info(f"Started thread for stage {stage_idx}")
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            logger.info(f"All threads completed for stages {stage_indices}")
        
        except Exception as e:
            logger.error(f"Fatal error in group process for stages {stage_indices}: {e}", exc_info=True)
        
        finally:
            # Terminate shared resources once for the entire group
            if init_vars:
                try:
                    termination_func(init_vars)
                    logger.info(f"Termination complete for stages {stage_indices}")
                except Exception as e:
                    logger.error(f"Error during termination: {e}", exc_info=True)


    def get_queue_sizes(self) -> Dict[int, int]:
        """Get current size of each queue (useful for monitoring)."""
        return {i: q.qsize() for i, q in enumerate(self.queues)}