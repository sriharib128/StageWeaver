import copy
import functools
import os, logging
from typing import List

class FsyncFileHandler(logging.FileHandler):
    """
    Adding an os.fsync wrapper around logging.FileHandler so that even in aws fsx, logging wont be buffered.
    """
    def emit(self, record):
        super().emit(record)
        self.flush()
        os.fsync(self.stream.fileno())
        
def get_logger(log_dir, name):

    # Create a logger
    # logger_name = name --> TODO this causes a lot of issue!! (something about logger being global and process-wide singletons)
    logger_name = f"{name}:{os.path.abspath(log_dir)}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO) 

    logger.propagate = False # --> TODO verify what it does
    
    if not logger.handlers:
        # Create a file handler that writes log messages to the file
        # file_handler = logging.FileHandler(log_file)

        # Create a log file path using the given directory and name
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{name}.log")

        file_handler = FsyncFileHandler(log_file)
        file_handler.setLevel(logging.INFO)  # Set the file handler's level to INFO

        # Create a console handler to also print logs to the console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)  # Set the console handler's level to INFO

        # Define a log formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Apply the formatter to the handlers
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # Add handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

def get_bit_mask(stages_to_mark_1: List[int]):
    """
    Create a bit mask with 1s at positions specified by stages_to_mark_1 (0-based).
    Returns:
        An integer bit mask with 1s at the specified positions (LSB is stage 0)
    """
    bit_mask = 0 # since we start with 0, we dont need to total number of stages to calculate bit mask
    for stage_idx in stages_to_mark_1:
        bit_mask |= (1 << stage_idx)
    return bit_mask