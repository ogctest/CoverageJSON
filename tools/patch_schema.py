# Patches properties of an existing bundled schema (e.g. set or drop $id).
#
# Adapted from https://github.com/covjson/covjson-validator/blob/main/tools/patch_schema.py

import argparse
import json
import copy


def patch_schema(schema, set_id=None, drop_id=False):
    """Patch properties of the given schema."""
    schema = copy.deepcopy(schema)

    if drop_id:
        schema.pop("$id", None)
    elif set_id:
        schema["$id"] = set_id

    return schema


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Patch properties of a JSON Schema file")
    parser.add_argument("input_path")
    parser.add_argument("--out", dest="output_path",
                        help="Output file (default: overwrite input)")
    parser.add_argument("--set-id", type=str, help="Set $id property value")
    parser.add_argument("--drop-id", action="store_true", help="Drop $id property")
    args = parser.parse_args()
    if args.output_path is None:
        args.output_path = args.input_path

    with open(args.input_path) as f:
        schema = json.load(f)

    schema = patch_schema(schema, args.set_id, args.drop_id)

    with open(args.output_path, "w") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")

    print(f"Patched schema written to {args.output_path}")
