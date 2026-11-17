"""The conformance suite, run against the reference compiler and (when Node.js is installed)
against the JavaScript implementation, plus a differential test on random files."""
import glob
import json
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from loma.api import compile_text, sha256
from loma.errors import LomaErrors
from loma.events import canonical_json

NODE = shutil.which("node")


def source(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8")


class Reference(unittest.TestCase):
    def test_valid_cases_byte_for_byte(self):
        paths = sorted(glob.glob(os.path.join(ROOT, "conformance", "valid", "*.loma")))
        self.assertGreaterEqual(len(paths), 100)
        for path in paths:
            base = path[:-5]
            compiled, midi = compile_text(source(path))
            with open(base + ".mid", "rb") as f:
                self.assertEqual(midi, f.read(), os.path.basename(path))
            with open(base + ".events.json", "rb") as f:
                self.assertEqual(canonical_json(compiled.events, compiled.track_names).encode("utf-8"), f.read(), os.path.basename(path))
            with open(base + ".sha256", encoding="utf-8") as f:
                self.assertEqual(sha256(midi), f.read().strip())

    def test_error_cases(self):
        paths = sorted(glob.glob(os.path.join(ROOT, "conformance", "errors", "*.loma")))
        self.assertGreaterEqual(len(paths), 120)
        for path in paths:
            with open(path[:-5] + ".errors.json", encoding="utf-8") as f:
                expected = [(e["code"], e["line"]) for e in json.load(f)]
            try:
                compile_text(source(path))
            except UnicodeDecodeError:
                got = [("E001", 1)]
            except LomaErrors as e:
                got = [(x.code, x.line) for x in e.errors]
            else:
                got = []
            self.assertEqual(got, expected, os.path.basename(path))

    def test_every_error_code_has_a_case(self):
        seen = set()
        for path in glob.glob(os.path.join(ROOT, "conformance", "errors", "*.errors.json")):
            with open(path, encoding="utf-8") as f:
                seen.update(e["code"] for e in json.load(f))
        self.assertEqual(sorted(seen), ["E%03d" % n for n in range(1, 22)])

    def test_hand_verified_hashes_are_unchanged(self):
        """Files that existed before 1.0: their bytes must never change."""
        known = {"010_minimal": "ab4d7aaa44d5b98d3df8d7df7937dbee852d20ce3869a8b5d4612758349bb460",
                 "011_example": "218a89ca75559c642a4f1b8bf587a26b6bb1197d9fc40cdf6180489cb4d213de",
                 "012_brano1": "01d4d64ffc3306d09551d5095e1724e9485510a5e9caa40ea8170446d634588f",
                 "020_tempo_ramp": "ff029dd08eb0a3c8911603eb0dc3acc94a7fd630c28bfeb509fca96f621fb213",
                 "021_tempo_same_tick": "3a7cddd93ebe2b144084f4172e312f29457cf765d24a07b6f279dc4f5f4113a3"}
        for name, digest in known.items():
            with open(os.path.join(ROOT, "conformance", "valid", name + ".sha256"), encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), digest, name)

    def test_runner_on_reference(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "conformance", "run.py"), "--cmd",
                            '"%s" -m loma' % sys.executable, "--quiet"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


@unittest.skipIf(NODE is None, "Node.js is not installed")
class SecondImplementation(unittest.TestCase):
    def test_runner_on_javascript(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "conformance", "run.py"), "--cmd",
                            '"%s" "%s"' % (NODE, os.path.join(ROOT, "js", "loma.js"))], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_random_files_agree(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fuzz_compare.py"), "--count", "1500",
                            "--seed", "2026", "--node", NODE], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_decompilers_agree(self):
        from loma.api import decompile
        script = ("const fs = require('fs'), l = require(process.argv[1]); const out = {};"
                  "for (const p of process.argv.slice(2)) out[p] = l.decompile(new Uint8Array(fs.readFileSync(p)));"
                  "process.stdout.write(JSON.stringify(out));")
        paths = sorted(glob.glob(os.path.join(ROOT, "conformance", "valid", "*.mid")))
        r = subprocess.run([NODE, "-e", script, os.path.join(ROOT, "js", "loma.js")] + paths, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout.decode("utf-8"))
        for path in paths:
            with open(path, "rb") as f:
                text, warnings = decompile(f.read())
            self.assertEqual(got[path]["source"], text, os.path.basename(path))
            self.assertEqual(got[path]["warnings"], warnings)

    def test_error_reports_agree_in_full(self):
        """Not only code and line: messages, context and suggestions are the same in the two compilers."""
        paths = sorted(glob.glob(os.path.join(ROOT, "conformance", "errors", "*.loma")))
        script = ("const fs = require('fs'), l = require(process.argv[1]); const out = {};"
                  "for (const p of process.argv.slice(2)) { try { l.compileText(new TextDecoder('utf-8', {fatal: true, ignoreBOM: true})"
                  ".decode(fs.readFileSync(p))); out[p] = []; } catch (e) { out[p] = e.errors || null; } }"
                  "process.stdout.write(JSON.stringify(out));")
        r = subprocess.run([NODE, "-e", script, os.path.join(ROOT, "js", "loma.js")] + paths, capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout.decode("utf-8"))
        compared = 0
        for path in paths:
            try:
                compile_text(source(path))
            except UnicodeDecodeError:
                continue
            except LomaErrors as e:
                self.assertEqual(got[path], [x.to_dict() for x in e.errors], os.path.basename(path))
                compared += 1
        self.assertGreaterEqual(compared, 110)

    def test_floor_div_table(self):
        script = ("const l = require(process.argv[1]);"
                  "console.log([l.floorDiv(7,3), l.floorDiv(-7,3), l.floorDiv(7,-3), l.floorDiv(-7,-3)].join(' '))")
        r = subprocess.run([NODE, "-e", script, os.path.join(ROOT, "js", "loma.js")], capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "2 -3 -3 2")


if __name__ == "__main__":
    unittest.main()
