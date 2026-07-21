"""Register create_imaging_tarball as self-contained Globus Compute source."""

from __future__ import annotations

from pathlib import Path

from globus_compute_sdk import Client


HERE = Path(__file__).resolve().parent
SOURCE_FILE = HERE / "package_function.py"
FUNCTION_NAME = "create_imaging_tarball"


def main():
    source = SOURCE_FILE.read_text(encoding="utf-8")

    function_id = Client().register_source_code(
        source,
        function_name=FUNCTION_NAME,
        description=(
            "Create a deterministic tar archive of a PI imaging directory "
            "and write a SHA-256 package result."
        ),
    )

    print(function_id)


if __name__ == "__main__":
    main()