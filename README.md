# Globus Flows Kit

This repository contains example Globus Flows that combine Globus Transfer
with Globus Compute for research-data processing.

## Prerequisites

- Python 3.10 or newer.
- Access to the Globus collections used by a flow.
- A running Globus Compute endpoint with access to the destination filesystem.
- Permission to register Compute functions and deploy or start Globus Flows.

The paths presented through a Globus collection may differ from the local
filesystem paths seen by a Compute worker. Each flow input must map those paths
to the same physical data.

Install the shared command-line and Python dependencies in a virtual
environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
globus login
```

[`requirements.txt`](requirements.txt) installs the Globus CLI, Globus Compute
SDK, and the ND2, CZI, TIFF, NumPy, and synthetic OME-TIFF dependencies used by
the examples. Imaging libraries must also be installed in the Compute worker
environment; registering a function does not install its third-party runtime
dependencies.

## Included flows

### [XRD flow](xrd-flow/README.md)

A compact transfer-and-analysis example for a CSV X-ray diffraction scan:

1. Transfer one scan from a source collection to Compute-visible storage.
2. Run a registered Compute function that detects peaks and calculates summary
   statistics.
3. Write the JSON analysis result to the destination filesystem.

The folder includes a deterministic sample-data generator, endpoint and
function tests, a Flow definition, an input schema, and a sample input.

### [Imaging flow](imaging-flow/README.md)

A larger microscopy ingest, delivery, sharing, and archival workflow:

1. Validate and transfer a PI imaging directory to Bell staging storage.
2. Extract ND2, CZI, TIFF, or OME-TIFF metadata into a JSON Lines manifest.
3. Package the staged PI directory and create a SHA-256 report.
4. Deliver the package to Data Depot.
5. Create or reuse a guest collection and grant recipient access.
6. Archive the package and report to tape.

The folder also includes Compute-function registration scripts, an input
builder and launcher, and a synthetic OME-TIFF generator for local smoke tests.

See each folder's README for endpoint configuration, path requirements,
registration, deployment, and run commands.
