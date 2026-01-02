import copy
from src.datamodels import StageConfig

from gr_ocr.drivers import detect, layout, doctr,textar, recognition, run_som_html_new as run_som_html
from gr_ocr.som_html.stages import preprocess, ocr, stage1 as som_stage1, stage2 as som_stage2


# Configurable paths
# ROOT="/projects/data/vision-team/aryan_jain/Patram-Eval/spdocvqa/val_images"
# OUTPUT_FOLDER="outputs_3"

def build_initialization_source(step_indices):
    """
    Builds the initialization_source list for StagedPipeline.

    Default behavior:
        initialization_source[i] = i  
        (each stage initializes from its own output)

    Special case:
        Steps 8 and 9 form a coupled SOM pipeline which use the same model.
        Step 9 must reuse the initialization state(vllm engine) of Step 8.
        So, if both steps 8 and 9 exist:
            initialization_source[pos_of_9] = pos_of_8

    Example:
        steps = [0,1,2,7,8,9]
        positions: 8→4, 9→5
        default init = [0,1,2,3,4,5]
        adjusted init = [0,1,2,3,4,4]
        (step 9 now initializes from step 8)

    """
    n = len(step_indices)
    init_src = list(range(n))  # default

    if 8 in step_indices and 9 in step_indices:
        pos_8 = step_indices.index(8)
        pos_9 = step_indices.index(9)
        init_src[pos_9] = pos_8

    return init_src

def get_functions(ROOT, OUTPUT_FOLDER):
    TEXT_DETECTION_DIR = f"{OUTPUT_FOLDER}/text_detections"  # Text detection results
    TEXT_DETECTION_CONFIG = "config/ocr_config.yaml"

    LAYOUT_DETECTION_DIR = f"{OUTPUT_FOLDER}/layout_detections"  # Layout detection results
    LAYOUT_DETECTION_CONFIG = "config/flat_layout.yaml"
    UNIFIED_MAPPING_CONFIG = "config/unified_mapping.yaml"

    TEXT_RECOGNITION_DIR = f"{OUTPUT_FOLDER}/text_recognition"
    TEXT_RECOGNITION_CONFIG = "config/text_recognition.yaml"

    DOCTR_DETECTION_DIR = f"{OUTPUT_FOLDER}/doctr_detections"
    DOCTR_CONFIG_PATH = "config/attribute_params.yaml"

    TEXTAR_DETECTION_DIR = f"{OUTPUT_FOLDER}/textar_detections"
    TEXTAR_CONFIG_PATH = "config/attribute_params.yaml"

    VIZ_DIR = f"{OUTPUT_FOLDER}/viz"
    CROPS_DIR = f"{OUTPUT_FOLDER}/crops"
    OCR_DIR = f"{OUTPUT_FOLDER}/ocr"

    # FONT_ADJUST_CONFIG = "config/font_adjust.yaml"
    # HTML_MERGE_CONFIG = "config/html_merging.yaml"
    # LLM_MODEL = "Qwen/Qwen2.5-VL-72B-Instruct"
    # os.environ['BASE_SOM_OUTPUT_DIR'] = OUTPUT_FOLDER # we have set this in the bash script

    SOM_HTML_CONFIG = "config/som_html_parallel.yaml"

    # ---------- STAGE 1: Text Detection ----------
    step0_text_detection_stage = StageConfig(
        name = "Text Detection (Hi-Sam)",
        function=detect.process_image_paths,
        args={
            "cfg": TEXT_DETECTION_CONFIG,
            "root": ROOT,
            "output_dir": TEXT_DETECTION_DIR,
            "global_batch_size": 64,
            "read_threads": 8,
            "write_threads": 8
        },
        queue_batch_size=32,
        queue_timeout=5.0,
        init_fn=detect.models_init,
        completion_fn=detect.check_output_exists,
        termination_fn=detect.models_end
    )

    # ---------- STAGE 2: Layout Detection ----------
    step1_layout_stage = StageConfig(
        name = "Layout Detection (DocLayNet + IndicDLP)",
        function=layout.process_image_paths,
        args={
            "cfg": LAYOUT_DETECTION_CONFIG,
            "unified_mapping": UNIFIED_MAPPING_CONFIG,
            "root": ROOT,
            "text_det": TEXT_DETECTION_DIR,
            "layout_dir": LAYOUT_DETECTION_DIR,
            "global_batch_size": 64,
            "vizualization_dir":"viz",
            "read_threads": 8,
            "write_threads": 8
        },
        queue_batch_size=56,
        queue_timeout=5.0,
        init_fn=layout.models_init,
        completion_fn=layout.check_output_exists,
        termination_fn=layout.models_end
    )

    # ---------- STAGE 3: DocTr OCR ----------
    step2_doctr_stage = StageConfig(
        name = "DocTr",
        function = doctr.process_image_paths,
        args={
            "root": ROOT,
            "cfg": DOCTR_CONFIG_PATH,
            "doctr_dir": DOCTR_DETECTION_DIR,
            "global_batch_size": 128,
            "write_threads": 8
        },
        queue_batch_size=128,
        queue_timeout=5.0,
        init_fn=doctr.models_init,
        completion_fn=doctr.check_output_exists,
        termination_fn=doctr.models_end
    )

    # ---------- STAGE 4: TextAR Detection ----------
    step3_textar_stage = StageConfig(
        name = "TextAR",
        function = textar.process_image_paths,
        args={
            "root": ROOT,
            "cfg": TEXTAR_CONFIG_PATH,
            "textar_dir": TEXTAR_DETECTION_DIR,
            "doctr_dir": DOCTR_DETECTION_DIR,
            "write_threads": 8
        },
        queue_batch_size=32,
        queue_timeout=5.0,
        init_fn=textar.models_init,
        completion_fn=textar.check_output_exists,
        termination_fn=textar.models_end
    )
    
    # ---------- STAGE 5: SOM HTML Crops (Preprocessing) ----------
    step4_crop_stage = StageConfig(
        name = "Crops Preprocessing",
        function=preprocess.crop_preprocess,
        args={
            "root_dir": ROOT,
            "layout_dir": LAYOUT_DETECTION_DIR,
            "text_dir": TEXT_DETECTION_DIR,
            "viz_dir": VIZ_DIR,
            "crops_dir": CROPS_DIR,
            "ocr_dir": OCR_DIR,
            "preprocess_threads": 8,
            "config": SOM_HTML_CONFIG
        },
        queue_batch_size=32,
        queue_timeout=5.0,
        init_fn=preprocess.crop_model_init,
        completion_fn=preprocess.check_crop_output_exists,
        termination_fn=preprocess.crop_models_end,

    )

    # ---------- STAGE 6: SOM HTML Visualization Preprocessing ----------
    step5_viz_stage = StageConfig(
        name = "Visualization Preprocessing(SOM)",
        function=preprocess.viz_som_preprocess,
        args={
            "root_dir": ROOT,
            "layout_dir": LAYOUT_DETECTION_DIR,
            "text_dir": TEXT_DETECTION_DIR,
            "viz_dir": VIZ_DIR,
            "preprocess_threads": 8,
            "config": SOM_HTML_CONFIG
        },
        queue_batch_size=32,
        queue_timeout=5.0,
        init_fn=preprocess.viz_model_init,
        completion_fn=preprocess.check_viz_output_exists,
        termination_fn=preprocess.viz_models_end
    )

    # ---------- STAGE 7: Text Recognition ----------
    step6_recognition_stage = StageConfig(
        name = "Text Recognition(Surya)",
        function=recognition.process_image_paths,
        args={
            "root": ROOT,
            "cfg": TEXT_RECOGNITION_CONFIG,
            "detection_dir": TEXT_DETECTION_DIR,
            "recognition_dir": TEXT_RECOGNITION_DIR,
            "read_threads": 8,
            "write_threads": 8,
            "crops_dir": CROPS_DIR,
        },
        queue_batch_size=1024,
        queue_timeout=5.0,
        init_fn=recognition.models_init,
        completion_fn=recognition.check_output_exists,
        termination_fn=recognition.models_end
    )

    # ---------- SOM HTML Pipeline Arguments ----------
    som_args = {
        "root_dir": ROOT,
        "layout_dir": LAYOUT_DETECTION_DIR,
        "text_dir": TEXT_DETECTION_DIR,
        "textar_dir": TEXTAR_DETECTION_DIR,
        "viz_dir": VIZ_DIR,
        "crops_dir": CROPS_DIR,
        "ocr_dir": OCR_DIR,
        "model_stage1": "logics-parsing",
        "model_stage2": "logics-parsing",
        "vizualization_dir": "viz",
        "stages": "0",
        "preprocess_threads": 8,
        "config": SOM_HTML_CONFIG
    }

    # ---------- STAGE 8: SOM HTML OCR Processing ----------
    ocr_args = copy.deepcopy(som_args)
    ocr_args['stages'] = "0"
    step7_som_ocr_stage = StageConfig(
        name = "OCR Processing",
        function=ocr.process_ocr,
        args=ocr_args,
        queue_batch_size=64,
        queue_timeout=5.0,
        init_fn=run_som_html.models_init,
        completion_fn=ocr.check_output_exists,
        termination_fn=run_som_html.models_end
    )

    # ---------- STAGE 9: SOM HTML Stage 1 (Structure Parsing) ----------
    stage1_args = copy.deepcopy(som_args)
    stage1_args['stages'] = "1"
    step8_som_stage1_stage = StageConfig(
        name = "SOM HTML Stage 1",
        function=som_stage1.process_stage1,
        args=stage1_args,
        queue_batch_size=8,
        queue_timeout=5.0,
        init_fn=run_som_html.models_init,
        completion_fn=som_stage1.check_output_exists,
        termination_fn=run_som_html.models_end
    )

    # ---------- STAGE 10: SOM HTML Stage 2 (Final HTML Rendering) ----------
    stage2_args = copy.deepcopy(som_args)
    stage2_args['stages'] = "2"
    step9_som_stage2_stage = StageConfig(
        name = "SOM HTML Stage 2",
        function=som_stage2.process_stage2,
        args=stage2_args,
        queue_batch_size=8,
        queue_timeout=5.0,
        init_fn=run_som_html.models_init,
        completion_fn=som_stage2.check_output_exists,
        termination_fn=run_som_html.models_end
    )

    return [
        step0_text_detection_stage,
        step1_layout_stage,
        step2_doctr_stage,
        step3_textar_stage,
        step4_crop_stage,
        step5_viz_stage,
        step6_recognition_stage,
        step7_som_ocr_stage,
        step8_som_stage1_stage,
        step9_som_stage2_stage
    ]

