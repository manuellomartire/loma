"""Command line interface. Exit status: 0 success, 1 errors in the input, 2 usage or I/O problem."""
import argparse
import json
import sys

from . import __version__, SPEC_VERSION
from .api import compile_text, expand_json, sha256
from .decompiler import decompile, DecompileError
from .errors import LomaError, LomaErrors
from .events import canonical_json
from .midi_reader import MidiError


def _read_source(path):
    if path == "-":
        data = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as f:
            data = f.read()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise LomaErrors([LomaError("E001", "the file is not valid UTF-8", 1)])


def _report(errors, as_json):
    if as_json:
        print(json.dumps([e.to_dict() for e in errors], sort_keys=True, ensure_ascii=False))
    else:
        for e in errors:
            print(e.format(), file=sys.stderr)
        print("%d error(s)" % len(errors), file=sys.stderr)


def _parser():
    ap = argparse.ArgumentParser(prog="loma", description="LOMA %s reference compiler" % SPEC_VERSION)
    ap.add_argument("--version", action="version", version="loma %s (language %s)" % (__version__, SPEC_VERSION))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("compile", help="compile a .loma file to MIDI")
    p.add_argument("file", help="source file, or - for standard input")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--json", action="store_true", help="errors as JSON on standard output")
    p = sub.add_parser("check", help="validate only")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("expand", help="print the expanded events")
    p.add_argument("file")
    p.add_argument("--json", action="store_true", help="canonical JSON")
    p = sub.add_parser("hash", help="SHA-256 of the MIDI output")
    p.add_argument("file")
    p = sub.add_parser("test-determinism", help="compile N times and compare the hashes")
    p.add_argument("file")
    p.add_argument("--runs", type=int, default=100)
    p = sub.add_parser("decompile", help="convert a MIDI file to LOMA")
    p.add_argument("file")
    p.add_argument("-o", "--output", help="output file (default: standard output)")
    return ap


def _run(args):
    if args.cmd == "decompile":
        with open(args.file, "rb") as f:
            source, warnings = decompile(f.read())
        for w in warnings:
            print("warning: " + w, file=sys.stderr)
        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="\n") as f:
                f.write(source)
        else:
            sys.stdout.write(source)
        return 0

    text = _read_source(args.file)
    if args.cmd == "check":
        compile_text(text)
        print("[]" if args.json else "OK")
    elif args.cmd == "compile":
        _, midi = compile_text(text)
        with open(args.output, "wb") as f:
            f.write(midi)
        if not args.json:
            print("wrote %s (%d bytes, sha256 %s)" % (args.output, len(midi), sha256(midi)))
    elif args.cmd == "expand":
        if args.json:
            sys.stdout.write(expand_json(text))
        else:
            compiled, _ = compile_text(text)
            names = compiled.track_names
            for e in compiled.events:
                d = e.to_dict(names)
                rest = " ".join("%s=%s" % (k, d[k]) for k in sorted(d) if k not in ("tick", "type"))
                print("%9d %-8s %s" % (e.tick, e.kind, rest))
    elif args.cmd == "hash":
        print(sha256(compile_text(text)[1]))
    elif args.cmd == "test-determinism":
        compiled, midi = compile_text(text)
        first = (sha256(midi), canonical_json(compiled.events, compiled.track_names))
        for _ in range(max(args.runs, 1) - 1):
            compiled, midi = compile_text(text)
            if (sha256(midi), canonical_json(compiled.events, compiled.track_names)) != first:
                print("FAIL: outputs differ between runs", file=sys.stderr)
                return 1
        print("OK: %d runs, identical output, sha256 %s" % (max(args.runs, 1), first[0]))
    return 0


def _portable_output():
    """UTF-8 and '\\n' on every system: the output must not depend on the platform (on Windows the
    default would be the local code page and '\\r\\n')."""
    for stream, errors in ((sys.stdout, "strict"), (sys.stderr, "backslashreplace")):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors=errors, newline="\n")


def main(argv=None):
    _portable_output()
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except LomaErrors as e:
        _report(e.errors, getattr(args, "json", False))
        return 1
    except (OSError, MidiError, DecompileError) as e:
        print("loma: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
