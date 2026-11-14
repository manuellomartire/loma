"""The documentation must stay true: every complete example compiles, the examples and the
experiment material are valid, and the documented numbers match the code."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from loma import SPEC_VERSION, __version__
from loma.api import compile_text, sha256
from loma.model import CHORD_INTERVALS, DRUMS, RESERVED, VERSIONS
from loma.util import duration_ticks

DOCS = ["README.md", "README.it.md", "SPEC.md", "SPEC.it.md",
        os.path.join("experiment", "prompt.md"), os.path.join("experiment", "prompt.it.md")]


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class Documentation(unittest.TestCase):
    def test_loma_blocks_compile(self):
        total = 0
        for name in DOCS:
            for block in re.findall(r"```loma\n(.*?)```", read(name), re.S):
                compile_text(block)
                total += 1
        self.assertGreaterEqual(total, 7)

    def test_both_specs_have_the_same_examples_and_structure(self):
        it, en = read("SPEC.it.md"), read("SPEC.md")
        self.assertEqual(len(re.findall(r"^## ", it, re.M)), len(re.findall(r"^## ", en, re.M)))
        self.assertEqual(len(re.findall(r"^### ", it, re.M)), len(re.findall(r"^### ", en, re.M)))
        hashes = lambda text: [sha256(compile_text(b)[1]) for b in re.findall(r"```loma\n(.*?)```", text, re.S)]
        self.assertEqual(hashes(it)[0], hashes(en)[0])
        self.assertEqual(hashes(it)[0], "ab4d7aaa44d5b98d3df8d7df7937dbee852d20ce3869a8b5d4612758349bb460")

    def test_both_prompts_have_the_same_rules(self):
        en, it = read(os.path.join("experiment", "prompt.md")), read(os.path.join("experiment", "prompt.it.md"))
        for pattern in (r"^#+ ", r"^[0-9]+\. ", r"^\*\*", r"`[^`]+`"):
            self.assertEqual(len(re.findall(pattern, en, re.M)), len(re.findall(pattern, it, re.M)), pattern)
        events = lambda text: [len(compile_text(b)[0].events) for b in re.findall(r"```loma\n(.*?)```", text, re.S)]
        self.assertEqual(events(en), events(it))

    def test_spec_tables_match_the_code(self):
        for name in ("SPEC.md", "SPEC.it.md"):
            text = read(name)
            for quality, intervals in CHORD_INTERVALS.items():
                if quality:
                    self.assertIn("| `%s` | %s |" % (quality, " ".join(map(str, intervals))), text, (name, quality))
            for drum, pitch in DRUMS.items():
                self.assertRegex(text, r"`%s` \| %d\b" % (drum, pitch))
            for word in RESERVED:
                self.assertIn(word, text)
            for spec, ticks in re.findall(r"\| `/([0-9]+(?:\.|t)?)` \| ([0-9]+) ", text):
                self.assertEqual(duration_ticks(spec), int(ticks), spec)
            for code in ["E%03d" % n for n in range(1, 22)]:
                self.assertIn("| %s |" % code, text)
            for version in VERSIONS:
                self.assertIn("**%s**" % version, text)

    def test_versions_agree(self):
        self.assertEqual(SPEC_VERSION, "1.0")
        self.assertIn('version = "%s"' % __version__, read("pyproject.toml"))
        self.assertEqual(json.loads(read(os.path.join("js", "package.json")))["version"], __version__)
        self.assertEqual(json.loads(read(os.path.join("editors", "vscode", "package.json")))["version"], __version__)
        r = subprocess.run([sys.executable, "-m", "loma", "--version"], cwd=ROOT, capture_output=True, text=True)
        self.assertIn(__version__, r.stdout)

    def test_readme_counts_match_the_suite(self):
        valid = len(glob.glob(os.path.join(ROOT, "conformance", "valid", "*.loma")))
        errors = len(glob.glob(os.path.join(ROOT, "conformance", "errors", "*.loma")))
        text = read("README.it.md")
        self.assertIn("%d file validi" % valid, text)
        self.assertIn("%d file con gli errori attesi" % errors, text)
        self.assertIn("%d casi della suite" % (valid + errors), text)
        text = read("README.md")
        self.assertIn("%d valid files" % valid, text)
        self.assertIn("%d files with the expected errors" % errors, text)
        self.assertIn("%d cases of the suite" % (valid + errors), text)

    def test_readmes_have_the_same_structure(self):
        en, it = read("README.md"), read("README.it.md")
        blocks = lambda t: [sha256(compile_text(b)[1]) for b in re.findall(r"```loma\n(.*?)```", t, re.S)]
        self.assertEqual(len(blocks(en)), len(blocks(it)))
        self.assertEqual(len(re.findall(r"^\| ", en, re.M)), len(re.findall(r"^\| ", it, re.M)))

    def test_no_placeholders(self):
        for path in glob.glob(os.path.join(ROOT, "**", "*"), recursive=True):
            if os.path.isdir(path) or not path.endswith((".py", ".js", ".md", ".ebnf", ".json", ".toml")):
                continue
            if os.sep + "conformance" + os.sep in path and path.endswith(".json"):
                continue
            if os.path.abspath(path) == os.path.abspath(__file__):
                continue
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for marker in ("TODO", "FIXME", "XXX", "NotImplemented"):
                self.assertNotIn(marker, text, path)


class Examples(unittest.TestCase):
    def test_examples_compile_and_are_deterministic(self):
        paths = sorted(glob.glob(os.path.join(ROOT, "examples", "*.loma")))
        self.assertEqual([os.path.basename(p) for p in paths],
                         ["brano1.loma", "brano2.loma", "brano3.loma", "example.loma", "showcase.loma"])
        for path in paths:
            with open(path, encoding="utf-8") as f:
                text = f.read()
            first = sha256(compile_text(text)[1])
            self.assertTrue(all(sha256(compile_text(text)[1]) == first for _ in range(10)), path)

    def test_showcase_uses_every_construct(self):
        text = read(os.path.join("examples", "showcase.loma"))
        for needle in ("title ", "key ", "drums", "pattern ", " from ", "swing ", "voicing ", "repeat ", "tempo=", ">",
                       "swing=", "use ", ",", " | ", "*open", "pedal+", "cc1=", "bend=", '"la"', "/16q", "/8t", "~",
                       "{o=", "a=stac", "a=leg", "m45", "transpose=", "\nat ", "^1", "/B", "[", " x2", "x3/2", "len=", "{d=", "5-", "(1 3 5)"):
            self.assertIn(needle, text, needle)

    def test_web_page_is_built_and_its_compiler_matches(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build_web.py"), "--check"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        page = read(os.path.join("docs", "index.html"))
        scripts = re.findall(r"<script>(.*?)</script>", page, re.S)
        self.assertEqual(len(scripts), 2)
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed")
        probe = scripts[0] + ("\nconst h = require('crypto');"
                              "console.log(JSON.stringify(EXAMPLES.map((e) => [e.source, h.createHash('sha256').update(LOMA.compileText(e.source).midi).digest('hex')])));")
        out = subprocess.run([node, "-e", probe], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        pairs = json.loads(out.stdout)
        self.assertEqual(len(pairs), 5)
        for source, digest in pairs:
            self.assertEqual(sha256(compile_text(source)[1]), digest)
        self.assertEqual(subprocess.run([node, "--check", "-"], input=scripts[1], capture_output=True, text=True).returncode, 0)

    def test_json_files_are_valid(self):
        for name in (os.path.join("editors", "vscode", "syntaxes", "loma.tmLanguage.json"),
                     os.path.join("editors", "vscode", "language-configuration.json"),
                     os.path.join("experiment", "results.json")):
            json.loads(read(name))

    def test_experiment_report_is_current(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "experiment", "run_experiment.py"), "--no-write"],
                           cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, read(os.path.join("experiment", "results.md")))
        self.assertIn("| reference | brano3 | 1 | sì | sì | 32 | 5 |", r.stdout)


if __name__ == "__main__":
    unittest.main()
