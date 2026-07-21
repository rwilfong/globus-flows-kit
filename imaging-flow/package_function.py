"""Globus Compute function for deterministic PI-directory packaging."""

from __future__ import annotations


def create_imaging_tarball(
    pi_folder_path,
    tarball_path,
    result_path,
    overwrite_policy="fail",
):
    """Create a tar archive and JSON result atomically on the Compute worker."""
    import hashlib
    import json
    import os
    import socket
    import tarfile
    from datetime import datetime, timezone
    from pathlib import Path

    source = Path(pi_folder_path).expanduser().resolve()
    target = Path(tarball_path).expanduser().resolve()
    result_file = Path(result_path).expanduser().resolve()

    if not source.is_dir():
        raise ValueError(f"PI folder is not a directory: {source}")
    if overwrite_policy not in {"fail", "reuse", "replace"}:
        raise ValueError(f"invalid overwrite_policy: {overwrite_policy}")

    target.parent.mkdir(parents=True, exist_ok=True)
    result_file.parent.mkdir(parents=True, exist_ok=True)

    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    if target.exists():
        if overwrite_policy == "fail":
            raise FileExistsError(f"tarball already exists: {target}")
        if overwrite_policy == "reuse":
            result = {
                "status": "reused",
                "tarball_path": str(target),
                "tarball_size_bytes": target.stat().st_size,
                "sha256": sha256(target),
                "hostname": socket.gethostname(),
            }
            result_file.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            return result

    temp_tar = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temp_result = result_file.with_name(f".{result_file.name}.{os.getpid()}.tmp")

    try:
        with tarfile.open(temp_tar, mode="w") as archive:
            archive.add(source, arcname=source.name, recursive=True)

        file_count = sum(1 for path in source.rglob("*") if path.is_file())
        result = {
            "status": "created",
            "pi_folder_path": str(source),
            "tarball_path": str(target),
            "tarball_size_bytes": temp_tar.stat().st_size,
            "sha256": sha256(temp_tar),
            "source_file_count": file_count,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "hostname": socket.gethostname(),
        }
        temp_result.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        temp_tar.replace(target)
        temp_result.replace(result_file)
        return result
    finally:
        temp_tar.unlink(missing_ok=True)
        temp_result.unlink(missing_ok=True)