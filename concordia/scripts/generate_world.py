"""Generate the CONCORDIA_SIM_V1 world and its six source-system projections."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sim.project import write  # noqa: E402

if __name__ == "__main__":
    manifest = write(ROOT / "data" / "generated" / "world")
    print(json.dumps(manifest, indent=2))
