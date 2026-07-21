"""
Registers the "analyze_xrd_scan" function with Globus Compute

Compute func: 9bb612a8-d807-471b-8e1f-c008970aa7f3
"""
from globus_compute_sdk import Client


def analyze_xrd_scan(file_path, output_path):
    import csv
    import json
    import os
    import platform
    import time

    time.sleep(15)

    two_theta = []
    intensity = []

    with open(file_path, newline="", encoding="utf-8") as infile:
        reader = csv.reader(infile)
        next(reader)

        for row in reader:
            two_theta.append(float(row[0]))
            intensity.append(float(row[1]))

    if not intensity:
        raise ValueError(f"No intensity data found in {file_path}")

    threshold = max(intensity) * 0.25
    peaks = []

    for i in range(1, len(intensity) - 1):
        if (
            intensity[i] > threshold
            and intensity[i] > intensity[i - 1]
            and intensity[i] > intensity[i + 1]
        ):
            peaks.append(round(two_theta[i], 2))

    result = {
        "input_file": file_path,
        "num_points": len(intensity),
        "max_intensity": round(max(intensity), 2),
        "mean_intensity": round(sum(intensity) / len(intensity), 2),
        "num_peaks": len(peaks),
        "peak_positions_2theta": peaks,
        "worker_os": platform.platform(),
    }

    output_directory = os.path.dirname(output_path)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)

    temporary_path = f"{output_path}.tmp"

    with open(temporary_path, "w", encoding="utf-8") as outfile:
        json.dump(result, outfile, indent=2)
        outfile.write("\n")

    # Avoid leaving a partially written result at output_path.
    os.replace(temporary_path, output_path)

    return {
        "result": result,
        "output_path": output_path,
    }


if __name__ == "__main__":
    gcc = Client()
    function_id = gcc.register_function(analyze_xrd_scan)
    print("Registered function_id:", function_id)