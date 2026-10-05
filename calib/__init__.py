"""Self-calibrating model engine for the NHL model.

    db.py        prediction database (SQLite, append-only): every projection, its inputs, the actual result
    metrics.py   error metrics (MAE, RMSE, bias, ...) over windows and segments
    bias.py      systematic-bias detection with significance tests and false-discovery control
    engine.py    recalibration: residual model on the projection's own components, sample-size shrinkage,
                 walk-forward backtest, accept / reject, model versions
    health.py    the Model Health payload for the web pages (metrics, biases, chart series, versions)
    config.py    thresholds (shrinkage tiers, significance, caps) in one place
    __main__.py  python -m calib {status, recalibrate, health} --sport nhl
"""
