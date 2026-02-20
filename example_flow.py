"""
Give a list of DbStageConfig dataclasses to be run.

### For each DbStageConfig you will need 
    - args -> given as a dict here but when we send it to model we use SimpleNameSpace to makesure this variable acts like a argparse
    - function -> the main function of each stage which run the main loop. The loop:
        1. fetch from state=0 if its the first state=0 or fetch from state=4 if it should be processed only after some upstream stage.
            - given by fetch_state arg in args of that stage
        2. process them
        3. mark in next_state_db as done by changing stage from 0 to 4 in next_stage_db
            - if this is the last stage then simply dont pass the next_stage_db_path in args.
        4. mark done in cur_db
    - init_fn to start and share varibales across stages.
    - termination_fn to run at the end of the stage.

### for each stage that u pass
    - an ingest function is also added.. which takes the image_soruce_text and adds all the paths to a stage_specific_db at db_path in args with default state=0
    - make sure every stage has db_path, ingest_batch_size, fetch_state and if it has some downstream stage then next_stage_db_path
    - if no new images are added to the image_soruce_text, and hence u want to skip the ingest phase, then u can pass `should_ingest=False` to pipeline.run

### initialisation source
    - by default a list of len = len(stages) and value at each index = index itself.
    - if u want some stage to share the model_init(init_vars) of some upstream stage.. then simple make the value at that index = index of that upstream state
    - example --> [0,1,2] --> each stage in its own process with init own init_vars
    - example2 --> [0,0,1] --> stage 1 will share the init_vars of stage 0 only. -> stage0 and stage1 will be run using multithreading in a separate process.

"""
import os
import time
import socket
import logging
from types import SimpleNamespace
import multiprocessing as mp
from stageweaver import DbStagedPipeline, DbStageConfig
from vision_ingest.drivers.db_driver import ingest_images
from vision_ingest.utils.utils import get_logger
from no_img_vlm.stage1 import model_init as vlm_model_init, model_end as vlm_model_shutdown, main_cli as stage1_main_cli
from two_img.stage2 import main_cli as stage2_main_cli
from layout_det.stage3 import models_init as layout_det_init, models_end as layout_det_end, main_cli as layout_det_cli


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
    logger = get_logger(node_run_specific_log_dir, "Entire_pipeline_log")
    
    logger.info("="*80)
    logger.info("DB-BASED STAGED PIPELINE EXAMPLE")
    logger.info("="*80)
    logger.info(f"Run ID: {run_id}")
    logger.info(f"Node: {node_name}")
    logger.info(f"Log Dir: {node_run_specific_log_dir}")
    
    # Define stage configurations
    # NOTE: All args must be JSON-serializable (dicts pass through multiprocessing)
    stage_configs = [
        # --------- Stage 1 --------------
        DbStageConfig(
            name="No image vlm call",
            function=stage1_main_cli,
            args={
                "name": "no image",

                # Database configuration
                "db_path": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/no_img_vlm/db",
                "logs_path": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/no_img_vlm/logs",
                "jsonl_output_path": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/no_img_vlm/jsonl_outputs",

                # Image source configuration
                "image_paths_source": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/images.txt",
                "ingest_batch_size": 32000,  # SQLITE3 can't handle above this

                # Processing configuration
                "batch_size": 4,
                "local_json_threads": 16,
                "fsync_every_lines": 250,

                # VLM configuration
                "vlm_model_name": "qwen_3_235b",
                "vlm_config_path": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/dependencies/Vision-Ingestion-Engine/src/vision_ingest/config/vllm_model.yaml",
                "vlm_gpus": "0,1,2,3,4,5,6,7",
                "prompt_path": "/fsxvision/srihari.bandarupalli/Vision-Ingestion-Engine/prompts/layout_v2.md",

                # Multi-Stage Configuration
                "next_stage_db_path": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/two_img/db",
                "fetch_state": 0 # 0 for the 1st stage in a pipeline and 4 if it has to wait on some other stage whose next_stage_db_path is this db.
            },
            ingest_fn=ingest_images,
            init_fn=vlm_model_init,
            termination_fn=vlm_model_shutdown
        ),

        # --------- Stage 2 --------------
        DbStageConfig(
            name="two images",
            function=stage2_main_cli,
            args={
                "name": "two images",

                # Database configuration
                "db_path": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/two_img/db",
                "logs_path": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/two_img/logs",
                "jsonl_output_path": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/two_img/jsonl_outputs",

                # Image source configuration
                "image_paths_source": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/images.txt",
                "ingest_batch_size": 32000,  # SQLITE3 can't handle above this

                # Processing configuration
                "batch_size": 4,
                "local_json_threads": 16,
                "fsync_every_lines": 250,

                # VLM configuration
                "vlm_model_name": "qwen_3_235b",
                "vlm_config_path": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/dependencies/Vision-Ingestion-Engine/src/vision_ingest/config/vllm_model.yaml",
                "vlm_gpus": "0,1,2,3,4,5,6,7",
                "prompt_path": "/fsxvision/srihari.bandarupalli/Vision-Ingestion-Engine/prompts/layout_v2.md",
                
                # Multi-Stage Configuration
                "next_stage_db_path": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/layout_det/db",
                "fetch_state": 4 # 0 for the 1st stage in a pipeline and 4 if it has to wait on some other stage whose next_stage_db_path is this db.
            },
            ingest_fn=ingest_images,
            init_fn=vlm_model_init,
            termination_fn=vlm_model_shutdown
        ),

        # --------- Stage 3 --------------
        DbStageConfig(
            name = "three layout",
            function=layout_det_cli,
            args={
                "image_paths_source": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/images.txt",
                "ingest_batch_size": 32000,  # SQLITE3 can't handle above this

                "layout_dir" : "outputs/layout_detections",
                "root": "",
                # give the path of root of images and make sure they are such that root_path/doc_id/pages/image_name.png, 
                #  so that outputs are stored at root_path/doc_id/{layout_dir}/image_name.json

                "effective_batch_size" : 256,
                "cfg": "/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/layout_det/config.yaml",
                "db_path" :"/fsxvision/srihari.bandarupalli/Layout-Data-Engine/src/layout_data_engine/layout_det/db",
                "write_threads" : 8,
                "save_visualizations" :True,

                # Multi-Stage Configuration
                "fetch_state" : 4
            },
            ingest_fn=ingest_images,
            init_fn=layout_det_init,
            termination_fn=layout_det_end,
        )
    ]
    

    # Initialization source: stages 0 & 1 share VLM init, stage 2 separate
    initialization_source = [0, 0, 2]
    
    stage_configs=stage_configs[:2]
    initialization_source = initialization_source[:2]
    # Create and run pipeline
    pipeline = DbStagedPipeline(
        stage_configs=stage_configs,
        initialization_source=initialization_source,
        logger=logger
    )
    
    try:
        pipeline.run(node_run_specific_log_dir=node_run_specific_log_dir, should_ingest=False)
    except KeyboardInterrupt:
        logger.warning("\n\nGraceful shutdown initiated by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"Pipeline failed with error: {e}", exc_info=False)
        raise


if __name__ == "__main__":
    os.environ['VLLM_WORKER_MULTIPROC_METHOD'] = 'spawn'
    mp.set_start_method('spawn', force=True)
    main()
