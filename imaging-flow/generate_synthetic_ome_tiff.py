#!/usr/bin/env python3
"""Generate a small, deterministic OME-TIFF for imaging-flow smoke tests."""

from __future__ import annotations

import argparse
from pathlib import Path


CHANNELS = (
    {
        "name": "DAPI",
        "excitation_wavelength_nm": 405.0,
        "emission_wavelength_nm": 461.0,
    },
    {
        "name": "GFP",
        "excitation_wavelength_nm": 488.0,
        "emission_wavelength_nm": 525.0,
    },
)


def synthetic_image(width: int, height: int, z_slices: int):
    """Return deterministic uint16 image data with ZCYX axis order."""
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "synthetic OME-TIFF generation requires numpy"
        ) from exc

    z, channel, y, x = np.indices(
        (z_slices, len(CHANNELS), height, width), dtype=np.uint32
    )
    # Different gradients in each dimension make axis-order mistakes visible.
    return ((x * 17 + y * 31 + z * 521 + channel * 1301) % 4096).astype(
        np.uint16
    )


def write_ome_tiff(
    output: Path,
    *,
    width: int = 64,
    height: int = 48,
    z_slices: int = 3,
) -> Path:
    """Write a two-channel OME-TIFF and return its resolved path."""
    if min(width, height, z_slices) < 1:
        raise ValueError("width, height, and z_slices must all be positive")

    try:
        import tifffile
    except ImportError as exc:
        raise RuntimeError(
            "synthetic OME-TIFF generation requires tifffile"
        ) from exc

    target = output.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    data = synthetic_image(width, height, z_slices)
    channel_metadata = {
        "Name": [channel["name"] for channel in CHANNELS],
        "AcquisitionMode": [
            "LaserScanningConfocalMicroscopy" for _ in CHANNELS
        ],
        "ExcitationWavelength": [
            channel["excitation_wavelength_nm"] for channel in CHANNELS
        ],
        "ExcitationWavelengthUnit": ["nm" for _ in CHANNELS],
        "EmissionWavelength": [
            channel["emission_wavelength_nm"] for channel in CHANNELS
        ],
        "EmissionWavelengthUnit": ["nm" for _ in CHANNELS],
    }
    tifffile.imwrite(
        target,
        data,
        ome=True,
        photometric="minisblack",
        metadata={
            "axes": "ZCYX",
            "Name": "Synthetic two-channel z-stack",
            "AcquisitionDate": "2026-01-15T14:30:00-05:00",
            "PhysicalSizeX": 0.108,
            "PhysicalSizeXUnit": "µm",
            "PhysicalSizeY": 0.108,
            "PhysicalSizeYUnit": "µm",
            "PhysicalSizeZ": 0.5,
            "PhysicalSizeZUnit": "µm",
            "SignificantBits": 12,
            "Channel": channel_metadata,
        },
    )
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="output .ome.tif or .ome.tiff path")
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=48)
    parser.add_argument("--z-slices", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target = write_ome_tiff(
        args.output,
        width=args.width,
        height=args.height,
        z_slices=args.z_slices,
    )
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
