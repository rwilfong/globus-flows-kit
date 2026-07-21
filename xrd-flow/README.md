# Generic XRD Flow

This directory contains a minimal Globus Flow that stages an X-ray diffraction
(XRD) scan on a machine with Globus Compute, analyzes the scan, and writes a
JSON result beside the staged input.

The example is intentionally small. Its analysis function uses only the Python
standard library and illustrates the mechanics of combining Globus Transfer,
Globus Compute, and Globus Flows.

## Workflow

The deployed Flow has two states:

1. `StageInputFile` transfers one CSV scan from the source collection to the
   destination collection.
2. `AnalyzeXRDScan` invokes a registered Compute function using a
   worker-visible input path and writes the analysis to a worker-visible output
   path.

The Compute function reads `two_theta` and `intensity` columns, finds local
maxima above 25% of the scan's maximum intensity, and returns summary
statistics and peak positions.

## Files

- `01_generate_sample_data.py` - generates a deterministic synthetic XRD scan.
- `02_register_compute_function.py` - defines and registers the analysis
  function.
- `03_test_registered_function.py` - directly submits the registered function
  to a Compute endpoint.
- `test_compute.py` - submits a tiny connectivity test to a Compute endpoint.
- `transfer_compute_flow.json` - two-state Transfer and Compute Flow
  definition.
- `transfer_compute_input_schema.json` - schema for Flow input documents.
- `transfer_compute_input.json` - example input containing site-specific IDs
  and paths that must be replaced.

## Prerequisites

- Python 3.10 or newer.
- A source Globus collection containing the input CSV.
- A destination Globus collection whose storage is mounted on, or otherwise
  visible to, the Compute worker.
- A running Globus Compute endpoint on that worker.
- Permission to deploy and start Globus Flows.

Create a local environment from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
globus login
```

The XRD analysis function itself has no third-party worker dependencies.

## Generate a sample scan

Run the generator from the directory where the CSV should be created:

```bash
cd xrd-flow
python 01_generate_sample_data.py
```

This creates `xrd_scan_001.csv` with approximately 1,400 measurements from 10
to 80 degrees 2-theta. The random generator uses a fixed seed, so repeated runs
produce the same scan. Its three simulated peaks are centered near 28.4, 47.3,
and 56.1 degrees.

The CSV format is:

```csv
two_theta,intensity
10.0,21.39
10.05,15.25
```

Move or generate this file beneath a path exposed by the source collection,
then update the source path in `transfer_compute_input.json`.

## Verify the Compute endpoint

Edit `ENDPOINT_ID` in `test_compute.py`, then run:

```bash
python xrd-flow/test_compute.py
```

A successful response reports the worker hostname and process ID and returns
`42` as the output. This confirms task submission but does not test storage
visibility.

## Register the analysis function

Register `analyze_xrd_scan`:

```bash
python xrd-flow/02_register_compute_function.py
```

The command prints a function UUID:

```text
Registered function_id: 00000000-0000-4000-8000-000000000000
```

Copy that UUID into `input.function_id` in
`transfer_compute_input.json`. Treat the IDs checked into the example files as
site-specific examples, not portable defaults.

## Test the registered function directly

Before deploying the Flow, edit these constants in
`03_test_registered_function.py`:

- `ENDPOINT_ID` - the destination Compute endpoint UUID.
- `FUNCTION_ID` - the newly registered analysis function UUID.
- `FILE_PATH` - an input path visible inside the Compute worker environment.
- The `output_path` value - a writable worker-visible result path.

Then run:

```bash
python xrd-flow/03_test_registered_function.py
```

This test bypasses Globus Transfer. The input file must already exist at the
configured worker path.

## Configure the Flow input

Copy the example before editing it:

```bash
cp xrd-flow/transfer_compute_input.json xrd-flow/local_input.json
```

Replace every collection ID, endpoint ID, function ID, and personal filesystem
path in `local_input.json`.

The document has this structure:

```json
{
  "input": {
    "source": {
      "collection_id": "<source-collection-uuid>",
      "path": "/collection/path/xrd_scan_001.csv"
    },
    "destination": {
      "collection_id": "<destination-collection-uuid>",
      "input_transfer_path": "/collection/path/work/xrd_scan_001.csv",
      "input_filesystem_path": "/worker/path/work/xrd_scan_001.csv",
      "output_transfer_path": "/collection/path/work/xrd_scan_001_results.json",
      "output_filesystem_path": "/worker/path/work/xrd_scan_001_results.json"
    },
    "compute_endpoint_id": "<compute-endpoint-uuid>",
    "function_id": "<registered-function-uuid>"
  }
}
```

### Transfer paths versus filesystem paths

The destination path appears in two namespaces:

- `input_transfer_path` is interpreted by the destination Globus collection.
- `input_filesystem_path` is interpreted by Python on the Compute worker.

Both values must resolve to the same physical file. They may be identical, but
storage-gateway mappings and container mounts often make them different. The
same distinction applies to the output paths.

`output_transfer_path` is required by the current input schema, but the current
Flow definition does not use it. The analysis writes directly to
`output_filesystem_path`; no final transfer state publishes the result to a
second collection.

## Deploy the Flow

From the repository root, create the Flow with its input schema:

```bash
globus flows create \
  "XRD transfer and compute" \
  xrd-flow/transfer_compute_flow.json \
  --input-schema xrd-flow/transfer_compute_input_schema.json \
  --subtitle "Stage and analyze an XRD scan" \
  --description "Transfers one XRD CSV to a Compute-visible destination and writes a JSON peak-analysis result." \
  --subscription-id <subscription-uuid> \
  --format json
```

Save the Flow UUID returned by the command.

## Start a run

Start the deployed Flow with the configured input document:

```bash
globus flows start <flow-uuid> \
  --input file:xrd-flow/local_input.json \
  --label "Analyze xrd_scan_001.csv" \
  --format json
```

Use the returned run UUID to inspect progress:

```bash
globus flows run show <run-uuid>
```

The Flow finishes when the Compute action completes. Transfer failures and
Compute failures propagate as failed runs; the current definition does not add
custom `Catch` states.

## Result format

The Compute function writes JSON similar to:

```json
{
  "input_file": "/worker/path/work/xrd_scan_001.csv",
  "num_points": 1401,
  "max_intensity": 965.02,
  "mean_intensity": 30.89,
  "num_peaks": 3,
  "peak_positions_2theta": [
    28.4,
    47.3,
    56.1
  ],
  "worker_os": "Linux-..."
}
```

Exact intensity statistics and detected peak count should be read from the
actual result rather than assumed from this illustrative document.

The function first writes `<output_path>.tmp` and atomically replaces the final
output file, avoiding a partially written JSON result.

## Troubleshooting

### The transfer succeeds but Compute cannot find the file

Compare `input_transfer_path` with `input_filesystem_path`. Confirm the
destination collection's storage mapping and any container bind mounts used by
the Compute endpoint.

### The Compute endpoint is offline

Start the endpoint using its deployment's normal process, then run
`test_compute.py` again. Also confirm that the endpoint UUID in the Flow input
matches the endpoint being tested.

### The output directory does not exist

The function creates the immediate output directory automatically when the
worker account has permission to create it. Parent storage and mount points
must already be available and writable.

### No intensity data found

Verify that the CSV contains a header followed by data rows. The first two
columns must be numeric `two_theta` and `intensity` values.

### Too many peaks are detected

This example uses a deliberately simple local-maximum detector. Noise near a
broad peak may produce multiple detections. For scientific analysis, replace
the example algorithm with a validated peak-finding method and record the
processing parameters in the result.

## Current limitations

- Only one CSV file is transferred and analyzed per run.
- The CSV column order is fixed and rows are not independently validated.
- The peak detector is demonstrative, not a scientific analysis pipeline.
- The output is not transferred to another collection after Compute finishes.
- The Flow has no custom retry policy, cleanup step, or named failure states.
- Example UUIDs and `/home/rwilfong/...` paths must be replaced before use.
