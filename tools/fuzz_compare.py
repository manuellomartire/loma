#!/usr/bin/env python3
"""Differential test: random LOMA files (valid, almost valid and corrupted) are compiled by the
Python reference compiler and by the JavaScript implementation; the results must be identical.

    python3 tools/fuzz_compare.py --count 3000 --seed 1

For a valid file the MIDI bytes and the events JSON are compared; for an invalid one the complete
error reports (code, line, context, message, suggestions). Exit status 1 on the first difference, with the offending file kept on disk.
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from loma.api import compile_text
from loma.errors import LomaErrors
from loma.events import canonical_json
from loma.util import duration_ticks

NODE_DRIVER = r"""
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const loma = require(process.argv[1]);
const dir = process.argv[2];
const out = {};
for (const name of fs.readdirSync(dir).filter((n) => n.endsWith(".loma")).sort()) {
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(fs.readFileSync(path.join(dir, name)));
  } catch (e) { out[name] = { errors: [{ code: "E001", line: 1 }] }; continue; }
  try {
    const r = loma.compileText(text);
    out[name] = { midi: crypto.createHash("sha256").update(r.midi).digest("hex"),
                  events: crypto.createHash("sha256").update(loma.canonicalJson(r.compiled)).digest("hex") };
  } catch (e) {
    if (!(e instanceof loma.LomaErrors)) { out[name] = { crash: String(e && e.stack || e) }; continue; }
    out[name] = { errors: e.errors };
  }
}
process.stdout.write(JSON.stringify(out));
"""

DURS_01 = ["1", "2", "4", "8", "16", "32", "2.", "4.", "8.", "16.", "4t", "8t", "16t", "8.."]
DURS_02 = DURS_01 + ["8q", "16q", "4x5/4"]
NOTES = ["C", "C#", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
QUALS_01 = ["", "m", "7", "maj7", "m7", "dim", "aug", "sus2", "sus4"]
QUALS_03 = QUALS_01 + ["9", "m9", "13", "6", "add9", "m7b5"]
DRUMS = ["kick", "snare", "hat", "ohat", "crash", "ride", "tom1", "tom2"]
NOISE = list(" \t/{}[]()|~#=>:*\"+-.,0123456789abcdrxmvotCEG") + ["\n", "è", "end", "bar ", "use ", "r/4 "]


class Gen:
    def __init__(self, rng):
        self.r = rng
        self.allow = {2: True, 3: True, 10: True, 11: True}
        self.cur_len = 1920
        self.drums_now = False

    def has(self, rank):
        """True if this file may use the features of that language version."""
        return self.allow[rank]

    @property
    def durs(self):
        return DURS_02 if self.has(2) else DURS_01

    def pick(self, seq):
        return seq[self.r.randrange(len(seq))]

    def chance(self, p):
        return self.r.random() < p

    def fill(self, length):
        out, left = [], length
        while left > 0:
            spec = self.pick(self.durs)
            ticks = duration_ticks(spec)
            if ticks > left or self.chance(0.08):
                spec, ticks = "#%d" % left, left
            out.append(spec)
            left -= ticks
        if self.chance(0.004):
            out.append(self.pick(self.durs))           # wrong on purpose
        if len(out) > 1 and self.chance(0.004):
            out.pop()
        return out

    def attrs(self, line_level=False):
        if not self.chance(0.3):
            return ""
        parts = []
        if self.chance(0.6):
            parts.append("v=%d" % self.r.randint(1, 127))
        if self.chance(0.3):
            parts.append("o=%d" % self.r.randint(-40, 40))
        if self.chance(0.2):
            parts.append("a=" + self.pick(["leg", "norm", "stac"]))
        if self.chance(0.1):
            parts.append("d=%d" % self.r.randint(1, 900))
        if line_level and self.chance(0.3) and self.has(2):
            parts.append("v=%d>%d" % (self.r.randint(1, 127), self.r.randint(1, 127)))
        if line_level and self.chance(0.2) and self.has(2):
            parts.append("swing=" + (self.pick(["sw", "sx"]) if self.chance(0.97) else "nope"))
        return "{%s}" % " ".join(parts) if parts else ""

    def pitch(self, drums):
        if drums:
            return "m%d" % self.r.randint(27, 90) if self.chance(0.1) and self.has(10) else self.pick(DRUMS)
        if self.chance(0.05) and self.has(10):
            return "m%d" % self.r.randint(0, 130 if self.chance(0.02) else 127)
        return "%s%d" % (self.pick(NOTES), self.r.randint(1, 7))

    def control(self):
        if not self.has(2):
            return self.pick(["pedal+", "pedal-"])
        kind = self.r.randrange(7 if self.has(10) else 5)
        if kind == 0:
            return "cc%d=%d" % (self.r.randint(0, 127), self.r.randint(0, 127))
        if kind == 1:
            return "cc%d=%d>%d/%s" % (self.r.randint(0, 127), self.r.randint(0, 127), self.r.randint(0, 127), self.pick(self.durs))
        if kind == 2:
            return "bend=%d" % self.r.randint(-8192, 8191)
        if kind == 3:
            return "bend=%d>%d/%s" % (self.r.randint(-8192, 8191), self.r.randint(-8192, 8191), self.pick(self.durs))
        if kind == 4:
            return self.pick(["pedal+", "pedal-"]) if not self.drums_now or self.chance(0.03) else "cc64=0"
        return '"%s"' % self.pick(["la", "do re", "x|y", "a#b", "è"])

    def content(self, length, drums):
        self.drums_now = drums
        toks, last = [], None           # last = (index, pitch) of the latest plain note
        for spec in self.fill(length):
            if self.chance(0.12) and (self.has(2) or not drums):
                toks.append(self.control())
            kind = self.r.random()
            tie = "~" if self.chance(0.001) else ""
            if last is not None and not drums and self.chance(0.12):
                toks[last[0]] += "~"            # a well-formed tie
                toks.append("%s/%s" % (last[1], spec))
                last = (len(toks) - 1, last[1])
                continue
            last = None
            if kind < 0.15:
                toks.append("r/" + spec)
            elif kind < 0.3:
                count = self.r.randint(1, 4)
                names = self.r.sample(DRUMS, count) if drums else ["%s%d" % (x, self.r.randint(2, 6)) for x in self.r.sample("CDEFGAB", count)]
                if self.chance(0.02):
                    names.append(names[0])      # duplicate on purpose
                toks.append("[%s]/%s%s%s" % (" ".join(x + self.attrs() for x in names), spec, tie, self.attrs()))
            elif kind < 0.38 and not drums and self.has(3):
                toks.append("*%s/%s%s%s" % (self.pick(["vo", "vs", "nope"] if self.chance(0.03) else ["vo", "vs"]), spec, tie, self.attrs()))
            else:
                name = self.pitch(drums)
                toks.append("%s/%s%s" % (name, spec, tie))
                if self.chance(0.7):
                    last = (len(toks) - 1, name)
                else:
                    toks[-1] += self.attrs()
        return toks

    def chord(self):
        c = self.pick(NOTES) + self.pick(QUALS_03 if self.has(3) else QUALS_01)
        if self.chance(0.15) and self.has(3):
            c += "^%d" % self.r.randint(0, 2)
        if self.chance(0.15) and self.has(3):
            c += "/" + self.pick(NOTES)
        return c

    def step(self):
        def tone():
            if self.chance(0.001):
                return "2"
            high = self.chance(0.02)            # tones that most chords do not have
            if self.has(3):
                return str(self.pick([7, 9, 14] if high else [0, 1, 3, 5, 8, 10, 12])) + self.pick(["", "", "", "+", "-"])
            return str(self.pick([7, 14] if high else [1, 1, 3, 5, 5, 8, 10, 12]))
        if self.chance(0.1):
            body = "r"
        elif self.chance(0.25):
            body = "(%s)" % " ".join(tone() for _ in range(self.r.randint(1, 3)))
        else:
            body = tone()
        if self.chance(0.01):
            body += "/" + self.pick(self.durs)
        return body + (self.attrs() if body[0] != "r" else "")

    def bars(self, meter_len, tracks, depth, out, indent):
        for _ in range(self.r.randint(1, 3)):
            if depth < 2 and self.chance(0.15) and self.has(2):
                out.append("%srepeat %d" % (indent, self.r.randint(1, 3)))
                self.bars(meter_len, tracks, depth + 1, out, indent + "  ")
                out.append(indent + "end")
                continue
            n = self.pick([1, 1, 1, 2, 2, 3, 4])
            head = "%sbar %s" % (indent, " ".join(self.chord() for _ in range(n)))
            if self.chance(0.12) and self.has(11):          # the meter changes from this bar to the end of the section
                num, den = self.pick([(4, 4), (3, 4), (6, 8), (2, 4), (5, 8), (3, 4)] if self.chance(0.97) else [(0, 4), (3, 5), (65, 4)])
                head += " meter=%d/%d" % (num, den)
                if 1 <= num <= 64 and den in (1, 2, 4, 8, 16, 32, 64):
                    self.cur_len = num * (1920 // den)
            if self.chance(0.08) and self.has(11):
                head += " key=" + self.pick(["C", "Dm", "F#", "Bbm", "Eb"] if self.chance(0.97) else ["H", "G#"])
            length = self.cur_len
            if self.chance(0.1):
                spec = self.pick(self.durs + ["#%d" % self.r.randint(1, 3000)])
                head += " len=/" + spec
                length = duration_ticks(spec)
            if self.chance(0.15):
                head += " tempo=%d" % self.r.randint(4, 400)
                if self.chance(0.6):
                    head += ">%d" % self.r.randint(4, 400)
            out.append(head)
            lines = []
            for name, drums in tracks:
                if self.chance(0.25):
                    continue
                lines.append((name, drums))
                while self.chance(0.2) and self.has(11):   # another voice on the same track
                    lines.append((name, drums))
            if lines and self.chance(0.2):
                self.r.shuffle(lines)
            for name, drums in lines:
                prefix = "%s  %s%s: " % (indent, name, self.attrs(True))
                if n > 1 and self.chance(0.35) and length % n == 0 and self.has(2):
                    parts = []
                    for _ in range(n if self.chance(0.97) else n + 1):
                        if not drums and self.chance(0.3) and ((length // n) % self.plen == 0 or self.chance(0.03)):
                            parts.append("use " + self.pick(["pa", "pb", "pc", "pa,pb", "nope"] if self.chance(0.1) else ["pa", "pb", "pc"]))
                        else:
                            parts.append(" ".join(self.content(length // n, drums)))
                    sep = " |\n%s      " % indent if self.chance(0.3) else " | "
                    out.append(prefix + sep.join(parts))
                elif not drums and self.chance(0.3) and length % n == 0 and ((length // n) % self.plen == 0 or self.chance(0.03)):
                    out.append(prefix + "use " + self.pick(["pa", "pb", "pc", "pb,pa", "pc,pc,pa"] if self.has(2) else ["pa", "pb", "pc"]))
                else:
                    toks = self.content(length, drums)
                    if len(toks) > 1 and self.chance(0.15) and self.has(2):
                        cut = self.r.randint(0, len(toks))
                        out.append(prefix + " ".join(toks[:cut]))
                        out.append(indent + "      " + " ".join(toks[cut:]))
                    else:
                        out.append(prefix + " ".join(toks))

    def song(self):
        version = self.pick(["0.1", "0.2", "0.3", "1.0", "1.0", "1.1", "1.1", "1.1"])
        rank = {"0.1": 1, "0.2": 2, "0.3": 3, "1.0": 10, "1.1": 11}[version]
        self.allow = {r: rank >= r or self.chance(0.05) for r in (2, 3, 10, 11)}   # sometimes too new: E020
        out = ["loma " + version]
        if self.chance(0.5):
            out.append('title "%s"' % self.pick(["Test", "È qui", "a # b"]))
        if self.chance(0.7):
            out.append("tempo %d" % self.r.randint(4, 400))
        num, den = self.pick([(4, 4), (4, 4), (3, 4), (6, 8), (5, 4), (2, 2), (7, 8)])
        out.append("meter %d/%d" % (num, den))
        if self.chance(0.4):
            out.append("key " + self.pick(["C", "Am", "F#m", "Bb", "Eb", "G#"] if self.chance(0.05) else ["C", "Am", "F#m", "Bb", "Eb"]))
        tracks = []
        channels = self.r.sample([1, 2, 3, 4, 11, 16], self.r.randint(1, 3))
        for i, ch in enumerate(channels):
            out.append("track T%d ch=%d program=%d" % (i, ch, self.r.randint(0, 127)))
            tracks.append(("T%d" % i, False))
        if self.chance(0.4):
            out.append("track K drums")
            tracks.append(("K", True))
        self.plen = self.pick([240, 480])       # every pattern of the song has this length
        for name in ("pa", "pb", "pc"):
            dur = self.pick(["8", "16", "8t"] if self.plen == 240 else ["4", "8", "16", "8t", "4t"])
            count = self.plen // duration_ticks(dur)
            out.append("pattern %s base=%d dur=/%s : %s" % (name, self.r.randint(2, 4), dur,
                                                           " ".join(self.step() for _ in range(count))))
        if self.chance(0.4) and self.has(2):
            out.append("pattern pd from pa%s : %s" % (self.pick(["", " base=2"]),
                       " ".join("%d=%s" % (1 if self.chance(0.97) else self.r.randint(1, 9), self.step()) for _ in range(self.r.randint(0, 2)))))
        if self.has(2):
            out.append("swing sx grid=/4 : 0 %d" % self.r.randint(-9, 9))
            out.append("swing sw grid=/%s : %s" % (self.pick(["8", "16", "8t"]), " ".join(str(self.r.randint(-30, 60)) for _ in range(self.r.randint(1, 4)))))
        if self.has(3):
            out.append("voicing vs base=3 : 0 7 10")
            out.append("voicing vo base=%d : %s" % (self.r.randint(2, 4), " ".join(sorted(set(self.pick(["1", "3", "5", "8", "10", "0", "5-", "12"] + (["7"] if self.chance(0.05) else [])) for _ in range(self.r.randint(1, 4)))))))
        meter_len = num * (1920 // den)
        names = []
        for i in range(self.r.randint(1, 3)):
            names.append("s%d" % i)
            out.append("section s%d" % i)
            self.cur_len = meter_len                # every section starts in the meter of the header
            self.bars(meter_len, tracks, 0, out, "  ")
            out.append("end")
        for _ in range(self.r.randint(1, 3)):
            line = "play " + self.pick(names + ["nope"] if self.chance(0.05) else names)
            if self.chance(0.3):
                line += " x%d" % self.r.randint(1, 3)
            if self.chance(0.3):
                line += " transpose=%d" % self.r.randint(-14, 14)
            out.append(line)
        for _ in range(self.r.randint(0, 3)):
            name, drums = self.pick(tracks)
            note = "%s d=%d v=%d" % (self.pitch(drums), self.r.randint(1, 2000), self.r.randint(1, 127))
            what = self.pick([note, "cc%d=%d" % (self.r.randint(0, 127), self.r.randint(0, 127)),
                              "bend=%d" % self.r.randint(-8192, 8191), '"la la"']) if self.has(10) else note
            out.append("at %d %s %s" % (self.r.randint(0, 20000), name, what))
        if self.chance(0.2) and self.has(10):
            out.append("at %d tempo=%d" % (self.r.randint(0, 9000), self.r.randint(4, 400)))
        for _ in range(self.r.randint(0, 2) if self.has(11) and self.chance(0.3) else 0):
            out.append("at %d %s" % (self.pick([0, 0, 480, 1920, self.r.randint(0, 9000)]),
                                     self.pick(["meter=3/4", "meter=7/8", "meter=4/4", "key=Dm", "key=A", "key=C", "meter=9/3", "key=Q"])))
        text = "\n".join(out) + "\n"
        if self.chance(0.25):
            chars = list(text)
            for _ in range(self.r.randint(1, 4)):
                i = self.r.randrange(len(chars))
                op = self.r.randrange(3)
                if op == 0:
                    del chars[i]
                elif op == 1:
                    chars.insert(i, self.pick(NOISE))
                else:
                    chars[i] = self.pick(NOISE)
            text = "".join(chars)
        if self.chance(0.1):
            text = text.replace("\n", "\r\n")
        return text


def reference(text):
    try:
        compiled, midi = compile_text(text)
    except LomaErrors as e:
        return {"errors": [x.to_dict() for x in e.errors]}
    events = canonical_json(compiled.events, compiled.track_names).encode("utf-8")
    return {"midi": hashlib.sha256(midi).hexdigest(), "events": hashlib.sha256(events).hexdigest()}


def main():
    ap = argparse.ArgumentParser(description="Python vs JavaScript differential test")
    ap.add_argument("--count", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--node", default="node")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    gen = Gen(rng)
    tmp = tempfile.mkdtemp(prefix="loma-fuzz-")
    expected = {}
    for i in range(args.count):
        name = "%06d.loma" % i
        text = gen.song()
        with open(os.path.join(tmp, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        expected[name] = reference(text)
    r = subprocess.run([args.node, "-e", NODE_DRIVER, os.path.join(ROOT, "js", "loma.js"), tmp], capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode("utf-8", "replace"))
        return 1
    got = json.loads(r.stdout.decode("utf-8"))
    valid = sum(1 for v in expected.values() if "midi" in v)
    for name in sorted(expected):
        if got.get(name) != expected[name]:
            print("DIFFERENCE in %s" % os.path.join(tmp, name))
            print("  python:     %s" % expected[name])
            print("  javascript: %s" % got.get(name))
            return 1
    print("OK: %d files (%d valid, %d invalid), identical results" % (args.count, valid, args.count - valid))
    for name in expected:
        os.remove(os.path.join(tmp, name))
    os.rmdir(tmp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
