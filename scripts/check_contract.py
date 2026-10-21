"""Strict baseline guard: reject unreviewed changes to existing wire definitions."""
import hashlib
import copy
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from openapi_spec_validator import validate
from cj_api.generated import ProbeResponse, ErrorResponse

ROOT = Path(__file__).resolve().parents[1]

def compatible(old, new):
    # Conservative on purpose: even optional additions require old-client evidence.
    for name, schema in old["components"]["schemas"].items():
        if new["components"]["schemas"].get(name) != schema:
            raise ValueError(f"Existing schema changed: {name}; publish a version and consumer evidence")
    for path, operations in old["paths"].items():
        for method, definition in operations.items():
            if new["paths"].get(path, {}).get(method) != definition:
                raise ValueError(f"Existing operation changed: {method} {path}")

def main():
    spec = json.loads((ROOT / "contracts/api/openapi.json").read_text())
    validate(spec)
    baseline = json.loads((ROOT / "contracts/api/baseline-1.0.0.json").read_text())
    compatible(baseline, spec)
    validators = {}
    for name in ("ProbeResponse", "ErrorResponse"):
        schema = {"$ref": f"#/components/schemas/{name}", "components": spec["components"]}
        validators[name] = Draft202012Validator(schema, format_checker=FormatChecker())
    for path in sorted((ROOT / "contracts/api/examples").glob("*.json")):
        value = json.loads(path.read_text())
        name = "ErrorResponse" if "error" in value else "ProbeResponse"
        validators[name].validate(value)
        (ErrorResponse if name == "ErrorResponse" else ProbeResponse).model_validate(value)
    invalid = json.loads((ROOT / "contracts/api/examples/normal.json").read_text())
    del invalid["request_id"]
    try:
        validators["ProbeResponse"].validate(invalid)
    except ValidationError:
        pass
    else:
        raise AssertionError("Missing request_id was accepted")
    changed = copy.deepcopy(spec)
    changed["components"]["schemas"]["ProbeResponse"]["required"].remove("request_id")
    try:
        compatible(spec, changed)
    except ValueError:
        pass
    else:
        raise AssertionError("Breaking change was accepted")
    manifest = json.loads((ROOT / "backend/migrations/manifest.json").read_text())
    versions = [item["version"] for item in manifest["migrations"]]
    assert versions == list(range(1, len(versions) + 1))
    for item in manifest["migrations"]:
        assert hashlib.sha256((ROOT / "backend/migrations" / item["file"]).read_bytes()).hexdigest() == item["sha256"]
    registry = json.loads((ROOT / "backend/storage-registry.json").read_text())
    required = {"id", "owner", "status", "principal_binding", "sensitive_fields", "retention", "cleanup_hook", "restore_fence"}
    assert all(required <= set(item) for item in registry["stores"])
    print("PASS OpenAPI, positive/failure/unknown/conflict examples, negative schema, compatibility guard, storage registry")

if __name__ == "__main__":
    main()
