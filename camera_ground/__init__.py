"""Offline CH01/CH02 ground calibration. No recording or camera control."""

# Keep offline checks gentle on shared machines; operators can explicitly override.
import os
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

__version__ = "1.0.0"
