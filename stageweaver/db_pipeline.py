import json, os 
import multiprocessing as mp
from threading import Thread
from multiprocessing import Process
from types import SimpleNamespace
from typing import List, Dict, Any

from .datamodels import DbStageConfig
# from .worker import stage_thread_worker
from .utils import get_logger
from .pipeline import StagedPipeline
# import time, socket

class DbStagedPipeline:
    """
    A simplified multi-stage pipeline for DB-based stages.
    
    Key differences from file-based StagedPipeline:
    - No queues: Each stage manages its own DB fetch/process/update
    - No sentinel protocol: Stages poll until no items found
    - Stages can run independently (even on different machines/times)
    - Still supports resource sharing via initialization_source
    """

    def __init__(self, stage_configs: List[DbStageConfig],
                initialization_source: List[int] = None, logger=None):
        
        # Set spawn method only if not already set
        try:
            if mp.get_start_method(allow_none=True) != 'spawn':
                mp.set_start_method('spawn')
        except RuntimeError:
            pass  # Already set, ignore
        self.stage_configs = stage_configs
        self.num_stages = len(stage_configs)
        self.logger=logger
        
        if initialization_source is None:
            self.initialization_source = list(range(self.num_stages))
        else:
            if len(initialization_source) != self.num_stages:
                raise ValueError(f"initialization_source length ({len(initialization_source)}) "
                               f"must match number of stages ({self.num_stages})")
            self.initialization_source = initialization_source
        self._log_stage_configs()

        # Group stages by their initialization source
        self.stage_groups = StagedPipeline._group_stages_by_init_source(self.initialization_source, self.logger)

        self.processes = []
        self._shutdown_requested = False

    def _log_stage_configs(self):
        self.logger.info("Logging stage configurations...")
        for idx, cfg in enumerate(self.stage_configs):

            args_str = json.dumps(cfg.args, ensure_ascii=False)

            self.logger.info(
                f"{'='*60}\n"
                f"[Stage {idx}] {cfg.name}\n"
                f"  • stage_idx       : {idx}\n"
                f"  • init_source     : {self.initialization_source[idx]}\n"
                f"  • function        : {cfg.function.__name__}\n"
                f"  • args            :{args_str}\n"
                f"  • ingest_fn       : {cfg.ingest_fn.__name__ if cfg.ingest_fn else None}\n"
                f"  • init_fn         : {cfg.init_fn.__name__ if cfg.init_fn else None}\n"
                f"  • termination_fn  : {cfg.termination_fn.__name__ if cfg.termination_fn else None}\n"
            )
        
    # def run(self, log_dir="logs"):
    def run (self, node_run_specific_log_dir):
        self.logger.info("Starting DB ingest for each of the stage")
        
        # run_id = time.strftime("%Y%m%d-%H%M%S")
        # node_name = socket.gethostname()

        # node_run_specific_log_dir = os.path.join(log_dir, node_name, run_id)
        # args.logs_path = node_run_specific_log_dir
        db_ingest_processes =[]
        for idx, stage in enumerate(self.stage_configs):
            cur_stage_db_ingest = Process(
                target = stage.ingest_fn,
                args=(
                    stage.args["db_path"],
                    stage.args["image_paths_source"],
                    f"{node_run_specific_log_dir}_{idx}_{stage.args['name']}",
                    stage.args["ingest_batch_size"],
                    True,
                ),
                name = f"{idx}_{stage.name}_ingest_process"
            )
            self.logger.info(
                f"{'='*60}\n"
                f"[Stage {idx}] {stage.name} - Starting DB Ingest Process\n"
            )
            cur_stage_db_ingest.start()
            db_ingest_processes.append(cur_stage_db_ingest)
        
        # wait till ingestion in all the stages is done
        for process in db_ingest_processes:
            process.join()
        self.logger.info(f"{'='*60}")
        self.logger.info("DB Ingest completed for all the stages")
        self.logger.info("Starting DB Staged Pipeline Processing...")
        self.logger.info(f"{'='*60}")
        for init_source, stage_indices in self.stage_groups.items():
            self._start_group_process(init_source, stage_indices, node_run_specific_log_dir)
        
        for proc in self.processes:
            proc.join()
        
        self.logger.info(f"{'='*60}")
        self.logger.info("Entire Pipeline Processed")
        self.logger.info(f"{'='*60}")

    def _start_group_process(self, init_source: int, stage_indices: List[int], log_dir: str = None):
        """
        Start a process for a group of stages (can be single or multiple stages).
        Each stage in the group will run as a thread within this process.
        ADAPTED from pipeline.py
        """
        # Pass stage configs directly without serialization
        stage_configs_subset = [self.stage_configs[i] for i in stage_indices]
        
        worker_process = Process(
            target=DbStagedPipeline.db_group_worker,
            args=(
                init_source,
                stage_indices,
                stage_configs_subset,
                log_dir
            ),
            name=f"DBGroup-{init_source}-Stages-{stage_indices}"
        )
        
        
        group_type = "single-stage" if len(stage_indices) == 1 else f"multi-stage ({len(stage_indices)} stages)"
        self.logger.info(
            f"Starting {group_type} process for stages {stage_indices} "
            f"(init source: {init_source})"
            f"further group specific logs at db_group_{init_source}_stages_{stage_indices}.log"
        )
        worker_process.start()
        self.processes.append(worker_process)

    
    @staticmethod
    def db_group_worker(
        init_source: int,
        stage_indices: List[int],
        stage_configs: List[DbStageConfig],
        log_dir: str = None
    ):
        """
        Worker process that runs one or more DB-based stages as threads, sharing initialization.
        ADAPTED from pipeline.py's group_worker - removed queue handling, simplified for DB stages.
        
        Args:
            init_source: Index of the stage whose initialization to use
            stage_indices: List of stage indices running in this group
            stage_configs: List of DbStageConfig objects
            log_dir: Optional directory for logs
        """
        logger = get_logger(
            name=f"stageweaver_group_{init_source}",
            log_dir=log_dir,
            log_file=f"db_group_{init_source}_stages_{stage_indices}.log" if log_dir else None,
            base_logger=None
        )
        
        logger.info(f"[DBGroupWorker-{init_source}] DB Group process started for stages {stage_indices} (PID: {os.getpid()})")

        init_vars = None

        try:
            # Initialize once using the init_source stage's configuration
            if stage_configs[0].init_fn:
                args = SimpleNamespace(**stage_configs[0].args)
                init_vars = stage_configs[0].init_fn(args=args, log=logger, config_only=False)
                logger.info(f"[DBGroupWorker-{init_source}] Initialization complete for stages {stage_indices} (init source: {init_source})")
            else:
                init_vars = {}  # Empty init_vars if no init function
                logger.info(f"[DBGroupWorker-{init_source}] No init_fn for stages {stage_indices}, using empty init_vars")

            # Start a thread for each stage in the group
            threads = []
            for idx, stage_cfg in enumerate(stage_configs):
                stage_idx = stage_indices[idx]
                thread = Thread(
                    target=DbStagedPipeline._db_stage_thread_worker,
                    args=(
                        stage_idx,
                        stage_cfg,
                        init_vars,  # Shared init_vars across all threads in this group
                        logger
                    ),
                    name=f"DBStage-{stage_idx}-{stage_cfg.name}-Thread"
                )
                logger.info(f"[DBGroupWorker-{init_source}] Starting thread for stage {stage_idx}: {stage_cfg.name}")
                thread.start()
                threads.append(thread)
            
            # Step 4: Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            logger.info(f"[DBGroupWorker-{init_source}] All threads completed for stages {stage_indices}")
        
        except Exception as e:
            logger.error(f"[DBGroupWorker-{init_source}] Fatal error in group process for stages {stage_indices}: {e}", exc_info=True)
        
        finally:
            # Step 5: Terminate shared resources once for the entire group
            if init_vars and stage_configs[0].termination_fn:
                try:
                    stage_configs[0].termination_fn(init_vars)
                    logger.info(f"[DBGroupWorker-{init_source}] Termination complete for stages {stage_indices}")
                except Exception as e:
                    logger.error(f"[DBGroupWorker-{init_source}] Error during termination: {e}", exc_info=True)

    @staticmethod
    def _db_stage_thread_worker(
        stage_idx: int,
        stage_cfg: DbStageConfig,
        init_vars: Dict[str, Any],
        logger
    ):
        """
        Worker thread for a single DB-based stage.
        Simplified from worker.py's stage_thread_worker - no queue handling.
        
        The stage function is responsible for:
        - Fetching items from its DB
        - Processing them
        - Updating state/forwarding to next stage DB
        - Returning when no more items to process
        
        Args:
            stage_idx: Index of this stage
            stage_cfg: DbStageConfig object
            init_vars: Shared initialization variables (models, configs, etc.)
            logger: Logger instance
        """
        logger.info(f"[StageThread-{stage_idx}] Stage {stage_idx} thread started: {stage_cfg.name}")
        
        try:
            # Create args namespace
            args = SimpleNamespace(**stage_cfg.args)
            
            # Call the stage function - it handles all DB logic internally
            stage_cfg.function(args, init_vars)
            
            logger.info(f"[StageThread-{stage_idx}] Stage {stage_idx} completed: {stage_cfg.name}")
            
        except Exception as e:
            logger.error(f"[StageThread-{stage_idx}] Error in stage {stage_idx} ({stage_cfg.name}): {e}", exc_info=True)
            raise
       
    

            


