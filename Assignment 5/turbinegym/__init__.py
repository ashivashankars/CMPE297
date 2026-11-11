"""TurbineGym: a laptop RSI environment for wind-turbine gearbox failure early warning."""
import os as _os
# Small models + many fits: one OpenMP thread per process is much faster and avoids
# thread oversubscription when several experiments run side by side.
_os.environ.setdefault("OMP_NUM_THREADS", "1")
from .fleet import make_fleet, describe, TRAIN_END, STEER_END, FIRMWARE_FACTOR
from .pipeline import (baseline_config, render, normalise, config_key, diff_features,
                       unified_diff, DIFF_FEATURE_NAMES, TRANSFORM_NAMES, BASE_FEATURES)
from .services import TurbineGym, BudgetExceeded
from . import edits, metrics

# A hand-built pipeline that uses ground-truth knowledge of the simulator.
# It is NEVER shown to an improver; it only calibrates "how good can this get".
ORACLE_CONFIG = {
    "transforms": ["impute_particles", "firmware_rescale", "turbine_zscore", "oil_residual",
                   "vib_slope14", "oil_slope14", "particle_log"],
    "features": ["particles"],
    "model": "hgb",
    "params": {"C": 1.0, "max_depth": 3, "lr": 0.1},
    "class_weight": "balanced",
    "alarm_rate": 0.08,
}
