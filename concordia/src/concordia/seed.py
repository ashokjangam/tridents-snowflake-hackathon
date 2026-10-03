"""Frozen CONCORDIA_SIM_V1 stream seeds. NumPy 2.2.6 PCG64."""

from __future__ import annotations

import hashlib

from concordia.contracts import MASTER_SEED, SIM_CONTRACT, STREAMS

NUMPY_VERSION = "2.2.6"


def stream_material(stream: str) -> str:
    if stream not in STREAMS:
        raise KeyError(stream)
    return f"{SIM_CONTRACT}|{MASTER_SEED}|{stream}"


def stream_seed(stream: str) -> int:
    digest = hashlib.sha256(stream_material(stream).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def stream_generator(stream: str):
    import numpy as np

    if np.__version__ != NUMPY_VERSION:
        raise RuntimeError(f"CONCORDIA_SIM_V1 requires NumPy {NUMPY_VERSION}, found {np.__version__}")
    return np.random.Generator(np.random.PCG64(stream_seed(stream)))
