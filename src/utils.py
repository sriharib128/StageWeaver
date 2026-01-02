import copy
import functools
import os, logging
from .datamodels import StageConfig

def get_dummy_stage(stage_cfg: StageConfig) -> StageConfig:
    """
    Create a dummy version of a stage_config whose purpose is:
      - Skip actual stage processing.
      - Preserve and reuse the original check_output / completion logic.
      - Ensure init_fn and completion_fn are called in 'config-only' mode.
      - Keep queue + args structure identical so downstream stages work.
    """

    # ---- No-op processing function (replaces actual heavy computation) ----
    @functools.wraps(stage_cfg.function)
    def noop_processing_fn(*args, **kwargs):
        return None  # intentionally do nothing

    # ---- Init wrapper: force config-only mode ----
    original_init = stage_cfg.init_fn
    @functools.wraps(original_init)
    def config_only_init(*args, **kwargs):
        kwargs["config_only"] = True
        return original_init(*args, **kwargs)

    # ---- Completion wrapper: run original check_output in config-only mode ----
    original_completion = stage_cfg.completion_fn
    @functools.wraps(original_completion)
    def config_only_completion(*args, **kwargs):
        kwargs["only_config"] = True
        return original_completion(*args, **kwargs)

    # ---- Termination fn becomes a no-op ----
    @functools.wraps(stage_cfg.termination_fn)
    def noop_termination(*args, **kwargs):
        return None

    # ---- Construct the dummy stage ----
    return StageConfig(
        name = f"dummy_{stage_cfg.name}",
        function = noop_processing_fn,           # heavy work skipped
        args = copy.deepcopy(stage_cfg.args),         # preserve structure for downstream stages
        queue_batch_size = stage_cfg.queue_batch_size,
        queue_timeout = stage_cfg.queue_timeout,
        init_fn = config_only_init,              # initialize only config
        completion_fn = config_only_completion,  # use check_output only
        termination_fn = noop_termination,
    )

def get_logger(
    name: str,
    log_dir: str = None,
    log_file: str = None,
    base_logger = None
):
    """
    Unified logger creation function for both group workers and stage workers.
    
    Args:
        name: Logger name (e.g., "group_0" or "stage_1")
        log_dir: Directory for log files. If None, uses base_logger or console.
        log_file: Filename for the log (used only if log_dir is provided)
        base_logger: Existing logger to use if log_dir is None (thread-safe sharing)
    
    Returns:
        Logger instance
    
    Behavior:
        - If log_dir provided: Creates file logger at log_dir/log_file
        - If log_dir is None and base_logger provided: Returns base_logger (shared)
        - If both None: Creates console logger
    """
    # If no log_dir and base_logger exists, share it (thread-safe)
    if log_dir is None and base_logger is not None:
        return base_logger
    
    # Create or get logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    if log_dir and log_file:
        # File logger
        os.makedirs(log_dir, exist_ok=True)
        full_path = os.path.join(log_dir, log_file)
        fh = logging.FileHandler(full_path, mode="w")
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        logger.info(f"{name} logger initialized at {full_path}")
    else:
        # Console logger
        ch = logging.StreamHandler()
        fmt = logging.Formatter(f"%(asctime)s [%(levelname)s] {name}: %(message)s")
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    return logger
