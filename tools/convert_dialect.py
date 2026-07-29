# Converts a bundled schema to a specific JSON Schema dialect.
#
# Supported target dialects:
#   - draft-07  (http://json-schema.org/draft-07/schema)
#   - 2019-09   (https://json-schema.org/draft/2019-09/schema)
#   - 2020-12   (https://json-schema.org/draft/2020-12/schema)
#
# The bundled input (from bundle_schema.py) uses $defs and /schemas/... $ref
# style which is native to 2019-09 and 2020-12. For draft-07, additional
# transformations are applied ($defs → definitions, $ref isolation, etc.).

import argparse
import json
import copy
import os

import jsonschema


DIALECTS = {
    "draft-07": "http://json-schema.org/draft-07/schema",
    "2019-09": "https://json-schema.org/draft/2019-09/schema",
    "2020-12": "https://json-schema.org/draft/2020-12/schema",
}


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


def _convert_to_modern(root_schema, dialect_uri):
    """Convert bundled schema to 2019-09 or 2020-12 dialect.

    These dialects natively support $defs and $ref alongside other keywords,
    so the main work is rewriting $ref values from /schemas/... to #/$defs/...
    and setting the $schema declaration.
    """
    out = copy.deepcopy(root_schema)
    out.pop("$schema", None)

    # Reorder so $schema is first
    result = {"$schema": dialect_uri}
    result.update(out)
    out = result

    # Strip $id from embedded $defs entries (they are local definitions now)
    schema_id_prefix = "/schemas/"

    def strip_def_ids(obj, key, value):
        assert key == "$defs"
        cleaned = {}
        for name, schema in value.items():
            if "$id" in schema:
                def_name = schema["$id"]
                if def_name.startswith(schema_id_prefix):
                    def_name = def_name[len(schema_id_prefix):]
                del schema["$id"]
            else:
                def_name = name
            cleaned[def_name] = schema
        obj["$defs"] = dict(sorted(cleaned.items()))

    walk_dict(out, "$defs", strip_def_ids)

    # Collect all definition names for validation
    all_defs = set()
    if "$defs" in out:
        all_defs.update(out["$defs"].keys())

    # Rewrite $ref values from /schemas/... to #/$defs/...
    defs_prefix = "#/$defs/"

    def patch_ref(obj, key, value):
        assert key == "$ref"
        new_value = value.replace("/schemas/", defs_prefix)
        if not new_value.startswith(defs_prefix):
            raise ValueError(f"Invalid $ref value '{value}'")
        def_name = new_value[len(defs_prefix):]
        assert def_name in all_defs, \
            f"$ref '{value}' -> '{def_name}' not in $defs: {sorted(all_defs)}"
        obj[key] = new_value

    walk_dict(out, "$ref", patch_ref)

    return out


def _convert_to_draft07(root_schema):
    """Convert bundled schema to draft-07 dialect.

    Draft-07 differences from modern dialects:
    - Uses "definitions" instead of "$defs"
    - $ref cannot coexist with other keywords (must wrap in allOf)
    - "dependentSchemas" must be renamed to "dependencies"
    """
    out = copy.deepcopy(root_schema)
    out.pop("$schema", None)

    result = {"$schema": DIALECTS["draft-07"]}
    result.update(out)
    out = result

    # Move $defs → definitions
    definitions = {}
    out["definitions"] = definitions
    schema_id_prefix = "/schemas/"

    def move_defs(obj, key, value):
        assert key == "$defs"
        for name, schema in value.items():
            if "$id" in schema:
                def_name = schema["$id"]
                if def_name.startswith(schema_id_prefix):
                    def_name = def_name[len(schema_id_prefix):]
                del schema["$id"]
            else:
                def_name = name
            assert def_name not in definitions, \
                f"Duplicate definition '{def_name}'"
            definitions[def_name] = schema
        del obj["$defs"]

    walk_dict(out, "$defs", move_defs)
    out["definitions"] = dict(sorted(definitions.items()))

    # Rewrite $ref to #/definitions/...
    def patch_ref(obj, key, value):
        assert key == "$ref"
        defs_prefix = "#/definitions/"
        new_value = value.replace("/schemas/", defs_prefix)
        new_value = new_value.replace("#/$defs/", defs_prefix)
        if not new_value.startswith(defs_prefix):
            raise ValueError(f"Invalid $ref '{value}'")
        def_name = new_value[len(defs_prefix):]
        assert def_name in definitions, \
            f"$ref '{value}' -> '{def_name}' not in definitions"
        obj[key] = new_value

    walk_dict(out, "$ref", patch_ref)

    # In draft-07, $ref must stand alone — wrap with allOf if siblings exist
    def isolate_ref(obj, key, value):
        assert key == "$ref"
        other_keywords = [
            k for k in obj.keys()
            if k != "$ref" and not k.startswith("$") and k != "definitions"
        ]
        if other_keywords:
            all_of = [
                {"$ref": value},
                {k: obj[k] for k in other_keywords},
            ]
            del obj["$ref"]
            for k in other_keywords:
                del obj[k]
            obj["allOf"] = all_of

    walk_dict(out, "$ref", isolate_ref)

    # Rename dependentSchemas → dependencies
    def patch_dependent_schemas(obj, key, value):
        assert key == "dependentSchemas"
        assert "dependencies" not in obj
        obj["dependencies"] = value
        del obj["dependentSchemas"]

    walk_dict(out, "dependentSchemas", patch_dependent_schemas)

    # Validate against draft-07 meta schema
    jsonschema.Draft7Validator.check_schema(out)

    return out


def convert_dialect(root_schema, dialect):
    """Convert a bundled schema to the specified dialect."""
    if dialect == "draft-07":
        return _convert_to_draft07(root_schema)
    elif dialect in ("2019-09", "2020-12"):
        return _convert_to_modern(root_schema, DIALECTS[dialect])
    else:
        raise ValueError(f"Unsupported dialect '{dialect}'. Choose from: {list(DIALECTS.keys())}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert a bundled JSON Schema to a specific dialect")
    parser.add_argument("input_path", help="Path to bundled schema JSON")
    parser.add_argument("--dialect", required=True, choices=list(DIALECTS.keys()),
                        help="Target JSON Schema dialect")
    parser.add_argument("--out", dest="output_path",
                        help="Output file (default: overwrite input)")
    args = parser.parse_args()
    if args.output_path is None:
        args.output_path = args.input_path

    with open(args.input_path) as f:
        schema = json.load(f)

    schema = convert_dialect(schema, args.dialect)

    os.makedirs(os.path.dirname(args.output_path) or ".", exist_ok=True)
    with open(args.output_path, "w") as f:
        json.dump(schema, f, indent=2)
        f.write("\n")

    print(f"Converted to {args.dialect} -> {args.output_path}")
