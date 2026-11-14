#!/usr/bin/env python3
"""Regenerates the expected files of the conformance suite from the reference compiler.

    conformance/valid/NAME.loma   -> NAME.mid, NAME.events.json, NAME.sha256
    conformance/errors/NAME.loma  -> NAME.errors.json

Run it only after a deliberate change of the specification: the generated files are the contract
that other implementations are checked against.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from loma.api import compile_text, sha256
from loma.errors import LomaErrors
from loma.events import canonical_json


def source(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8")


def main():
    status = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "conformance", "valid", "*.loma"))):
        base = path[:-5]
        try:
            compiled, midi = compile_text(source(path))
        except LomaErrors as e:
            print("NOT VALID %s: %s" % (os.path.basename(path), e.errors[0].format()))
            status = 1
            continue
        with open(base + ".mid", "wb") as f:
            f.write(midi)
        with open(base + ".events.json", "w", encoding="utf-8", newline="\n") as f:
            f.write(canonical_json(compiled.events, compiled.track_names))
        with open(base + ".sha256", "w", encoding="utf-8", newline="\n") as f:
            f.write(sha256(midi) + "\n")
    for path in sorted(glob.glob(os.path.join(ROOT, "conformance", "errors", "*.loma"))):
        try:
            with open(path, "rb") as f:
                compile_text(f.read().decode("utf-8"))
        except UnicodeDecodeError:
            errors = [{"code": "E001", "line": 1}]
        except LomaErrors as e:
            errors = [{"code": x.code, "line": x.line} for x in e.errors]
        else:
            print("NOT AN ERROR CASE %s" % os.path.basename(path))
            status = 1
            continue
        with open(path[:-5] + ".errors.json", "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(errors) + "\n")
    return status


if __name__ == "__main__":
    sys.exit(main())
