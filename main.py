import os
import logging
import argparse
from datetime import datetime
from src.utils import get_dummy_stage # to get dummy stage configs which skip the processing and check only if the output_path exists

from src.pipeline import StagedPipeline
from .gr_ocr_funcs import (get_functions,
    build_initialization_source, # to make sure step8_som_Stage1 and step9_som_Stage2 share the same init source
    )

def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument("--log_root", type=str, required=True)
    parser.add_argument("--root", type=str, required=True)
    parser.add_argument("--output_folder", type=str, required=True)

    parser.add_argument(
        "--steps_to_run",
        type=str,
        default="0,1,2,3,4,5,7,8,9",
        help="Comma-separated execution steps"
    )

    parser.add_argument(
        "--steps_to_check",
        type=str,
        default="",
        help="Comma-separated steps that must only be checked with dummy stages"
    )

    return parser.parse_args()


def parse_step_list(s):
    s = s.strip()
    if not s:
        return []
    return [int(x.strip()) for x in s.split(",")]


def main():
    args = parse_args()

    funcs_list = get_functions(args.root, args.output_folder)

    steps_to_run = parse_step_list(args.steps_to_run)
    steps_to_check = parse_step_list(args.steps_to_check)

    # union and sorted
    all_steps = sorted(set(steps_to_run) | set(steps_to_check)) 


    # construct stage configs (dummy vs real)
    stage_cfgs = []
    for step in all_steps:
        base_cfg = funcs_list[step]

        # if some step is in both the lists, prioritize running it
        if step in steps_to_run:
            stage_cfgs.append(base_cfg)
        else:
            stage_cfgs.append(get_dummy_stage(base_cfg))

    logger = logging.getLogger(f"PipelineLogger_{id(object())}")
    logger.setLevel(logging.INFO)

    pipeline = StagedPipeline(
        data_folder=args.root,
        stage_configs=stage_cfgs,
        initialization_source=build_initialization_source(all_steps),
        queue_size=1024,
        logger=logger
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log_dir = os.path.join(args.log_root, ts)
    os.makedirs(run_log_dir, exist_ok=True)

    pipeline.run(log_dir=run_log_dir)


if __name__ == "__main__":
    main()
