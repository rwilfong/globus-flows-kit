"""Globus Compute wrapper for the existing imaging_metadata.py CLI."""


def create_imaging_metadata_manifest(
    root,
    output_path,
    fortress_root="/",
    timezone="America/Indiana/Indianapolis",
    aliases_path=None,
    path_layout="auto",
    strict=True,
):
    """Run imaging_metadata.py on a Compute worker and return a summary.

    ``root``, ``output_path``, and ``aliases_path`` are worker-visible paths.
    ``fortress_root`` is the collection-visible prefix stored in each record.
    """
    import socket
    from pathlib import Path

    # During Compute execution, register_compute_function.py bundles the
    # extractor into the same source module, so its main() is already global.
    # The fallback makes this wrapper directly testable from the repository.
    try:
        extractor_main = main
    except NameError:
        from imaging_metadata import main as extractor_main

    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        str(root),
        "--output", str(output),
        "--fortress-root", str(fortress_root),
        "--timezone", str(timezone),
        "--path-layout", str(path_layout),
    ]
    if aliases_path:
        argv.extend(["--aliases", str(aliases_path)])
    if strict:
        argv.append("--strict")

    exit_code = extractor_main(argv)
    if exit_code:
        raise RuntimeError(
            f"imaging metadata extraction completed with exit code {exit_code}"
        )

    with output.open("r", encoding="utf-8") as manifest:
        record_count = sum(1 for line in manifest if line.strip())
    return {
        "output_path": str(output),
        "record_count": record_count,
        "hostname": socket.gethostname(),
    }
