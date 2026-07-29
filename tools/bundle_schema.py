# Bundles all referenced schema fragments into a single root schema.
# Adapted from https://github.com/covjson/covjson-validator/blob/main/tools/bundle_schema.py
#
# Follows the method described in:
# https://datatracker.ietf.org/doc/html/draft-bhutton-json-schema-00#section-9.3.1

import argparse
import json
import copy
import os


def walk_dict(obj, match_key, fn):
    """Recursively walk a dict and call fn(obj, key, value) for every match_key found."""
    for key, value in list(obj.items()):
        if key == match_key:
            fn(obj, key, value)
        elif isinstance(value, dict):
            walk_dict(value, match_key, fn)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    walk_dict(item, match_key, fn)


def create_schema_store(schema_dir):
    """Load all JSON schema fragments from a directory into a dict keyed by $id."""
    schema_store = {}
    for entry in os.scandir(schema_dir):
        if entry.is_file() and entry.path.endswith(".json"):
            with open(entry.path) as f:
                schema = json.load(f)
            if "$id" in schema:
                schema_store[schema["$id"]] = schema
    return schema_store


def bundle_schema(schema_store, root_schema_id):
    """Bundle all referenced schemas into the root schema using $defs."""
    root_schema = copy.deepcopy(schema_store[root_schema_id])

    # Collect all referenced schema IDs recursively
    refs = set()

    def record_ref(obj, key, value):
        if value in schema_store:
            refs.add(value)

    done = set()
    todo = {root_schema_id}
    while todo:
        for schema_id in todo:
            walk_dict(schema_store[schema_id], "$ref", record_ref)
            done.add(schema_id)
        todo = refs - done

    # Remove self-reference if present
    refs.discard(root_schema_id)

    # Embed referenced schemas under $defs
    if refs:
        defs = root_schema.setdefault("$defs", {})
        for schema_id in sorted(refs):
            defs[schema_id] = copy.deepcopy(schema_store[schema_id])

    return root_schema


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bundle CoverageJSON schema fragments into a single file")
    parser.add_argument("--schema-dir", default="standard/schema",
                        help="Directory containing schema fragment JSON files")
    parser.add_argument("--root", default="/schemas/coveragejson",
                        help="$id of the root schema fragment")
    parser.add_argument("--out", default="dist/coveragejson.json",
                        help="Output file path")
    args = parser.parse_args()

    store = create_schema_store(args.schema_dir)
    schema = bundle_schema(store, args.root)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")

    print(f"Bundled schema written to {args.out}")
