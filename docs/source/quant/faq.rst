FAQ
===

Why are models excluded?
------------------------
Models can be excluded by high failure rate, low empirical coverage, or too few successful folds.

Do CI tests need a permanent Timescale DB?
------------------------------------------
No. CI uses an ephemeral Timescale service container for integration tests.

What if there is no new data?
-----------------------------
The pipeline emits ``run_status=no_new_data`` and exits with code ``2`` in CLI mode.
