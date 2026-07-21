"""Extract ND2, OME-TIFF, and CZI metadata into a Globus manifest JSONL file."""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo


DEFAULT_ALIASES = {
    "instruments": {
        "nikon_a1rsi": "Nikon A1RSi",
        "zeiss_lsm_880_upright": "Zeiss LSM 880 Upright",
        "nikon_a1r-mp": "Nikon A1R-MP",
        "nikon_intravital": "Nikon Intravital"

    }
}
SUPPORTED_SUFFIXES = {".czi", ".nd2", ".tif", ".tiff"}
PI_DIRECTORY_RE = re.compile(r"^[^_]+_[^_]+_[^_]+$")
OBJECTIVE_ALIASES = {
    # NIS-Elements TIFF export replaces the lambda character used by the ND2.
    "Plan Apo ? 100x Oil": "Plan Apo λ 100x Oil",
}


def _clean(value: Any) -> Any:
    """Convert library objects into compact JSON-compatible values."""
    if dataclasses.is_dataclass(value):
        return _clean(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _number(value: str | None, integer: bool = False) -> int | float | None:
    if value in (None, ""):
        return None
    try:
        return int(value) if integer else float(value)
    except ValueError:
        return None


def _iso_datetime(value: str | None, timezone: ZoneInfo) -> str | None:
    if not value:
        return None
    parsed: datetime | None = None
    for fmt in ("%m/%d/%Y  %I:%M:%S %p", "%m/%d/%Y %I:%M:%S %p"):
        try:
            parsed = datetime.strptime(value.strip(), fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.isoformat()


def _local_name(raw: str, aliases: dict[str, str]) -> str:
    if raw in aliases:
        return aliases[raw]
    value = re.sub(r"[_-]+", " ", raw).strip()
    return re.sub(r"\s+", " ", value)


def _person_name(raw: str, aliases: dict[str, str]) -> str:
    """Normalize lastname_firstname_alias while retaining an alias override."""
    if raw in aliases:
        return aliases[raw]
    parts = raw.split("_")
    if len(parts) >= 2 and parts[0] and parts[1]:
        return f"{parts[1]} {parts[0]}"
    return _local_name(raw, aliases)


def _normalize_objective(value: str | None) -> str | None:
    if value is None:
        return None
    return OBJECTIVE_ALIASES.get(value.strip(), value.strip())


def path_metadata(
    file_path: Path,
    instrument_root: Path,
    aliases: dict[str, dict[str, str]],
    path_layout: str = "auto",
) -> dict[str, Any]:
    """Interpret instrument/PI/student/project from a path under an instrument root."""
    relative = file_path.relative_to(instrument_root)
    folders = relative.parts[:-1]
    pi_raw = folders[0] if folders else None
    people = aliases.get("people", {})
    remainder = folders[1:]
    has_operator = bool(remainder) and (
        path_layout == "pi-student"
        or (path_layout == "auto" and remainder[0] in people)
    )
    operator_raw = remainder[0] if has_operator else None
    project_parts = remainder[1:] if has_operator else remainder
    pi = _person_name(pi_raw, people) if pi_raw else None
    operator = _person_name(operator_raw, people) if operator_raw else pi
    return {
        "instrument": _local_name(
            instrument_root.name, aliases.get("instruments", {})
        ),
        "pi": pi,
        "operator": operator,
        "project": "/".join(project_parts) or None,
    }


def _common_record(
    file_path: Path,
    instrument_root: Path,
    fortress_root: str,
    aliases: dict[str, dict[str, str]],
    path_layout: str,
) -> dict[str, Any]:
    relative = PurePosixPath(instrument_root.name) / PurePosixPath(
        *file_path.relative_to(instrument_root).parts
    )
    fortress_path = str(PurePosixPath("/") / fortress_root.strip("/") / relative)
    return {
        "fortress_absolute_path": fortress_path,
        "source_path": str(file_path.resolve()),
        "data_type": "imaging",
        **path_metadata(file_path, instrument_root, aliases, path_layout),
        "sample_name": file_path.name,
        "file_size_bytes": file_path.stat().st_size,
        "file_format": (
            "TIFF" if file_path.suffix.lower() in {".tif", ".tiff"}
            else file_path.suffix.lstrip(".").upper()
        ),
    }


def extract_nd2(file_path: Path, timezone: ZoneInfo) -> dict[str, Any]:
    try:
        import nd2
    except ImportError as exc:
        raise RuntimeError("ND2 support requires: python3 -m pip install -r requirements.txt") from exc

    with nd2.ND2File(file_path) as image:
        metadata = _clean(image.metadata)
        text_info = _clean(image.text_info or {})
        sizes = dict(image.sizes)
        channels = metadata.get("channels", [])
        channel_records: list[dict[str, Any]] = []
        for item in channels:
            channel = item.get("channel", {})
            microscope = item.get("microscope", {})
            channel_records.append(
                {key: value for key, value in {
                    "name": channel.get("name"),
                    "excitation_wavelength_nm": channel.get("excitationLambdaNm"),
                    "emission_wavelength_nm": channel.get("emissionLambdaNm"),
                    "color_rgba": channel.get("color"),
                    "modality": microscope.get("modalityFlags"),
                }.items() if value is not None}
            )

        first = channels[0] if channels else {}
        microscope = first.get("microscope", {})
        volume = first.get("volume", {})
        modalities = list(dict.fromkeys(
            modality
            for item in channels
            for modality in (item.get("microscope", {}).get("modalityFlags") or [])
        ))
        calibration = volume.get("axesCalibration") or []
        custom = _clean(image.custom_data or {})
        camera = (
            custom.get("GrabberCameraSettingsV1_0", {})
            .get("GrabberCameraSettings", {})
        )
        properties = camera.get("PropertiesQuality", {})
        laser_power = {
            f"CH{i}": properties.get(f"CH{i}LaserPower")
            for i in range(1, 5)
            if properties.get(f"CH{i}LaserPower") is not None
        }
        pmt_voltage = {
            f"CH{i}": properties.get(f"CH{i}PMTHighVoltage")
            for i in range(1, 5)
            if properties.get(f"CH{i}PMTHighVoltage") is not None
        }
        objective = _normalize_objective(
            microscope.get("objectiveName") or text_info.get("optics")
        )
        method_parts = [*modalities]
        if objective:
            method_parts.append(objective)

        result = {
            "acquisition_date": _iso_datetime(text_info.get("date"), timezone),
            "instrument_name": text_info.get("capturing", "").splitlines()[0] or None,
            "instrument_model": camera.get("CameraFamilyName"),
            "instrument_method": "; ".join(method_parts) or None,
            "data_types": list(dict.fromkeys(["ND2", "microscopy", *modalities])),
            "dimensions": sizes,
            "image_width_pixels": sizes.get("X"),
            "image_height_pixels": sizes.get("Y"),
            "channel_count": sizes.get("C", len(channel_records)),
            "z_slices": sizes.get("Z", 1),
            "timepoints": sizes.get("T", 1),
            "positions": sizes.get("P", sizes.get("V", 1)),
            "bit_depth": volume.get("bitsPerComponentInMemory"),
            "significant_bits": volume.get("bitsPerComponentSignificant"),
            "pixel_size_x_um": calibration[0] if len(calibration) > 0 else None,
            "pixel_size_y_um": calibration[1] if len(calibration) > 1 else None,
            "pixel_size_z_um": calibration[2] if len(calibration) > 2 and sizes.get("Z") else None,
            "channel_names": [c["name"] for c in channel_records if c.get("name")],
            "channels": channel_records,
            "objective": objective,
            "objective_magnification": microscope.get("objectiveMagnification"),
            "objective_numerical_aperture": microscope.get("objectiveNumericalAperture"),
            "zoom_magnification": microscope.get("zoomMagnification"),
            "immersion_refractive_index": microscope.get("immersionRefractiveIndex"),
            "pinhole_diameter_um": microscope.get("pinholeDiameterUm"),
            "modality": modalities,
            "laser_power_percent": laser_power or None,
            "pmt_voltage": pmt_voltage or None,
        }
        return {k: v for k, v in result.items() if v is not None}


def _elements(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == local_name]


def _child_text(node: ET.Element, local_name: str) -> str | None:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1] == local_name:
            value = (child.text or "").strip()
            if value:
                return value
    return None


def _first_text(root: ET.Element, local_name: str) -> str | None:
    nodes = _elements(root, local_name)
    for node in nodes:
        value = (node.text or "").strip()
        if value:
            return value
    return None


def extract_czi_xml(xml: str, timezone: ZoneInfo) -> dict[str, Any]:
    """Extract discovery metadata from Zeiss CZI XML."""
    root = ET.fromstring(xml)
    dimensions = {}
    for axis in ("C", "T", "X", "Y", "Z", "S"):
        value = _number(_first_text(root, f"Size{axis}"), integer=True)
        if value is not None:
            dimensions[axis] = value
    for axis in ("C", "T", "Z", "S"):
        dimensions.setdefault(axis, 1)

    channel_records = []
    for node in _elements(root, "Channel"):
        excitation = _child_text(node, "ExcitationWavelength")
        if excitation is None:
            continue
        channel_records.append({key: value for key, value in {
            "name": node.attrib.get("Name"),
            "acquisition_mode": _child_text(node, "AcquisitionMode"),
            "excitation_wavelength_nm": _number(excitation),
            "emission_wavelength_nm": _number(_child_text(node, "EmissionWavelength")),
            "pixel_time_seconds": _number(_child_text(node, "PixelTime")),
        }.items() if value is not None})

    objective_nodes = [
        node for node in _elements(root, "Objective") if _child_text(node, "LensNA")
    ]
    objective_node = objective_nodes[0] if objective_nodes else None
    objective = _child_text(objective_node, "Model") if objective_node is not None else None
    if objective is None:
        objective_values = [
            (node.text or "").strip() for node in _elements(root, "Objective")
            if (node.text or "").strip()
        ]
        objective = objective_values[-1] if objective_values else None
    objective = _normalize_objective(objective)

    modes = list(dict.fromkeys(
        value for value in (
            *[item.get("acquisition_mode") for item in channel_records],
            *[(node.text or "").strip() for node in _elements(root, "AcquisitionMode")],
        ) if value
    ))
    lasers = []
    for node in _elements(root, "Laser"):
        name = _child_text(node, "LaserName")
        power = _number(_child_text(node, "LaserPower"))
        if name or power is not None:
            lasers.append({key: value for key, value in {"name": name, "power": power}.items() if value is not None})
    detectors = []
    for node in _elements(root, "Detector"):
        identifier = _child_text(node, "DetectorIdentifier")
        if not identifier:
            continue
        start = _number(_child_text(node, "WavelengthStart"))
        end = _number(_child_text(node, "WavelengthEnd"))
        detectors.append({key: value for key, value in {
            "name": node.attrib.get("Name"),
            "identifier": identifier,
            "wavelength_start_nm": start * 1e9 if start is not None else None,
            "wavelength_end_nm": end * 1e9 if end is not None else None,
        }.items() if value is not None})

    application_nodes = _elements(root, "Application")
    application = application_nodes[0] if application_nodes else None
    position_nodes = _elements(root, "Position")
    position = position_nodes[0].attrib if position_nodes else {}
    method_parts = [*modes]
    if objective:
        method_parts.append(objective)
    bit_depth = _number(_first_text(root, "ComponentBitCount"), integer=True)

    def scaling_um(axis: str) -> float | None:
        value = _number(_first_text(root, f"Scaling{axis}"))
        return value * 1e6 if value is not None else None

    application_parts = (
        [_child_text(application, "Name"), _child_text(application, "Version")]
        if application is not None else []
    )
    result = {
        "acquisition_date": _iso_datetime(_first_text(root, "CreationDate"), timezone),
        "instrument_name": _first_text(root, "System"),
        "instrument_model": _first_text(root, "System"),
        "instrument_method": "; ".join(method_parts) or None,
        "acq_software_version": " ".join(value for value in application_parts if value) or None,
        "data_types": list(dict.fromkeys(["CZI", "microscopy", *modes])),
        "dimensions": dimensions,
        "image_width_pixels": dimensions.get("X"),
        "image_height_pixels": dimensions.get("Y"),
        "channel_count": dimensions.get("C", len(channel_records)),
        "z_slices": dimensions.get("Z", 1),
        "timepoints": dimensions.get("T", 1),
        "positions": dimensions.get("S", 1),
        "pixel_type": _first_text(root, "PixelType"),
        "bit_depth": bit_depth,
        "pixel_size_x_um": scaling_um("X"),
        "pixel_size_y_um": scaling_um("Y"),
        "pixel_size_z_um": scaling_um("Z"),
        "channel_names": [item["name"] for item in channel_records if item.get("name")],
        "channels": channel_records,
        "objective": objective,
        "objective_magnification": _number(
            _child_text(objective_node, "NominalMagnification") if objective_node is not None else None
        ),
        "objective_numerical_aperture": _number(
            _child_text(objective_node, "LensNA") if objective_node is not None else None
        ),
        "objective_immersion": (
            _child_text(objective_node, "Immersion") if objective_node is not None else None
        ),
        "modality": modes or None,
        "lasers": lasers or None,
        "detectors": detectors or None,
        "stage_position_um": {
            axis.lower(): _number(position.get(axis)) for axis in ("X", "Y", "Z")
            if position.get(axis) is not None
        } or None,
        "operator_from_file": _first_text(root, "UserName"),
    }
    return {key: value for key, value in result.items() if value is not None}


def extract_czi(file_path: Path, timezone: ZoneInfo) -> dict[str, Any]:
    try:
        from czifile import CziFile
    except ImportError as exc:
        raise RuntimeError("CZI support requires: python3 -m pip install -r requirements.txt") from exc
    with CziFile(file_path) as image:
        return extract_czi_xml(image.metadata(), timezone)


def extract_ome_xml(xml: str, timezone: ZoneInfo) -> dict[str, Any]:
    """Extract the discovery-relevant subset of OME-XML."""
    root = ET.fromstring(xml)
    pixels_nodes = _elements(root, "Pixels")
    pixels = pixels_nodes[0].attrib if pixels_nodes else {}
    channel_records = []
    for node in _elements(root, "Channel"):
        attrs = node.attrib
        channel_records.append(
            {key: value for key, value in {
                "name": attrs.get("Name"),
                "acquisition_mode": attrs.get("AcquisitionMode"),
                "excitation_wavelength_nm": _number(attrs.get("ExcitationWavelength")),
                "emission_wavelength_nm": _number(attrs.get("EmissionWavelength")),
                "pinhole_diameter_um": _number(attrs.get("PinholeSize")),
            }.items() if value is not None}
        )
    objective_nodes = [
        node for node in _elements(root, "Objective") if node.attrib.get("Model")
    ]
    objective = objective_nodes[-1].attrib if objective_nodes else {}
    objective_name = _normalize_objective(objective.get("Model"))
    microscope_nodes = _elements(root, "Microscope")
    acquisition_nodes = _elements(root, "AcquisitionDate")
    planes = _elements(root, "Plane")
    first_plane = planes[0].attrib if planes else {}
    modes = list(dict.fromkeys(
        c["acquisition_mode"] for c in channel_records if c.get("acquisition_mode")
    ))
    method_parts = [*modes]
    if objective_name:
        method_parts.append(objective_name)
    dimensions = {
        axis: _number(pixels.get(f"Size{axis}"), integer=True)
        for axis in ("C", "T", "X", "Y", "Z")
        if pixels.get(f"Size{axis}")
    }
    result = {
        "acquisition_date": _iso_datetime(
            acquisition_nodes[0].text if acquisition_nodes else None, timezone
        ),
        "instrument_name": microscope_nodes[-1].attrib.get("Model") if microscope_nodes else None,
        "instrument_method": "; ".join(method_parts) or None,
        "data_types": list(dict.fromkeys(["TIFF", "OME-TIFF", "microscopy", *modes])),
        "dimensions": dimensions,
        "image_width_pixels": dimensions.get("X"),
        "image_height_pixels": dimensions.get("Y"),
        "channel_count": dimensions.get("C", len(channel_records)),
        "z_slices": dimensions.get("Z"),
        "timepoints": dimensions.get("T"),
        "pixel_type": pixels.get("Type"),
        "pixel_size_x_um": _number(pixels.get("PhysicalSizeX")),
        "pixel_size_y_um": _number(pixels.get("PhysicalSizeY")),
        "pixel_size_z_um": _number(pixels.get("PhysicalSizeZ")),
        "channel_names": [c["name"] for c in channel_records if c.get("name")],
        "channels": channel_records,
        "objective": objective_name,
        "objective_magnification": _number(objective.get("NominalMagnification")),
        "objective_numerical_aperture": _number(objective.get("LensNA")),
        "objective_immersion": objective.get("Immersion"),
        "modality": modes or None,
        "stage_position_um": {
            key.removeprefix("Position").lower(): _number(value)
            for key, value in first_plane.items()
            if key in {"PositionX", "PositionY", "PositionZ"}
        } or None,
    }
    return {k: v for k, v in result.items() if v is not None}


def extract_tiff(file_path: Path, timezone: ZoneInfo) -> dict[str, Any]:
    try:
        import tifffile
    except ImportError as exc:
        raise RuntimeError("TIFF support requires: python3 -m pip install -r requirements.txt") from exc

    with tifffile.TiffFile(file_path) as image:
        page = image.pages[0]
        description = page.description or ""
        if description.lstrip().startswith("<?xml") and "<OME" in description:
            result = extract_ome_xml(description, timezone)
        else:
            result = {
                "data_types": ["TIFF", "microscopy"],
                "image_width_pixels": page.imagewidth,
                "image_height_pixels": page.imagelength,
            }
        bits = page.tags.get("BitsPerSample")
        if bits:
            value = bits.value
            result["bit_depth"] = max(value) if isinstance(value, tuple) else value
        result["page_count"] = len(image.pages)
        return result


def extract_file(
    file_path: Path,
    instrument_root: Path,
    fortress_root: str,
    aliases: dict[str, dict[str, str]],
    timezone: ZoneInfo,
    path_layout: str = "auto",
) -> dict[str, Any]:
    record = _common_record(file_path, instrument_root, fortress_root, aliases, path_layout)
    if file_path.suffix.lower() == ".nd2":
        record.update(extract_nd2(file_path, timezone))
    elif file_path.suffix.lower() == ".czi":
        record.update(extract_czi(file_path, timezone))
    else:
        record.update(extract_tiff(file_path, timezone))
    return {k: v for k, v in record.items() if v is not None}


def _matches_path_layout(file_path: Path, instrument_root: Path, path_layout: str) -> bool:
    """Return whether a file has the directories required by the selected layout."""
    relative_parts = file_path.relative_to(instrument_root).parts
    folder_count = len(relative_parts) - 1
    # Every accepted path requires a PI. In pi-student mode the next directory,
    # when present, is the student; a file directly under PI belongs to the PI.
    return folder_count >= 1 and bool(PI_DIRECTORY_RE.fullmatch(relative_parts[0]))


def iter_images(root: Path, path_layout: str | None = None) -> Iterable[Path]:
    pi_roots = sorted(
        (
            path for path in root.iterdir()
            if path.is_dir() and PI_DIRECTORY_RE.fullmatch(path.name)
        ),
        key=lambda path: path.name.casefold(),
    )
    return sorted(
        (
            path
            for pi_root in pi_roots
            for path in pi_root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_SUFFIXES
            and (path_layout is None or _matches_path_layout(path, root, path_layout))
        ),
        key=lambda path: str(path).casefold(),
    )


def _load_aliases(path: Path | None) -> dict[str, dict[str, str]]:
    aliases = {section: dict(values) for section, values in DEFAULT_ALIASES.items()}
    if path:
        supplied = json.loads(path.read_text(encoding="utf-8"))
        for section in ("instruments", "people"):
            aliases[section].update(supplied.get(section, {}))
    return aliases


def instrument_roots(
    root: Path, aliases: dict[str, dict[str, str]]
) -> list[Path]:
    """Find only exact, direct-child instrument keys configured in the aliases."""
    instrument_keys = aliases.get("instruments", {})
    if root.name in instrument_keys:
        return [root]
    return [root / key for key in sorted(instrument_keys) if (root / key).is_dir()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", type=Path,
        help="one configured instrument directory, or a parent containing configured instruments",
    )
    parser.add_argument("--output", "-o", type=Path, help="JSONL output; defaults to stdout")
    parser.add_argument("--fortress-root", default="/", help="destination prefix used in fortress_absolute_path")
    parser.add_argument("--timezone", default="America/Indiana/Indianapolis", help="IANA timezone for naive acquisition timestamps")
    parser.add_argument("--aliases", type=Path, help="optional JSON file extending instrument/person aliases")
    parser.add_argument(
        "--path-layout", choices=("auto", "pi-student", "pi-only"), default="auto",
        help="whether the folder after PI is a student/operator or project (default: recognize aliases)",
    )
    parser.add_argument("--strict", action="store_true", help="stop at the first unreadable file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")
    aliases = _load_aliases(args.aliases)
    roots = instrument_roots(root, aliases)
    if not roots:
        configured = ", ".join(sorted(aliases.get("instruments", {}))) or "none"
        raise SystemExit(
            f"no configured instrument directories found directly under {root}; "
            f"configured keys: {configured}"
        )
    timezone = ZoneInfo(args.timezone)
    output = args.output.open("w", encoding="utf-8") if args.output else sys.stdout
    written = failed = skipped_layout = 0
    try:
        for instrument_root in roots:
            candidates = list(iter_images(instrument_root))
            files = [
                file_path for file_path in candidates
                if _matches_path_layout(file_path, instrument_root, args.path_layout)
            ]
            skipped_layout += len(candidates) - len(files)
            print(
                f"scanning instrument {instrument_root.name}: {len(files)} supported file(s)",
                file=sys.stderr,
            )
            for file_path in files:
                try:
                    record = extract_file(
                        file_path, instrument_root, args.fortress_root,
                        aliases, timezone, args.path_layout,
                    )
                    output.write(
                        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                    )
                    written += 1
                except Exception as exc:
                    failed += 1
                    print(f"warning: {file_path}: {exc}", file=sys.stderr)
                    if args.strict:
                        raise
    finally:
        if output is not sys.stdout:
            output.close()
    print(
        f"wrote {written} record(s); {failed} failed; "
        f"{skipped_layout} supported file(s) skipped by path layout",
        file=sys.stderr,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
