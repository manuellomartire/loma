#!/usr/bin/env python3
"""LOMA conformance runner. Works with any compiler that implements the command protocol:

    <cmd> compile FILE -o OUT        exit 0, writes the MIDI file
    <cmd> expand FILE --json         exit 0, canonical JSON of the events on standard output
    <cmd> check FILE --json          exit 1 on errors, JSON array of {"code", "line", ...} on standard output

Usage:
    python3 conformance/run.py --cmd "python3 -m loma"
    python3 conformance/run.py --cmd "node js/loma.js"

Exit status: 0 if every case passes, 1 otherwise.
"""
import argparse
import glob
import json
import os
import shlex
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def run(cmd, args, timeout):
    return subprocess.run(cmd + args, capture_output=True, timeout=timeout)


def check_valid(cmd, path, tmp, timeout):
    base = path[:-5]
    out = os.path.join(tmp, "out.mid")
    if os.path.exists(out):
        os.remove(out)
    r = run(cmd, ["compile", path, "-o", out], timeout)
    if r.returncode != 0 or not os.path.exists(out):
        return "compile failed (exit %d): %s" % (r.returncode, r.stderr.decode("utf-8", "replace").strip()[:200])
    with open(out, "rb") as f, open(base + ".mid", "rb") as g:
        if f.read() != g.read():
            return "MIDI bytes differ"
    r = run(cmd, ["expand", path, "--json"], timeout)
    with open(base + ".events.json", "rb") as g:
        if r.returncode != 0 or r.stdout != g.read():
            return "events JSON differs"
    return None


def check_error(cmd, path, timeout, first_only):
    with open(path[:-5] + ".errors.json", encoding="utf-8") as f:
        expected = [(e["code"], e["line"]) for e in json.load(f)]
    r = run(cmd, ["check", path, "--json"], timeout)
    if r.returncode != 1:
        return "expected exit status 1, got %d" % r.returncode
    try:
        got = [(e["code"], e["line"]) for e in json.loads(r.stdout.decode("utf-8"))]
    except (ValueError, KeyError, TypeError):
        return "the output is not a JSON array of errors with code and line"
    if first_only:
        expected, got = expected[:1], got[:1]
    if got != expected:
        return "expected %s, got %s" % (expected, got)
    return None


def main():
    ap = argparse.ArgumentParser(description="LOMA conformance runner")
    ap.add_argument("--cmd", required=True, help='compiler command, e.g. "python3 -m loma"')
    ap.add_argument("--first-error-only", action="store_true",
                    help="for invalid files compare only the first error (the minimum a conforming compiler must report)")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    cmd = shlex.split(args.cmd)

    failures, total = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        for path in sorted(glob.glob(os.path.join(HERE, "valid", "*.loma"))):
            total += 1
            try:
                problem = check_valid(cmd, path, tmp, args.timeout)
            except (subprocess.TimeoutExpired, OSError) as e:
                problem = str(e)
            if problem:
                failures.append((os.path.relpath(path, HERE), problem))
        for path in sorted(glob.glob(os.path.join(HERE, "errors", "*.loma"))):
            total += 1
            try:
                problem = check_error(cmd, path, args.timeout, args.first_error_only)
            except (subprocess.TimeoutExpired, OSError) as e:
                problem = str(e)
            if problem:
                failures.append((os.path.relpath(path, HERE), problem))
    if not args.quiet:
        for name, problem in failures:
            print("FAIL %s: %s" % (name, problem))
    print("%d/%d conformance cases passed" % (total - len(failures), total))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
