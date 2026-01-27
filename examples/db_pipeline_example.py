"""
Example usage of DbStagedPipeline for DB-based multi-stage processing.

This example demonstrates:
1. Running multiple stages in parallel processes
2. Sharing model initialization across stages (stages 0 & 1 share VLM)
3. Stage-specific DB ingestion before model initialization
4. Each stage managing its own DB fetch/process/update internally

Key pattern:
- ingest_fn: Called BEFORE model init to populate stage DB (parallel across stages)
- init_fn: Loads models/resources (shared across stages with same init_source)
- function: Processes items from current DB, updates next stage DB
- termination_fn: Cleanup resources after stage completes
"""

import os
import time
import socket
import logging
from types import SimpleNamespace
from stageweaver import DbStagedPipeline, DbStageConfig


# ============================================================================
# INGEST FUNCTIONS: Populate stage DBs (called BEFORE model initialization)
# ============================================================================
# Signature: ingest_fn(db_path, image_paths_source, log_dir, batch_size, flag)

def ingest_stage0_db(db_path, image_paths_source, log_dir, batch_size, create_if_not_exists):
    """
    Ingest images into stage 0 DB.
    Called as a separate process BEFORE model initialization.
    
    Args:
        db_path: Path to stage DB
        image_paths_source: Source directory/file for images
        log_dir: Directory for logs
        batch_size: Batch size for ingestion
        create_if_not_exists: Whether to create DB if it doesn't exist
    """
    print(f"\n[INGEST Stage 0] Starting DB ingestion")
    print(f"  DB Path: {db_path}")
    print(f"  Source: {image_paths_source}")
    print(f"  Log Dir: {log_dir}")
    print(f"  Batch Size: {batch_size}")
    
    # Simulate ingestion work
    # In real code:
    # from your_db_module import ingest_images_to_db
    # ingest_images_to_db(
    #     db_path=db_path,
    #     source=image_paths_source,
    #     batch_size=batch_size,
    #     create=create_if_not_exists
    # )
    
    time.sleep(1)  # Simulate work
    print(f"[INGEST Stage 0] Completed. Ready for processing.\n")


def ingest_stage1_db(db_path, image_paths_source, log_dir, batch_size, create_if_not_exists):
    """Initialize stage 1 DB (usually empty, gets populated by stage 0)."""
    print(f"\n[INGEST Stage 1] Initializing DB at {db_path}")
    # In real code: create_empty_db_with_schema(db_path)
    time.sleep(0.3)
    print(f"[INGEST Stage 1] DB initialized.\n")


def ingest_stage2_db(db_path, image_paths_source, log_dir, batch_size, create_if_not_exists):
    """Initialize stage 2 DB."""
    print(f"\n[INGEST Stage 2] Initializing DB at {db_path}")
    time.sleep(0.3)
    print(f"[INGEST Stage 2] DB initialized.\n")


# ============================================================================
# INIT FUNCTIONS: Load models/resources (shared across stages)
# ============================================================================

def vlm_model_init(args, log, config_only=False):
    """
    Initialize VLM model (shared across stages 0 and 1).
    
    Args:
        args: SimpleNamespace with configuration
        log: Logger instance
        config_only: If True, return lightweight config only (for completion checks)
    
    Returns:
        init_vars: Dict with loaded resources
    """
    if config_only:
        return {"config": "lightweight_config"}
    
    try:
        print(f"\n[INIT VLM] Loading VLM model: {args.vlm_model_name}")
        print(f"[INIT VLM] Using GPUs: {args.vlm_gpus}")
        
        # In real code, replace with:
        # from vllm import VLLMConfig, VLLMService
        # cfg_model = VLLMConfig(args.vlm_model_name, args.vlm_config_path)
        # service = VLLMService(
        #     engine_args=cfg_model.engine_args,
        #     batch_size=args.batch_size,
        #     gpus=args.vlm_gpus
        # )
        
        # Simulated model loading
        time.sleep(2)  # Simulate loading time
        vlm_service = {"model": "simulated_vlm_70B", "status": "loaded"}
        
        print(f"[INIT VLM] Model loaded successfully\n")
        
        return {
            "vlm_config": {"model_name": args.vlm_model_name},
            "vlm_service": vlm_service
        }
    except Exception as e:
        if log:
            log.error(f"Failed to initialize VLM: {e}")
        raise


def lightweight_init(args, log, config_only=False):
    """Lightweight initialization for stage 2 (no heavy model)."""
    print(f"\n[INIT Stage 2] Lightweight initialization")
    print(f"[INIT Stage 2] Output dir: {args.output_dir}\n")
    return {"config": "lightweight", "output_dir": args.output_dir}


# ============================================================================
# STAGE WORKER FUNCTIONS: Process items from DB
# ============================================================================

def stage0_worker(args, init_vars):
    """
    Stage 0: Preprocessing with VLM
    Fetches from stage0 DB, processes, updates stage1 DB.
    
    Args:
        args: SimpleNamespace with stage configuration
        init_vars: Dict from vlm_model_init (shared with stage 1)
    """
    print(f"\n{'='*60}")
    print(f"STAGE 0 STARTED (PID: {os.getpid()})")
    print(f"{'='*60}")
    print(f"  DB Path: {args.db_path}")
    print(f"  Next Stage DB: {args.next_stage_db_path}")
    print(f"  VLM Service: {init_vars['vlm_service']['status']}")
    print(f"  Batch Size: {args.batch_size}")
    
    # Simulate DB-based processing loop
    # In real code:
    # from your_db_module import fetch_pending_items, mark_complete, insert_to_next_stage
    # 
    # while True:
    #     items = fetch_pending_items(args.db_path, limit=args.batch_size)
    #     if not items:
    #         break  # No more work
    #     
    #     # Process batch
    #     for item in items:
    #         result = init_vars["vlm_service"].inference(item)
    #         
    #         # Update current stage DB
    #         mark_complete(args.db_path, item.id, status="processed")
    #         
    #         # Forward to next stage DB
    #         insert_to_next_stage(args.next_stage_db_path, item, result, status="pending")
    
    # Simulated work
    for i in range(5):
        print(f"  [Stage 0] Processing batch {i+1}/5...")
        time.sleep(0.5)
    
    print(f"\nSTAGE 0 COMPLETED")
    print(f"{'='*60}\n")


def stage1_worker(args, init_vars):
    """
    Stage 1: Main inference with VLM (shares model with stage 0)
    Fetches from stage1 DB, processes, updates stage2 DB.
    """
    print(f"\n{'='*60}")
    print(f"STAGE 1 STARTED (PID: {os.getpid()})")
    print(f"{'='*60}")
    print(f"  DB Path: {args.db_path}")
    print(f"  Next Stage DB: {args.next_stage_db_path}")
    print(f"  VLM Service: {init_vars['vlm_service']['status']} (SHARED with Stage 0)")
    print(f"  Batch Size: {args.batch_size}")
    
    # Same pattern as stage 0
    for i in range(5):
        print(f"  [Stage 1] Processing batch {i+1}/5...")
        time.sleep(0.5)
    
    print(f"\nSTAGE 1 COMPLETED")
    print(f"{'='*60}\n")


def stage2_worker(args, init_vars):
    """
    Stage 2: Postprocessing (lightweight, no VLM)
    Fetches from stage2 DB, processes, updates final DB.
    """
    print(f"\n{'='*60}")
    print(f"STAGE 2 STARTED (PID: {os.getpid()})")
    print(f"{'='*60}")
    print(f"  DB Path: {args.db_path}")
    print(f"  Output Dir: {init_vars['output_dir']}")
    
    for i in range(3):
        print(f"  [Stage 2] Processing batch {i+1}/3...")
        time.sleep(0.3)
    
    print(f"\nSTAGE 2 COMPLETED")
    print(f"{'='*60}\n")


# ============================================================================
# TERMINATION FUNCTIONS: Cleanup resources
# ============================================================================

def vlm_model_shutdown(init_vars):
    """Cleanup VLM model resources (called once after stages 0 & 1 complete)."""
    print(f"\n[SHUTDOWN VLM] Releasing model resources...")
    # In real code: init_vars["vlm_service"].shutdown()
    time.sleep(1)
    print(f"[SHUTDOWN VLM] Complete\n")


def lightweight_shutdown(init_vars):
    """Lightweight cleanup for stage 2."""
    print(f"\n[SHUTDOWN Stage 2] Cleanup complete\n")


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def setup_logger(log_dir):
    """Setup a basic logger for the pipeline."""
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger("DbPipeline")
    logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(os.path.join(log_dir, "pipeline.log"))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(console_formatter)
    logger.addHandler(file_handler)
    
    return logger


def main():
    """
    Example: Running a 3-stage DB pipeline with shared VLM initialization.
    
    Execution flow:
    1. All ingest functions run in parallel (populate stage DBs)
    2. Stages grouped by initialization_source:
       - Group 0: Stages 0 & 1 (share VLM) → run as threads in process 1
       - Group 2: Stage 2 (lightweight) → runs in process 2
    3. Both groups run in parallel
    4. Each stage polls its DB until no more work
    """
    
    # Setup paths
    run_id = time.strftime("%Y%m%d-%H%M%S")
    node_name = socket.gethostname()
    log_root = "./logs"
    node_run_specific_log_dir = os.path.join(log_root, node_name, run_id)
    
    # Create logger
    logger = setup_logger(node_run_specific_log_dir)
    
    logger.info("="*80)
    logger.info("DB-BASED STAGED PIPELINE EXAMPLE")
    logger.info("="*80)
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Node: {node_name}")
    logger.info(f"Log Dir: {node_run_specific_log_dir}")
    
    # Define stage configurations
    # NOTE: All args must be JSON-serializable (dicts pass through multiprocessing)
    stage_configs = [
        DbStageConfig(
            name="Stage_0_Preprocessing",
            function=stage0_worker,
            args={
                "name": "Stage_0_Preprocessing",
                "db_path": "dbs/stage0.db",
                "next_stage_db_path": "dbs/stage1.db",
                "image_paths_source": "/data/images",  # Used by ingest_fn
                "ingest_batch_size": 100,              # Used by ingest_fn
                "vlm_model_name": "llama-70b",
                "vlm_config_path": "configs/vlm.yaml",
                "vlm_gpus": [0, 1],
                "batch_size": 32,
            },
            ingest_fn=ingest_stage0_db,
            init_fn=vlm_model_init,
            termination_fn=vlm_model_shutdown
        ),
        
        DbStageConfig(
            name="Stage_1_MainInference",
            function=stage1_worker,
            args={
                "name": "Stage_1_MainInference",
                "db_path": "dbs/stage1.db",
                "next_stage_db_path": "dbs/stage2.db",
                "image_paths_source": "",  # Not used (stage1 populated by stage0)
                "ingest_batch_size": 0,
                "vlm_model_name": "llama-70b",  # SAME as stage 0
                "vlm_config_path": "configs/vlm.yaml",
                "vlm_gpus": [0, 1],
                "batch_size": 32,
            },
            ingest_fn=ingest_stage1_db,
            init_fn=vlm_model_init,  # SAME function as stage 0
            termination_fn=vlm_model_shutdown
        ),
        
        DbStageConfig(
            name="Stage_2_Postprocessing",
            function=stage2_worker,
            args={
                "name": "Stage_2_Postprocessing",
                "db_path": "dbs/stage2.db",
                "next_stage_db_path": "dbs/final.db",
                "image_paths_source": "",
                "ingest_batch_size": 0,
                "output_dir": "./outputs",
                "batch_size": 16,
            },
            ingest_fn=ingest_stage2_db,
            init_fn=lightweight_init,
            termination_fn=lightweight_shutdown
        ),
    ]
    
    # Initialization source: stages 0 & 1 share VLM init, stage 2 separate
    initialization_source = [0, 0, 2]
    
    logger.info("\nStage grouping by initialization:")
    logger.info(f"  initialization_source = {initialization_source}")
    logger.info(f"  → Group 0: Stages 0, 1 (shared VLM)")
    logger.info(f"  → Group 2: Stage 2 (lightweight)")
    
    # Create and run pipeline
    pipeline = DbStagedPipeline(
        stage_configs=stage_configs,
        initialization_source=initialization_source,
        logger=logger
    )
    
    try:
        logger.info("\n" + "="*80)
        logger.info("STARTING PIPELINE EXECUTION")
        logger.info("="*80 + "\n")
        
        pipeline.run(node_run_specific_log_dir=node_run_specific_log_dir)
        
        logger.info("\n" + "="*80)
        logger.info("PIPELINE EXECUTION COMPLETE")
        logger.info("="*80)
        
    except KeyboardInterrupt:
        logger.warning("\n\nGraceful shutdown initiated by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
