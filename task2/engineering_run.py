"""Frozen-input Python/STK engineering verification; legacy comparison helper retained."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys


def compare_region_intervals(coarse, fine, tolerance_s=.02):
    """Require identical per-satellite contact topology, then compare every endpoint."""
    import numpy as np
    columns=['sat_id','start_s','stop_s']
    a=coarse.sort_values(columns)[columns].to_numpy(float)
    b=fine.sort_values(columns)[columns].to_numpy(float)
    same=(a.shape==b.shape and np.array_equal(a[:,0],b[:,0]))
    delta=float(np.max(np.abs(a[:,1:]-b[:,1:]))) if same and len(a) else (0. if same else None)
    return dict(counts=[len(a),len(b)],satellite_sequence_equal=same,
                max_endpoint_difference_s=delta,endpoint_tolerance_s=tolerance_s,
                ok=bool(same and delta<=tolerance_s))


def main():
    from engineering_validation import main as verify
    verify()


if __name__ == '__main__':
    main()
