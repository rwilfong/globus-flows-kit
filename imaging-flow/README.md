# Imaging Flow

This directory contains a Globus Flow for moving microscopy data from a source
collection to Bell, extracting discovery metadata with Globus Compute,
packaging the PI directory, delivering the package to Data Depot, sharing it
through a guest collection, and archiving it to tape.

The metadata extractor supports ND2, CZI, TIFF, and OME-TIFF files. It writes
one compact JSON object per image to a JSON Lines (`.jsonl`) manifest.

## Workflow

A successful run performs these operations in order:

1. Stat the source path.
2. Transfer the source data to Bell staging storage.
3. Run the imaging metadata extractor on a Globus Compute endpoint.
4. Create a tar archive and SHA-256 package report.
5. Transfer both package files to Data Depot.
6. Create or reuse a Data Depot guest collection.
7. Grant the configured Globus identity access to that collection.
8. Transfer the package and report to tape.

Each external action has an explicit failure state in
[`flow_definition.json`](flow_definition.json).

## Files

- `flow_definition.json` - Globus Flow state-machine definition.
- `input_schema.json` - schema for flow-run input documents.
- `run_flow.py` - builds a run input document and optionally starts a deployed
  flow.
- `run_flow.sh` - deployment command template.
- `imaging_metadata.py` - standalone metadata extraction CLI.
- `imaging_compute_function.py` - Compute wrapper around the extractor.
- `register_imaging_function.py` - bundles and registers the metadata function.
- `package_function.py` - creates a tar package and checksum report.
- `register_package_function.py` - registers the packaging function.
- `generate_synthetic_ome_tiff.py` - creates a small OME-TIFF for smoke tests.

## Prerequisites

- Python 3.10 or newer.
- Access to a Globus subscription that can deploy and run Flows.
- A configured Globus Compute endpoint on Bell.
- Source, Bell, Data Depot mapped, and tape collections accessible to the run
  owner.
- A Data Depot GCSv5 POSIX storage gateway capable of hosting guest
  collections.

Create a local environment from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
globus login
```

The Compute worker environment also needs `nd2`, `czifile`, and `tifffile`
installed. Registering a function bundles the project source, but it does not
install those third-party libraries on the worker.

## Expected source layout

The extractor recognizes configured instrument directories and PI directories
with exactly three underscore-separated fields:

```text
<instrument-key>/
└── <last-name>_<first-name>_<username>/
    ├── image.ome.tiff
    └── <student-or-project>/
        └── image.nd2
```

For example:

```text
nikon_a1rsi/Doe_Jane_jdoe/project-a/sample.ome.tiff
```

The built-in instrument keys are:

- `nikon_a1rsi`
- `zeiss_lsm_880_upright`
- `nikon_a1r-mp`
- `nikon_intravital`

Aliases may be extended with a JSON file containing `instruments` and `people`
objects. Pass that file to `imaging_metadata.py` with `--aliases`. For a Flow
run, set `metadata.aliases_path` to a path visible on the Compute worker.

The `--path-layout` option controls how the directory after the PI is
interpreted:

- `auto` treats a known person alias as an operator and other names as project
  paths.
- `pi-student` always treats the directory after the PI as the operator.
- `pi-only` treats every directory after the PI as part of the project path.

## Local OME-TIFF smoke test

Generate a deterministic two-channel OME-TIFF in a valid directory layout:

```bash
python imaging-flow/generate_synthetic_ome_tiff.py \
  /tmp/imaging-flow-test/nikon_a1rsi/Doe_Jane_jdoe/demo/synthetic.ome.tiff
```

Run the extractor against that instrument directory:

```bash
python imaging-flow/imaging_metadata.py \
  /tmp/imaging-flow-test/nikon_a1rsi \
  --output /tmp/imaging-flow-test/manifest.jsonl \
  --strict
```

The manifest should contain one record with two channels (`DAPI` and `GFP`),
three Z slices, and `OME-TIFF` in `data_types`:

```bash
python -m json.tool --json-lines /tmp/imaging-flow-test/manifest.jsonl
```

## Register the Compute functions

Run registration from the repository root. The metadata function may be shared
with a Globus Group or bound to a high-assurance endpoint:

```bash
python imaging-flow/register_imaging_function.py

# Optional alternatives:
python imaging-flow/register_imaging_function.py --group <group-uuid>
python imaging-flow/register_imaging_function.py --ha-endpoint-id <endpoint-uuid>
```

Register the packaging function:

```bash
python imaging-flow/register_package_function.py
```

Record both returned function IDs. Update the metadata `function_id` in
`flow_definition.json`. The packaging function ID is supplied when building a
run input.

Also replace the Compute `endpoint_id` in both `RunMetadataExtraction` and
`CreateTarball` if the checked-in Bell endpoint is not the intended endpoint:

```bash
rg -n 'endpoint_id|function_id' imaging-flow/flow_definition.json
```

## Configure recipients

Before launching a run, replace the placeholder entry in `IDENTITY_MAP` inside
`run_flow.py` with approved recipient information:

```python
IDENTITY_MAP = {
    "Doe_Jane_jdoe": {
        "email": "jane.doe@example.edu",
        "identity_id": "00000000-0000-4000-8000-000000000000",
        "guest_collection_id": "",
    }
}
```

Leave `guest_collection_id` empty to create a PI-specific guest collection.
After the first successful run, store that collection's UUID to reuse it on
later runs. Do not launch with the checked-in brace-delimited placeholder
values; they are nonempty and will be treated as real configuration.

## Deploy the Flow

Edit the subscription placeholder in `run_flow.sh`, then run it from the
`imaging-flow` directory:

```bash
cd imaging-flow
bash run_flow.sh
```

Alternatively, run the equivalent command directly:

```bash
globus flows create \
  "Imaging ingest, delivery, and archive" \
  imaging-flow/flow_definition.json \
  --input-schema imaging-flow/input_schema.json \
  --subtitle "Transfer imaging data to Bell, extract metadata, package, share, and archive." \
  --description "Moves PI imaging data from a GCP collection to HPC, packages and shares it, and archives it to tape." \
  --subscription-id <subscription-uuid> \
  --format json
```

Save the deployed Flow UUID from the response.

## Build an input document

The following command writes `flow_input.json` without starting the Flow:

```bash
python imaging-flow/run_flow.py \
  --pi-directory Doe_Jane_jdoe \
  --source-collection-id <source-collection-uuid> \
  --source-path /source/path/Doe_Jane_jdoe/ \
  --instrument nikon_a1rsi \
  --bell-collection-id <bell-collection-uuid> \
  --bell-transfer-root /bell/staging/imaging \
  --bell-local-root /worker-visible/bell/staging/imaging \
  --package-function-id <package-function-uuid> \
  --depot-collection-id <depot-mapped-collection-uuid> \
  --depot-root /depot/imaging \
  --tape-collection-id <tape-collection-uuid> \
  --tape-root /archive/imaging \
  --fortress-root /published/imaging \
  --output flow_input.json
```

Review the generated document carefully. Transfer paths are collection-visible
paths, while `bell.local_*` values must be filesystem paths visible to the
Compute worker.

### Bell path invariant

After the source transfer, the worker-visible data must exist at:

```text
<bell-local-root>/<pi-directory>/<run-timestamp>/input/
└── <instrument>/
    └── <pi-directory>/
        └── <image files>
```

`run_flow.py` currently sends the transfer to the instrument directory while
the metadata and packaging steps expect the PI directory beneath it. Confirm
the resulting directory behavior on the selected collections before a
production run. If the transfer maps the source directory contents directly
onto the destination, include `pi_directory` in the destination path in
`build_input`.

## Start a run

Add `--flow-id` to build the input and immediately start the deployed Flow:

```bash
python imaging-flow/run_flow.py \
  --flow-id <flow-uuid> \
  --pi-directory Doe_Jane_jdoe \
  --source-collection-id <source-collection-uuid> \
  --source-path /source/path/Doe_Jane_jdoe/ \
  --instrument nikon_a1rsi \
  --bell-collection-id <bell-collection-uuid> \
  --bell-transfer-root /bell/staging/imaging \
  --bell-local-root /worker-visible/bell/staging/imaging \
  --package-function-id <package-function-uuid> \
  --depot-collection-id <depot-mapped-collection-uuid> \
  --depot-root /depot/imaging \
  --tape-collection-id <tape-collection-uuid> \
  --tape-root /archive/imaging
```

Useful optional arguments are:

- `--path-layout auto|pi-student|pi-only`
- `--overwrite-policy fail|reuse|replace`
- `--non-strict` to continue after unreadable image files
- `--fortress-root <path>` to control manifest publication paths
- `--output <file>` to select the generated input-document location

Every run includes a UTC timestamp in its staging and package names. As a
result, collisions are uncommon unless the same input document is submitted
more than once.

## Outputs

The Bell staging area contains:

- `imaging_metadata.jsonl` inside the staged PI directory.
- `<pi>__<timestamp>.tar` under the run's `packages` directory.
- `<pi>__<timestamp>.tar.package.json` containing the archive size, SHA-256,
  source-file count, creation time, and worker hostname.

The tar file and package report are transferred to both Data Depot and tape.
The metadata manifest is included in the PI tar archive.

## Troubleshooting

### No configured instrument directories found

The extractor root must either be one built-in instrument directory or contain
one as a direct child. Check the spelling of `--instrument` and the Bell
filesystem layout.

### Zero supported files

Confirm that files end in `.nd2`, `.czi`, `.tif`, or `.tiff` and that the PI
directory has exactly three underscore-separated components.

### Import errors on Compute

Install the imaging dependencies in the Compute worker environment, not only
on the machine used to register the function.

### Packaging says the PI folder is missing

Inspect the actual destination produced by the source transfer and compare it
with `bell.local_pi_folder_path` in the generated input document. See the Bell
path invariant above.

### Guest collection creation fails

Verify that the destination is a subscribed GCSv5 mapped collection backed by
a POSIX storage gateway and that the run owner may create guest collections at
the configured base path.

### A package already exists

Choose the desired `--overwrite-policy`:

- `fail` stops without overwriting.
- `reuse` keeps the existing tarball.
- `replace` creates and transfers a replacement.

Use `reuse` only after independently confirming that the existing package
belongs to the same source dataset.
