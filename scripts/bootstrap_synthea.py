"""Download, verify, and prepare the paired Synthea CSV/C-CDA sample."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data"
DEFAULT_GENERATED = ROOT / "generated"


@dataclass(frozen=True)
class Archive:
    name: str
    url: str
    sha256: str
    destination: str


ARCHIVES = (
    Archive(
        name="synthea_sample_data_csv_latest.zip",
        url=(
            "https://synthetichealth.github.io/synthea-sample-data/downloads/latest/"
            "synthea_sample_data_csv_latest.zip"
        ),
        sha256="D61417B551E5B0997C33851B339C157421751F0EA68C18EA686CEB1850907C35",
        destination="csv",
    ),
    Archive(
        name="synthea_sample_data_ccda_latest.zip",
        url=(
            "https://synthetichealth.github.io/synthea-sample-data/downloads/latest/"
            "synthea_sample_data_ccda_latest.zip"
        ),
        sha256="CAC8F607B8ACD56D38B69A3A8FD4877B3606E37CE486A670C8C232F2E0C4719D",
        destination="ccda",
    ),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def download(archive: Archive, data_dir: Path) -> Path:
    target = data_dir / archive.name
    if not target.exists():
        print(f"Downloading {archive.url}")
        urllib.request.urlretrieve(archive.url, target)
    actual = sha256(target)
    if actual != archive.sha256:
        raise ValueError(
            f"{archive.name} SHA-256 mismatch: expected {archive.sha256}, got {actual}"
        )
    print(f"Verified {archive.name}: {actual}")
    return target


def extract(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"Unsafe zip member: {member.filename}")
        archive.extractall(destination)
    print(f"Extracted {source.name} to {destination}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--generated-dir", type=Path, default=DEFAULT_GENERATED)
    parser.add_argument("--skip-parse", action="store_true")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    for archive in ARCHIVES:
        extract(download(archive, args.data_dir), args.data_dir / archive.destination)
    if args.skip_parse:
        return 0
    command = [
        sys.executable,
        str(ROOT / "scripts" / "parse_ccda.py"),
        "--ccda-dir",
        str(args.data_dir / "ccda"),
        "--csv-dir",
        str(args.data_dir / "csv"),
        "--patients-csv",
        str(args.data_dir / "csv" / "patients.csv"),
        "--output-dir",
        str(args.generated_dir),
        "--expected-documents",
        "108",
    ]
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
