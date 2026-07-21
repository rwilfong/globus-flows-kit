"""Build an imaging-flow input document and optionally start a deployed Globus Flow."""

from __future__ import annotations

import argparse
import sys
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


IDENTITY_MAP = {
    "FolderName": {
        "email": "PIEmail@Institution.edu",
        # Replace with the user's Globus Auth identity UUID
        "identity_id": "{Globus UUID}",
        # Set after the first run if reusing one guest collection per PI
        "guest_collection_id": "{Guest Collection ID}",
    }
}


def join_posix(root: str, *parts: str, trailing_slash: bool = False) -> str:
    value = str(PurePosixPath(root, *parts))
    if not value.startswith("/"):
        value = "/" + value
    if trailing_slash and not value.endswith("/"):
        value += "/"
    return value


def build_input(args: argparse.Namespace) -> dict:
    recipient = IDENTITY_MAP.get(args.pi_directory)
    if recipient is None:
        raise SystemExit(f"No approved identity mapping for {args.pi_directory!r}")
    if recipient["identity_id"].startswith("REPLACE-"):
        raise SystemExit("Replace the mapped Globus identity UUID before running.")

    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    package_name = f"{args.pi_directory}__{run_stamp}.tar"
    result_name = f"{package_name}.package.json"

    bell_transfer_run = join_posix(args.bell_transfer_root, args.pi_directory, run_stamp)
    bell_local_run = str(Path(args.bell_local_root, args.pi_directory, run_stamp))
    bell_transfer_dataset = join_posix(
    bell_transfer_run,
    "input",
    args.instrument,
    trailing_slash=True,
    )

    bell_local_dataset = str(
        Path(bell_local_run, "input", args.instrument)
    )

    bell_local_pi = str(
        Path(bell_local_dataset, args.pi_directory)
    )

    depot_run = join_posix(args.depot_root, args.pi_directory, run_stamp)
    tape_run = join_posix(args.tape_root, args.pi_directory, run_stamp)

    existing_guest = recipient.get("guest_collection_id", "")
    create_guest = not bool(existing_guest)

    return {
        "pi_directory": args.pi_directory,
        "source": {
            "id": args.source_collection_id,
            "path": args.source_path,
        },
        "bell": {
            "collection_id": args.bell_collection_id,
            "transfer_dataset_path": bell_transfer_dataset,
            # This root must match imaging_metadata.py's expected instrument layout.
            "local_metadata_root": bell_local_dataset,
            "local_metadata_output_path": str(Path(bell_local_pi, "imaging_metadata.jsonl")),
            "local_pi_folder_path": bell_local_pi,
            "local_tarball_path": str(Path(bell_local_run, "packages", package_name)),
            "local_package_result_path": str(Path(bell_local_run, "packages", result_name)),
            "transfer_tarball_path": join_posix(bell_transfer_run, "packages", package_name),
            "transfer_package_result_path": join_posix(bell_transfer_run, "packages", result_name),
        },
        "metadata": {
            "fortress_root": args.fortress_root,
            "timezone": "America/Indiana/Indianapolis",
            "aliases_path": None,
            "path_layout": args.path_layout,
            "strict": not args.non_strict,
        },
        "package": {
            "function_id": args.package_function_id,
        },
        "depot": {
            "mapped_collection_id": args.depot_collection_id,
            "tarball_path": join_posix(depot_run, package_name),
            "package_result_path": join_posix(depot_run, result_name),
            "guest_collection_base_path": join_posix(args.depot_root, args.pi_directory, trailing_slash=True),
        },
        "sharing": {
            "create_guest_collection": create_guest,
            "existing_guest_collection_id": existing_guest,
            "guest_collection_display_name": f"Imaging data - {args.pi_directory}",
            "recipient_identity_id": recipient["identity_id"],
            "recipient_email": recipient["email"],
            "permissions": "r",
        },
        "tape": {
            "collection_id": args.tape_collection_id,
            "tarball_path": join_posix(tape_run, package_name),
            "package_result_path": join_posix(tape_run, result_name),
        },
        "overwrite_policy": args.overwrite_policy,
    }


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--flow-id", help="Deployed Flow UUID; omit to only write input JSON")
    p.add_argument("--pi-directory", required=True)
    p.add_argument("--source-collection-id", required=True)
    p.add_argument("--instrument", required=True)
    p.add_argument("--source-path", required=True)
    p.add_argument("--bell-collection-id", required=True)
    p.add_argument("--bell-transfer-root", required=True)
    p.add_argument("--bell-local-root", required=True)
    p.add_argument("--package-function-id", required=True)
    p.add_argument("--depot-collection-id", required=True)
    p.add_argument("--depot-root", required=True)
    p.add_argument("--tape-collection-id", required=True)
    p.add_argument("--tape-root", required=True)
    p.add_argument("--fortress-root", default="/")
    p.add_argument("--path-layout", choices=("auto", "pi-student", "pi-only"), default="auto")
    p.add_argument("--overwrite-policy", choices=("fail", "reuse", "replace"), default="fail")
    p.add_argument("--non-strict", action="store_true")
    p.add_argument("--output", type=Path, default=Path("flow_input.json"))
    return p


def main() -> None:
    args = parser().parse_args()
    payload = build_input(args)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")

    if not args.flow_id:
        return

    command = [
        "globus",
        "flows",
        "start",
        args.flow_id,
        "--input",
        f"file:{args.output}",
        "--label",
        f"Imaging ingest {args.pi_directory}",
        "--format",
        "json",
    ]
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
    )

    if completed.stdout:
        print(completed.stdout)

    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()