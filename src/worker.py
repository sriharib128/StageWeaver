import os, time, logging
from typing import Callable, List, Dict, Any, Optional
from multiprocessing import Queue
# from .model_init import terminate_model, initialize_model
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime
from multiprocessing import Queue, Process
from .utils import get_logger


def collect_batch(
    stage_idx: int,
    input_queue: Queue,
    batch_size: int,
    timeout: float,
    sentinel: str,
    logger,
    retry_buffer: list
) -> Optional[tuple]:
    """
    Collect a batch from input_queue. Wait until either (whichever comes first):
    - batch_size items are collected, OR
    - timeout seconds have passed

    Returns:
        - (batch, sentinel_received=False) normal batch
        - (batch, sentinel_received=True) batch before final sentinel
        - None → stop now (sentinel and retry_buffer empty)
    """

    batch = []
    start_time = time.time()

    while len(batch) < batch_size:
        elapsed = time.time() - start_time
        remaining = max(0.1, timeout - elapsed) # At least 0.1 second

        try:
            item = input_queue.get(timeout=remaining)

            # ---------------------------
            # SENTINEL HANDLING
            # ---------------------------
            if item == sentinel:
                logger.info(
                    f"Stage {stage_idx}: Sentinel received. Retry buffer size: {len(retry_buffer)}"
                )

                # Case A — retry buffer EMPTY → all work done → STOP this stage
                if len(retry_buffer) == 0 and len(batch) == 0:
                    logger.info(f"Stage {stage_idx}: No retries left. Finalizing stage.")
                    return None

                # Case B — retry buffer EMPTY but we already have batch → finalize after batch
                if len(retry_buffer) == 0:
                    logger.info(
                        f"Stage {stage_idx}: Retry buffer empty. "
                        f"Processing final batch of size {len(batch)}."
                    )
                    return (batch, True) # Items collected + sentinel encountered

                # Case C — retry buffer NOT empty, so we reinsert them before sentinel
                logger.info(
                    f"Stage {stage_idx}: Reinserting {len(retry_buffer)} retry items before sentinel."
                )

                # Reinsert retry items
                for r in retry_buffer:
                    input_queue.put(r)
                retry_buffer.clear()

                # Put sentinel back ONLY after retries
                input_queue.put(sentinel)

                # Continue collecting — ignore this sentinel occurrence
                continue

            # ---------------------------
            # NORMAL ITEM
            # ---------------------------
            batch.append(item)
            logger.debug(f"Stage {stage_idx}: Batch item {len(batch)}/{batch_size} collected.")

        except Exception:
            # Timeout
            if len(batch) > 0:
                logger.debug(f"Stage {stage_idx}: Batch timeout. Processing {len(batch)} items.")
                return (batch, False)
            else:
                continue

        # Hard timeout
        if time.time() - start_time >= timeout:
            if len(batch) > 0:
                logger.debug(f"Stage {stage_idx}: Batch timeout. Processing {len(batch)} items.")
                return (batch, False)

    logger.debug(f"Stage {stage_idx}: Batch full. Processing {len(batch)} items.")
    return (batch, False)

def stage_thread_worker(
    stage_idx: int,
    main_function: Callable,
    func_kwargs: Dict[str, Any],
    batch_size: int,
    timeout: float,
    input_queue: Queue,
    output_queue: Optional[Queue],
    completion_func: Callable,
    init_vars: Any,  # Shared initialization variables
    sentinel: str,
    base_logger = None,  # Logger from parent process (if no log_dir)
    log_dir: str = None
):
    """
    Thread worker for a single stage. Each thread gets its own logger.
    If base_logger is provided and no log_dir, uses the shared group logger.
    """
    # Set up thread-specific logging
    logger = get_logger(
        name=f"stage_{stage_idx}",
        log_dir=log_dir,
        log_file=f"stage_{stage_idx}.log" if log_dir else None,
        base_logger=base_logger
    )
    logger.info(f"Stage {stage_idx} thread started")
    fn_name = main_function.__name__
    is_dummy = (fn_name == "noop_processing_fn")

    if is_dummy:
        logger.info(f"Stage {stage_idx}: Running in DUMMY mode (no-op stage)")
    else:
        logger.info(f"Stage {stage_idx}: Running REAL stage function {fn_name}")


    retry_buffer = []  # per-thread retry buffer
    total_items = 0
    batch_count = 0
    stage_start = time.time()
    
    try:
        args = SimpleNamespace(**func_kwargs)
        
        while True:
            if not is_dummy:
                retry_buffer.clear() # we dont want to retry for real stages
                # we want to keep on checking if output_exists for dummy stages as other nodes might have processed them in the meantime
            batch_info = collect_batch(
                stage_idx,
                input_queue,
                batch_size,
                timeout,
                sentinel,
                logger,
                retry_buffer
            )

            # Final STOP condition
            if batch_info is None:
                logger.info(f"Stage {stage_idx}: No more work left. Shutting down.")
                break

            batch, final_sentinel = batch_info
            if not batch:
                continue

            batch_count += 1
            batch_start = time.time()
            logger.info(
                f"Stage {stage_idx} - Processing batch #{batch_count} ({len(batch)} items)"
            )

            # -------------------------
            # PRE-FILTER already completed
            # -------------------------
            pre_filtered = []
            for item in batch:
                try:
                    if completion_func and completion_func(args, item, init_vars, only_config=False):
                        logger.info(
                            f"Stage {stage_idx}: {item} already processed, forwarding."
                        )
                        if output_queue:
                            output_queue.put(item)
                    else:
                        pre_filtered.append(item)
                except Exception as e:
                    logger.error(f"Stage {stage_idx}: Pre-check failed for {item}: {e}")
                    retry_buffer.append(item)

            # -------------------------
            # MAIN PROCESS
            # -------------------------
            try:
                if pre_filtered:
                    main_function(args, pre_filtered, init_vars)
            except Exception as e:
                logger.error(f"Stage {stage_idx}: Batch processing error: {e}")
                retry_buffer.extend(pre_filtered)
                continue

            # -------------------------
            # POST CHECK
            # -------------------------
            for item in pre_filtered:
                try:
                    if completion_func and completion_func(args, item, init_vars, only_config=False):
                        if output_queue:
                            output_queue.put(item)
                        logger.info(f"Stage {stage_idx}: {item} completed, forwarded.")
                    else:
                        logger.error(f"Stage {stage_idx}: {item} failed completion, retrying.")
                        retry_buffer.append(item)
                except Exception as e:
                    logger.error(f"Stage {stage_idx}: Error in completion check: {e}")
                    retry_buffer.append(item)

            total_items += len(batch)
            logger.info(
                f"Stage {stage_idx} - Batch #{batch_count} done in {time.time()-batch_start:.2f}s"
            )

            if final_sentinel:
                logger.info(
                    f"Stage {stage_idx}: Final sentinel encountered after batch. Ending."
                )
                break

        # ------------------------------------------
        # CLEAN END
        # ------------------------------------------
        logger.info(
            f"Stage {stage_idx} finished. Total {total_items} items in "
            f"{time.time() - stage_start:.2f}s across {batch_count} batches."
        )

    except Exception as e:
        logger.error(f"Fatal error in stage {stage_idx}: {e}", exc_info=True)

    finally:
        if output_queue is not None:
            output_queue.put(sentinel)
            logger.info(f"Stage {stage_idx}: Sentinel forwarded to output queue.")
