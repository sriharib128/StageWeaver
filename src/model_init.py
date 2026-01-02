from multiprocessing import Queue
from pathlib import Path
from typing import Callable, List #, Any, Optional, Callable, Dict
# import time
# from types import SimpleNamespace

def pages_iter(root: Path):
    """
    Return full paths of all the images in the root folder.
    """
    IMG_EXT = ("*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tif", "*.tiff", "*.webp")
    for pages_dir in root.rglob("pages"):
        if not pages_dir.is_dir():
            continue
        for ext in IMG_EXT:
            yield from pages_dir.glob(ext)

def check_and_populate_queues(
    data_folder: Path,
    queues: List[Queue],
    sentinel: str,
    logger
):
    """
    Simplified version: add all items to queue[0] only.
    """
    logger.info("Checking resumability status and populating queue 0...")

    try:
        image_paths = list(pages_iter(data_folder))
        logger.info(f"Found {len(image_paths)} images in {data_folder}")

        for image_path in image_paths:
            logger.debug(f"Enqueueing {image_path} in stage 0")
            queues[0].put(image_path)

        # Send sentinel to signal end of input
        queues[0].put(sentinel)
        logger.info("All images added to queue 0. Sentinel sent.")

    except Exception as e:
        logger.error(f"Error during queue population: {e}", exc_info=True)
        queues[0].put(sentinel)


# def check_and_populate_queues(
#     data_folder: Path,
#     queues: List[Queue],
#     func_args: List[Dict[str, Any]],
#     completion_check_functions: List[Callable],
#     initialization_functions: List[Callable],
#     # shared_init_vars ,
#     num_stages: int,
#     sentinel: str, 
#     logger
# ):
#     """
#     Check which images have completed which stages and populate the appropriate
#     queues to resume processing.
#     """
#     logger.info("Checking resumability status and populating queues...")

#     try:
#         image_paths = list(pages_iter(data_folder))
#         logger.info(f"Found {len(image_paths)} images in {data_folder}")
        
#         stage_init_vars = [None] * num_stages # basically to store the configs of each stage
#         for stage_idx in range(num_stages):
#             stage_init_vars[stage_idx] = initialization_functions[stage_idx](
#                 args = SimpleNamespace(**func_args[stage_idx]) , log=None , config_only=True
#         )
            
#         # For each image, determine which stage it should enter
#         for image_path in image_paths:
#             entry_stage = 0

#             if completion_check_functions:
#                 # Start from the last stage and work backwards to find the first incomplete stage
#                 for stage_idx in range(num_stages - 1, -1, -1):
#                     check_func = completion_check_functions[stage_idx]
#                     init_vars = stage_init_vars[stage_idx]
#                     args = SimpleNamespace(**func_args[stage_idx])
#                     if check_func and check_func(args, image_path, init_vars, only_config=True):
#                         # This stage is complete, so the entry point is the next stage
#                         entry_stage = stage_idx + 1
#                         break # Found the last completed stage, no need to check earlier ones
            
#             if entry_stage < num_stages:
#                 logger.debug(f"Enqueueing {image_path} at stage {entry_stage}")
#                 queues[entry_stage].put(image_path)
#             else:
#                 logger.debug(f"Skipping {image_path}: All stages already complete.")
        
#         # If the first queue has any data, it needs a sentinel.
#         # If all data is already processed, we still need to trigger the pipeline shutdown sequence.
#         queues[0].put(sentinel)
#         logger.info("Data loading complete. Sentinel sent to the first stage.")

#     except Exception as e:
#         logger.error(f"Error during data loading and queue population: {e}", exc_info=True)
#         # Ensure the pipeline can shut down even if loading fails
#         queues[0].put(sentinel)

# def initialize_model(
#     stage_idx: int, 
#     init_var_source: List[int],
#     shared_init_vars: Any,
#     initialization_functions: List[Callable],
#     function_args: List[Dict[str, Any]],
#     logger
# ):
#     """Initialize model for a specific stage."""
#     source_idx = init_var_source[stage_idx]
    
#     if source_idx != stage_idx:
#         logger.info(f"Stage {stage_idx}: Reusing init_vars from stage {source_idx}")
#         while shared_init_vars[source_idx] is None:
#             time.sleep(0.1)
#         shared_init_vars[stage_idx] = shared_init_vars[source_idx]
#         return
    
#     init_func = initialization_functions[stage_idx]
#     if init_func is None:
#         logger.error(f"Stage {stage_idx}: No initialization function provided")
#         return
    
#     try:
#         logger.info(f"Stage {stage_idx}: Initializing models ...")
#         init_vars = init_func(
#             args = SimpleNamespace(**function_args[stage_idx]) , log=None 
#             # not sending logger as we need new stage specific logger
#         )
#         shared_init_vars[stage_idx] = init_vars
#         logger.info(f"Stage {stage_idx}: Model initialization complete")
#     except Exception as e:
#         logger.error(f"Stage {stage_idx}: Model initialization failed: {e}")
#         raise

# def terminate_model(
#     stage_idx: int, 
#     init_vars: Any,
#     init_var_source: List[int],
#     num_stages: int,
#     term_func: Callable,
#     logger
# ):
#     """
#     Terminate/cleanup model for a specific stage.
#     Only terminates if this is the last stage that uses these init_vars.
    
#     Args:
#         stage_idx: Index of the stage to terminate
#         init_vars: The initialization variables to clean up
#         init_var_source: List indicating which stage's init_vars each stage uses
#         num_stages: Total number of stages
#         termination_functions: List of termination functions
#     """
    
#     if term_func is None:
#         logger.info(f"Stage {stage_idx}: No termination function provided")
#         return
    
#     source_idx = init_var_source[stage_idx]
    
#     # Check if any later stages use the same init_vars (from the same source)
#     # We need not check previous stages since only way cur_stage gets the sentinel is if all previous stages have completed
#     has_later_stages_using_same_init = any(
#         init_var_source[i] == source_idx 
#         for i in range(stage_idx + 1, num_stages)
#     )
    
#     if has_later_stages_using_same_init:
#         logger.info(f"Stage {stage_idx}: Skipping termination - other stages still need these init_vars")
#         return
    
#     try:
#         logger.info(f"Stage {stage_idx}: Running termination function...")
#         term_func(init_vars)
#         logger.info(f"Stage {stage_idx}: Termination complete")
    
#     except Exception as e:
#         logger.error(f"Stage {stage_idx}: Termination failed: {e}")


