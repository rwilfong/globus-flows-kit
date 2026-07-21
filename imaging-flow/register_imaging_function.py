#!/usr/bin/env python3
"""Bundle and register imaging_metadata.py as a Globus Compute function."""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path

from imaging_compute_function import create_imaging_metadata_manifest


FUNCTION_NAME = "create_imaging_metadata_manifest"
HERE = Path(__file__).resolve().parent
EXTRACTOR = HERE / "imaging_metadata.py"

def registration_source() -> str:
    """Return one self-contained source module for Globus Compute."""
    extractor = EXTRACTOR.read_text(encoding="utf-8")
    main_guard = '\nif __name__ == "__main__":'
    if main_guard not in extractor:
        raise RuntimeError(f"could not find CLI main guard in {EXTRACTOR}")
    extractor_without_cli_launch = extractor.rsplit(main_guard, 1)[0]
    return (
        extractor_without_cli_launch
        + "\n\n"
        + inspect.getsource(create_imaging_metadata_manifest)
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sharing = parser.add_mutually_exclusive_group()
    sharing.add_argument("--group", help="Globus Group UUID allowed to use the function")
    sharing.add_argument(
        "--ha-endpoint-id",
        help="bind registration to one high-assurance Compute endpoint UUID",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from globus_compute_sdk import Client

    function_id = Client().register_source_code(
        registration_source(),
        function_name=FUNCTION_NAME,
        description="Extract ND2, OME-TIFF, and CZI metadata to JSONL.",
        group=args.group,
        ha_endpoint_id=args.ha_endpoint_id,
    )
    print(json.dumps({"imaging_metadata_function_id": function_id}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
