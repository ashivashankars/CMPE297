"""Download every real dataset used in this repo and pin it with a SHA-256.

All sources are public mirrors of well-known Kaggle / UCI / benchmark datasets.
Run once:  python data/fetch_data.py
The manifest (data/MANIFEST.json) records URL, size and hash so a reviewer can
confirm the exact bytes each model was trained on (reproducibility audit).
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import urllib.request

RAW = pathlib.Path(__file__).parent / "raw"
GH = "https://raw.githubusercontent.com"
NAB = f"{GH}/numenta/NAB/master/data/realKnownCause"

SOURCES = {
    # Project 01 - NYC TLC yellow/green taxi rides (March 2019 sample, seaborn mirror)
    "taxis.csv": f"{GH}/mwaskom/seaborn-data/master/taxis.csv",
    # Project 02 - Tiny Shakespeare corpus (Karpathy char-rnn)
    "tinyshakespeare.txt": f"{GH}/karpathy/char-rnn/master/data/tinyshakespeare/input.txt",
    # Project 03 - Kaggle "Mall Customer Segmentation Data"
    "mall_customers.csv": f"{GH}/SteffiPeTaffy/machineLearningAZ/master/Machine%20Learning%20A-Z%20Template%20Folder/Part%204%20-%20Clustering/Section%2025%20-%20Hierarchical%20Clustering/Mall_Customers.csv",
    # Project 04 - Groceries transactions (Hahsler arules dataset, also on Kaggle)
    "groceries.csv": f"{GH}/stedy/Machine-Learning-with-R-datasets/master/groceries.csv",
    # Project 06 - Numenta Anomaly Benchmark, real series with known-cause failures
    "nab_machine_temperature.csv": f"{NAB}/machine_temperature_system_failure.csv",
    "nab_ambient_temperature.csv": f"{NAB}/ambient_temperature_system_failure.csv",
    "nab_cpu_asg_misconfig.csv": f"{NAB}/cpu_utilization_asg_misconfiguration.csv",
    "nab_ec2_latency.csv": f"{NAB}/ec2_request_latency_system_failure.csv",
    "nab_nyc_taxi.csv": f"{NAB}/nyc_taxi.csv",
    "nab_labels.json": f"{GH}/numenta/NAB/master/labels/combined_windows.json",
    # Project 12 - Open Power System Data, German daily electricity consumption
    "opsd_germany_daily.csv": f"{GH}/jenfly/opsd/master/opsd_germany_daily.csv",
}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in SOURCES.items():
        dest = RAW / name
        if not dest.exists():
            print(f"downloading {name} ...")
            urllib.request.urlretrieve(url, dest)
        blob = dest.read_bytes()
        manifest[name] = {"url": url, "bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}
        print(f"  {name:32s} {len(blob):>9,d} bytes")
    (RAW.parent / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    print("wrote data/MANIFEST.json")


if __name__ == "__main__":
    main()
