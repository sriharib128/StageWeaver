Decisions
- changed detect.py such that it has function
 - `check_output_exists(args, page_path:Path, init_vars)->bool:`
 - `models_init(args,log): `
    - anything u want to load once and have access to it throughout all the batches
    - if log is None it will create a new logger for this stage.
    - this allows us to use a common logger throughout or a function specific logger
    - this will return a tuple of intialisation variables all of which will go into process_image_paths, so make sure u unpack correctly in the process_image_paths function
    - return init_vars
 - `def process_image_paths(args, pages_todo: List[Path], init_vars):`
 - `def models_end(init_vars):`
    - unloads the models_loaded
- make sure these functions exist for any future method u create
- and always initialise logger in main and then pass it as arguments to functions as we may call this function in a different file.
- considering multiprocessing instead of multithreading because of GIL and as it allows us to have process specific environ variables
- Using static method for stage_worker and collect batch
    - A static method is a method that belongs to a class rather than to an instance of the class, meaning it can be called directly on the class name without needing to create an object. These methods cannot access instance variables directly but can operate on static variables and other static methods.
    - Avoids Pickling the Entire Instance, since self is not need for these static functions
    - Without @staticmethod:
        - Python would try to pickle the entire StagedPipeline instance (the self object)
        - This includes all queues, managers, function references, etc.
        - Many of these objects (like Queue, Manager) don't pickle well or can cause circular reference issues
    - When a method is called on an instance (e.g., self.method()), Python must first look up the method and then bind the instance (self) to the function definition. When calling a static method (StagedPipeline._stage_worker(...)), this binding step is skipped
- init_var_source must be such that at anypoint value<=idx of that list
- after each stage_worker runs a batch we will again use check_completion function to check if that stage was successfull for each image, and only if successful we will put in the next queue

- change such that inside worker.. if log_dir arg is empty then continue with the logger it got, else create a new stage_specific logger and print to a log file in the log_dir
- check each image passed in the batch inside stage worker also for completion and run only not completed files .. completed files will directly be put into output queue


