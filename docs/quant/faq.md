# FAQ

## Why are some models excluded?
Models are excluded due to high fold failure rate, low empirical coverage, or insufficient successful folds.

## Does CI need a permanent DB?
No. Timescale integration tests use an ephemeral service container in CI.

## What if no new data arrives?
Pipeline writes artifacts with `run_status=no_new_data` and returns exit code `2` in CLI mode.
