Getting Started
===============

Install with quant extras:

.. code-block:: bash

   pip install -e ".[dev,forecasting,quant]"

Run from CLI:

.. code-block:: bash

   python -m sktime_quant.run --config config.yaml --print-summary

Minimal config:

.. code-block:: yaml

   run_id: demo_run
   data:
     source_type: csv
     csv_path: ./examples/quant/data/sample_market.csv
   backtest:
     window_length: 60
     step_length: 10
     horizon: 1
   model:
     candidates: [naive_last, naive_mean, theta]
   execution:
     output_dir: ./results
