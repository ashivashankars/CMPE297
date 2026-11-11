"""
TurbineGym fleet simulator.

Problem area: early warning of wind-turbine gearbox failures (predictive maintenance).
Task: every day, for every turbine, predict "will this gearbox fail in the next 14 days?"

The simulator plants FOUR hidden mechanisms. An improver that only tweaks surface
knobs (threshold, regularisation) cannot fix them; an improver that diagnoses them can.

  1. Per-turbine calibration offset - each vibration sensor has its own baseline
     (0.6x .. 2.2x). Raw vibration mixes "this sensor reads high" with "this gearbox is wearing".
  2. Firmware unit change - half the fleet gets a firmware update around day 170-230.
     After it, vibration is reported in different units (x2.2). Training data is mostly
     pre-update; steering and held-out data are mostly post-update -> false alarms.
  3. Seasonal confounding - gearbox oil temperature follows ambient temperature and load.
     The wear signal (+12 C) hides inside a 30 C seasonal swing.
  4. Sensor dropout - the oil-particle counter is offline ~15% of the time (NaN).

Everything is generated from a seed, so every lab is reproducible.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

N_TURBINES = 24
N_DAYS = 360
HORIZON = 14            # predict failure within the next 14 days
DEGRADE_DAYS = 30       # wear becomes visible ~30 days before failure
REPAIR_DAYS = 5         # turbine is offline for repairs after a failure
FIRMWARE_FACTOR = 2.2   # hidden unit change after firmware v2

TRAIN_END = 210         # days [0, 210)   -> train
STEER_END = 285         # days [210, 285) -> steering split (used for selection)
                        # days [285, 360) -> held-out split (never used for selection)


def make_fleet(seed: int = 7, firmware_factor: float = FIRMWARE_FACTOR) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for tid in range(N_TURBINES):
        vib_offset = float(np.exp(rng.uniform(np.log(0.5), np.log(3.0))))
        particle_base = rng.uniform(3, 14)
        oil_offset = rng.normal(0, 3.0)
        updated = tid % 2 == 0                      # half the fleet gets firmware v2
        fw_day = int(rng.integers(150, 231)) if updated else 10_000

        # failure days: 1-3 per turbine, at least 70 days apart, after day 40
        n_fail = int(rng.integers(1, 4))
        fails = []
        while len(fails) < n_fail:
            d = int(rng.integers(40, N_DAYS + 20))  # some failures fall after the window
            if all(abs(d - f) > 70 for f in fails):
                fails.append(d)
        fails.sort()

        phase = rng.uniform(0, 2 * np.pi)
        for day in range(N_DAYS):
            # offline during repair
            if any(f <= day < f + REPAIR_DAYS for f in fails):
                continue
            upcoming = [f - day for f in fails if f - day > 0]
            to_fail = min(upcoming) if upcoming else 10_000
            health = 0.0 if to_fail > DEGRADE_DAYS else (1 - to_fail / DEGRADE_DAYS) ** 2

            ambient = 15 + 12 * np.sin(2 * np.pi * day / 365 - 1.3) + rng.normal(0, 2.5)
            wind = max(0.5, rng.gamma(4.0, 2.0))
            power = float(np.clip((wind / 12) ** 3, 0, 1))
            rpm = 8 + 8 * power + rng.normal(0, 0.4)

            fw2 = day >= fw_day
            vib_true = vib_offset * (1 + 0.8 * health + 0.15 * power) * np.exp(rng.normal(0, 0.12))
            vibration = vib_true * (firmware_factor if fw2 else 1.0)
            oil = ambient + 25 + oil_offset + 9 * power + 8 * health + rng.normal(0, 2.0)
            particles = float(rng.poisson(particle_base * rng.gamma(2.0, 0.5) + 25 * health ** 2))
            if rng.random() < 0.15:
                particles = np.nan

            rows.append(dict(
                turbine_id=tid, day=day, firmware=2 if fw2 else 1,
                vibration=round(vibration, 4), oil_temp=round(oil, 3),
                ambient_temp=round(ambient, 3), wind_speed=round(wind, 3),
                power=round(power, 4), rotor_rpm=round(rpm, 3), particles=particles,
                label=int(0 < to_fail <= HORIZON),
            ))
    df = pd.DataFrame(rows)
    df["split"] = np.where(df.day < TRAIN_END, "train",
                  np.where(df.day < STEER_END, "steer", "heldout"))
    return df


def describe(df: pd.DataFrame) -> str:
    out = []
    for s in ["train", "steer", "heldout"]:
        d = df[df.split == s]
        out.append(f"{s:8s} rows={len(d):5d} positives={d.label.sum():4d} "
                   f"({d.label.mean():.1%})  firmware-v2 rows={(d.firmware == 2).mean():.0%}")
    return "\n".join(out)


if __name__ == "__main__":
    df = make_fleet()
    print(describe(df))
