# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
