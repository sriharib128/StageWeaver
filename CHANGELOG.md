# Changelog

All notable changes to this project will be documented in this file.

## [0.4.0] - 2026-04-16

- Reorganized codebase. Moved all old file based stageweaver into `legacy/`
- Right now its sqlite3 based. We have to add support to postgres based pipeline.

## [0.3.0] - 2026-02-20

- **README.md** added for DB-based pipelines, detailing installation, execution flow, state machine, and core concepts.
- Added `example_flow.py` showcasing a complete working example of a DB-based staged pipeline.

## [0.2.2] - 2026-02-19

- Include log_dir in the logger name to avoid the global singleton collision.


## [0.2.1] - 2026-01-31

- Added a signal_handler for each group process which sets a threading.event in case of interruption and this singal will be propogated to main stage function
- Added logging such that all logs of a run appear together

## [0.2.0] - 2026-01-27

- Added a `DbStagedPipeline` class in `db_pipeline.py` for database-specific staged pipelines.
- Introduced `DbStageConfig` dataclass in `datamodels.py` for database stage configurations.
- Implemented database connection pooling and management in `db_pipeline.py`.
- TODO: Update README.md and documentation to include database pipeline usage.

## [0.1.1] - 2026-01-24

### Fixed
- Corrected typo in documentation for `StageConfig` parameters

## [0.1.0] - 2026-01-23

### Added
- Initial release of StageWeaver
- Core `StagedPipeline` class for multi-stage parallel processing
- `StageConfig` dataclass for stage configuration
- Hybrid multiprocessing-threading architecture
- Resource sharing via `initialization_source` parameter
- Per-item completion tracking and resumability
- Queue-based backpressure control
- `get_dummy_stage()` utility for dry-run testing
- `get_logger()` utility for unified logging
- Comprehensive documentation and examples

### Features
- Zero external dependencies (pure Python stdlib)
- Python 3.8+ support
- MIT license
- Production-ready error handling and logging
