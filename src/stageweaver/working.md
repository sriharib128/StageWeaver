1) we can pass a set of functions that we want to run in parallel but each data_item must be run sequentially
    - each image needs to pass through each of the function sequentially.
    - but while function2 is processing image1, function1 must start processing image 2.
2) we will pass this function as a list of `StageConfig`s to the StagedPipeline
3) each of `StageConfig`(single step) must have the following
    - init_fn -> things which are intialised once, but used throughout the processing loop
    - all the outputs of init_fn will be captured in a tuple named init_vars and will be available to u throughout.
    - here the init_fn must output two kinds of outputs,
        1) when we initialise with init_fn(args, log, config_only)
        2) here if log =None.. then init_fn will create a new logger for that specific_fn else use the logger sent by pipeline
        3) if config_only=False
            - this is the default operation of init_vars where all the things required for function to run are returnrf in the init_vars like VLM_service, etc.
        4) if config_only=True
            - the returned init_vars will only contain lightweight things such as config or datapaths which will be passed to `completion_func(args,item,init_vars,only_config)`
            - `completion_fn` will unpack the init_vars based on the only_config flag.
        5) this `config_only` operation is added to the init_fn to return two kinds of outputs 1) to be used by both processing and completionfn and 2) a lightweight output which can be used to quickly just run the completion fn.
            - the advantage we get by this.. sometime we dont want to run a step but we just want to check if step is done or not for a particualar item and only if done, do we want to mode to the next step
        6) this can used like this.. in main.py u can pass both steps to run and steps to check. both these indicies will be combined to a single list of stageconfigs which goes as input to Pipeline
            - but in this list .. Steps_to_check will have a `only_config=true` adn they will just run a no_op.. the only function it serves is it check for each item it gets if the output of that item exists and only if it exists then it passes this item to the further stage. if not then it will add item to a retry buffer and then recheck again at the end.
            - Steps to check will have `only_config=Flase` they will run the actual processing.
    - termination_fn -> for clean exit of the items/models loaded in init_fn
    - completion_fn(args, item, init_vars, only_config) -> checks if the item(image_path) is processed for current stage or not
    - function(args, pre_filtered, init_vars) -> the main processing function which process the list of items (pre_filter)
    - the set of args u want ur stage to have access to -> we will give args as dict.. but we do SimpleNameSpace(args) and then pass to functions of this stage, so that the function can use as if args is an argparser.
4) for steps_to_run -> u will directly append the stageconfig to a list
5) for steps_to_check -> u will wrap the stageconfig around `get_dummy_stage(stageconfig)`and then add to list. this will add a noop function, and wrap all the function with only_config = True -> so that these stages essentialy only acts to checkers of that stage and not processers.
6) Now we will pass this list of StageConfigs to StagedPipeline along with a initialization_source which is a list of int
    - if this is left empty then then default will be a list of len = len(stageconfigs) and list[i] = i
    - this essentially means that each stage uses its only init_function and init_vars.
    - but if list[i] = x where x < i then i th stage will use the init_vars of x th stage. 
    - what happens under the hood is.. pipeline will group the stages that share common init_vars into a group.. if a stage is not sharing with anything then that group will have only one stage.
7) Now each stage will have a input and ouputqueue. output queue of stage0 and input_queu of stage1 is same. each stage takes a batch of items from its input_queue.. checks if it is done using completion fn, if done puts them directly in output queue.. takes those items that not done, processes them.. again checks if done and then puts into output_queue.
    - Those item that are not done even after processing are stopped there itself, they are not put into output_queue for further processing
    - if the stage is a dummy stage(steps to check) then if completion_fn fails, we simple add them to a retry buffer to check later.
8) a stage will know if its work is done.. only if it gets a "sentinel" in its input_queue. When a stage gets a sentinel if retru buffer is not free then we insert the rertyr buffer into theinput queue and then add sentinel at the end. if retry buffer is free then we simply end the stage by running termination function
9) Working of entire System
    - main.py will send a list of stageconfigs along with init_soruce to pipeline
    - pipeline will see inti_source and create a group for each unique inti_source.
    - a logger for entire pipeline in created
10) in main.py when pipeline.run is entered
    - a check and populatequeue process runs and puts image_paths in the input_queu[0] and adds "sentinel" at the end
    - a separate process for each group is started
11) inside each group process
    - we create a separate logger for each group.
    - run init_fn and get inti_vars
    - then initalise each stage that belongs to this group in a thread and passes the common inti_vars
    - if cur_group has only 1 stage then we send the same logger we initialised to it, else each thread creates its own logger.
    - after all the threads are done.. we run the termination_fn
12) Inside each stage_thread_worker
    - if create a logger/ use the logger of parent group
    - collect bath, filter completed, process those not completed, check again, put in output queue or retry buffer or just leave.
