"""MIDI -> LOMA."""
import glob
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from loma.api import compile_text, decompile
from loma.decompiler import DecompileError
from loma.midi_reader import MidiError, read_midi


def smf(fmt, division, *tracks):
    out = b"MThd" + (6).to_bytes(4, "big") + fmt.to_bytes(2, "big") + len(tracks).to_bytes(2, "big") + division.to_bytes(2, "big")
    for body in tracks:
        out += b"MTrk" + len(body).to_bytes(4, "big") + body
    return out


class RoundTrip(unittest.TestCase):
    def test_every_conformance_file_survives_byte_for_byte(self):
        paths = sorted(glob.glob(os.path.join(ROOT, "conformance", "valid", "*.mid")))
        self.assertGreaterEqual(len(paths), 90)
        for path in paths:
            with open(path, "rb") as f:
                data = f.read()
            src, warnings = decompile(data)
            self.assertEqual(warnings, [], os.path.basename(path))
            self.assertEqual(compile_text(src)[1], data, os.path.basename(path))

    def test_decompiled_source_is_stable(self):
        with open(os.path.join(ROOT, "conformance", "valid", "404_showcase.mid"), "rb") as f:
            data = f.read()
        first, _ = decompile(data)
        second, _ = decompile(compile_text(first)[1])
        self.assertEqual(first, second)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "x.loma")
            mid = os.path.join(ROOT, "conformance", "valid", "011_example.mid")
            r = subprocess.run([sys.executable, "-m", "loma", "decompile", mid, "-o", out], cwd=ROOT, capture_output=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            h1 = subprocess.run([sys.executable, "-m", "loma", "hash", out], cwd=ROOT, capture_output=True, text=True).stdout.strip()
            with open(mid[:-4] + ".sha256", encoding="utf-8") as f:
                self.assertEqual(h1, f.read().strip())
            bad = os.path.join(tmp, "bad.mid")
            with open(bad, "wb") as f:
                f.write(b"not midi")
            self.assertEqual(subprocess.run([sys.executable, "-m", "loma", "decompile", bad], cwd=ROOT, capture_output=True).returncode, 2)


class ForeignFiles(unittest.TestCase):
    def test_format_0_running_status_and_other_division(self):
        # 96 ticks per quarter; note-on, then the note-off as a running-status note-on with velocity 0
        body = (b"\x00\xff\x51\x03\x07\xa1\x20" b"\x00\x90\x3c\x64" b"\x60\x3c\x00" b"\x00\xb0\x07\x50"
                b"\x00\xe0\x00\x40" b"\x00\xff\x2f\x00")
        src, warnings = decompile(smf(0, 96, body))
        self.assertIn("track ch1 ch=1 program=0", src)
        self.assertIn("at 0 ch1 C4 d=480 v=100", src)
        self.assertIn("at 480 ch1 cc7=80", src)
        self.assertIn("at 480 ch1 bend=0", src)
        self.assertIn("tempo 120", src)
        self.assertIn("bar C len=/#480", src)
        self.assertEqual(warnings, [])
        compile_text(src)

    def test_lossy_content_is_reported(self):
        body = (b"\x00\xff\x51\x03\x07\xa1\x21"          # 500001 us: not an integer BPM
                b"\x00\xc0\x05" b"\x00\x90\x3c\x64" b"\x00\x90\x3c\x64"       # duplicate note
                b"\x00\xd0\x10" b"\x00\xf0\x02\x01\xf7" b"\x00\xc0\x06"       # aftertouch, sysex, 2nd program
                b"\x83\x60\x80\x3c\x00" b"\x00\x80\x3c\x00" b"\x00\x90\x40\x64"  # last note never ends
                b"\x83\x60\xff\x2f\x00")
        src, warnings = decompile(smf(1, 480, body))
        text = "\n".join(warnings)
        for needle in ("not an integer BPM", "duplicate note", "aftertouch", "system exclusive",
                       "program changes after the first one", "no note-off"):
            self.assertIn(needle, text)
        self.assertIn("program=5", src)
        compile_text(src)

    def test_drums_and_unknown_drum_pitch(self):
        body = b"\x00\x99\x24\x64" b"\x10\x89\x24\x00" b"\x00\x99\x23\x64" b"\x10\x89\x23\x00" b"\x00\xff\x2f\x00"
        src, _ = decompile(smf(0, 480, body))
        self.assertIn("track drumkit drums", src)
        self.assertIn("at 0 drumkit kick d=16", src)
        self.assertIn("at 16 drumkit m35 d=16", src)
        compile_text(src)

    def test_track_names_are_made_valid_and_unique(self):
        def track(name, ch):
            return b"\x00\xff\x03" + bytes([len(name)]) + name + bytes([0x00, 0x90 | ch, 60, 100, 0x10, 0x80 | ch, 60, 0, 0x00, 0xff, 0x2f, 0x00])
        src, _ = decompile(smf(1, 480, b"\x00\xff\x2f\x00", track(b"Piano", 0), track(b"Piano", 1), track(b"bar", 2), track(b"1 x", 3)))
        for needle in ("track Piano ch=1", "track Piano_2 ch=2", "track ch3 ch=3", "track ch4 ch=4"):
            self.assertIn(needle, src)
        compile_text(src)

    def test_errors(self):
        with self.assertRaises(MidiError):
            read_midi(b"RIFF")
        with self.assertRaises(MidiError):
            read_midi(smf(2, 480, b"\x00\xff\x2f\x00"))
        with self.assertRaises(MidiError):
            read_midi(smf(1, 0xE728, b"\x00\xff\x2f\x00"))
        with self.assertRaises(MidiError):
            read_midi(smf(1, 480, b"\x00\x90\x3c"))
        with self.assertRaises(MidiError):
            read_midi(smf(1, 480, b"\x00\x3c\x40"))
        with self.assertRaises(DecompileError):
            decompile(smf(0, 100, b"\x01\x90\x3c\x64" b"\x01\x80\x3c\x00" b"\x00\xff\x2f\x00"))


if __name__ == "__main__":
    unittest.main()
