# StageWeaver
A framework for building efficient multi-step pipelines. Each stage runs in separate processes for parallelism, while stages that share initialization are grouped into a single process and executed using multithreading. StageWeaver handles process orchestration, inter-stage queues, and shared setup so you can focus on stage logic, not concurrency.
