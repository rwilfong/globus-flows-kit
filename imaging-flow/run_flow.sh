globus flows create \
  "Imaging ingest, delivery, and archive" \
  flow_definition.json \
  --input-schema input_schema.json \
  --subtitle "Transfer imaging data to Bell, extract metadata, package, share, and archive." \
  --description "Moves PI imaging data from a GCP collection to HPC, runs Globus Compute metadata extraction, creates a tar package, delivers it to data storage, grants guest access, and archives it to tape." \
  --format json \
  --subscription-id {subscription ID}