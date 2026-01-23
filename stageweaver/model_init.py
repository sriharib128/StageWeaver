from multiprocessing import Queue
from pathlib import Path
from typing import List

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
