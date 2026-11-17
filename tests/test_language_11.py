"""LOMA 1.1: meter and key changes, several voices on one track. Expected values are computed by hand."""
import glob
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from loma.api import compile_text, decompile
from loma.errors import LomaErrors

H = "loma 1.1\ntempo 120\nmeter 4/4\ntrack P ch=1 program=0\n"


def song(body, head=H, tail="play s\n"):
    return head + "section s\n" + body + "end\n" + tail


def errs(text):
    try:
        compile_text(text)
    except LomaErrors as e:
        return [(x.code, x.line) for x in e.errors]
    return []


def events(text, *kinds):
    compiled, _ = compile_text(text)
    return [(e.tick, e.kind, tuple(e.data[k] for k in sorted(e.data))) for e in compiled.events if e.kind in kinds]


def notes(text):
    """[(start, end, pitch, velocity)] sorted by start, pitch."""
    compiled, _ = compile_text(text)
    on, out = {}, []
    for e in compiled.events:
        if e.kind == "note_on":
            on[e.pitch] = (e.tick, e.data["vel"])
        elif e.kind == "note_off":
            start, vel = on.pop(e.pitch)
            out.append((start, e.tick, e.pitch, vel))
    return sorted(out)


class Meter(unittest.TestCase):
    def test_conductor_bytes_by_hand(self):
        text = "loma 1.1\ntempo 120\nmeter 4/4\nkey C\ntrack P ch=1\n" \
               "section s\n  bar C\n    P: C4/1\n  bar C meter=3/4 key=F\n    P: C4/2.\nend\nplay s\n"
        conductor = bytes.fromhex(
            "00FF580404021808"      # tick 0: 4/4
            "00FF59020000"          # tick 0: C major
            "00FF510307A120"        # tick 0: 120 BPM = 500000 microseconds
            "8F00FF580403021808"    # delta 1920: 3/4
            "00FF5902FF00"          # same tick: F major, one flat = 0xFF
            "8B20FF2F00")           # delta 1440: end of track at 3360
        midi = compile_text(text)[1]
        self.assertEqual(midi[14:22], b"MTrk" + len(conductor).to_bytes(4, "big"))
        self.assertEqual(midi[22:22 + len(conductor)], conductor)

    def test_from_the_bar_to_the_end_of_the_section(self):
        body = "  bar C\n    P: C4/1\n  bar C meter=3/4\n    P: C4/2.\n  bar C\n    P: C4/2.\n"
        compiled, _ = compile_text(song(body, tail="play s x2\n"))
        self.assertEqual(compiled.bars, [0, 1920, 3360, 4800, 6720, 8160])
        self.assertEqual(compiled.end_tick, 9600)
        self.assertEqual(events(song(body, tail="play s x2\n"), "meter"),
                         [(1920, "meter", (4, 3)), (4800, "meter", (4, 4)), (6720, "meter", (4, 3))])

    def test_every_section_starts_in_the_meter_of_the_header(self):
        text = H + "section a\n  bar C meter=6/8\n    P: C4/2.\nend\nsection b\n  bar C\n    P: C4/1\nend\nplay a\nplay b\nplay b\nplay a\n"
        compiled, _ = compile_text(text)
        self.assertEqual(compiled.bars, [0, 1440, 3360, 5280])
        self.assertEqual(events(text, "meter"), [(1440, "meter", (4, 4)), (5280, "meter", (8, 6))])
        self.assertEqual(compiled.meter, (6, 8))            # the first bar replaces the signature of the header
        self.assertIn(bytes.fromhex("00FF580406031808"), compile_text(text)[1])
        self.assertNotIn(bytes.fromhex("00FF580404021808"), compile_text(text)[1][:40])

    def test_repeat_does_not_limit_the_scope(self):
        body = "  repeat 2\n    bar C\n      P: C4/#%d\n    bar C meter=2/4\n      P: C4/2\n  end\n  bar C\n    P: C4/2\n"
        # first pass: 4/4 then 2/4; second pass: the first bar of the block is 4/4 in the text
        compiled, _ = compile_text(song(body % 1920))
        self.assertEqual(compiled.bars, [0, 1920, 2880, 4800, 5760])
        self.assertEqual(events(song(body % 1920), "meter"),
                         [(1920, "meter", (4, 2)), (2880, "meter", (4, 4)), (4800, "meter", (4, 2))])

    def test_same_meter_writes_nothing(self):
        body = "  bar C meter=4/4\n    P: C4/1\n  bar C meter=4/4\n    P: C4/1\n"
        self.assertEqual(events(song(body), "meter"), [])

    def test_len_keeps_the_meter(self):
        body = "  bar C meter=3/4 len=/4\n    P: C4/4\n  bar C\n    P: C4/2.\n"
        compiled, _ = compile_text(song(body))
        self.assertEqual(compiled.bars, [0, 480])
        self.assertEqual(compiled.meter, (3, 4))

    def test_bar_length_errors_follow_the_meter(self):
        body = "  bar C meter=3/4\n    P: C4/1\n  bar C\n    P: C4/2.\n  bar C F meter=5/8\n    P: C4/4 r/#120 | C4/4 r/#120\n"
        self.assertEqual(errs(song(body)), [("E003", 7)])
        self.assertEqual(errs(song("  bar C F G A meter=1/64\n    P: r/#30\n")), [("E014", 6)])

    def test_limits_and_syntax(self):
        for bad, code in (("meter=65/4", "E018"), ("meter=3/5", "E018"), ("meter=0/4", "E018"), ("meter=3", "E001"),
                          ("meter=", "E001"), ("key=H", "E013"), ("key=G#", "E013"), ("key=", "E013")):
            self.assertEqual(errs(song("  bar C %s\n    P: C4/1\n" % bad)), [(code, 6)], bad)
            self.assertEqual(errs(song("  bar C\n    P: C4/1\n") + "at 0 %s\n" % bad), [(code, 10)], bad)

    def test_wrong_meter_line_hides_the_bars_after_it(self):
        body = "  bar C\n    P: C4/2\n  bar C meter=9/9\n    P: C4/1\n  bar C\n    P: C4/2\n"
        text = H + "section s\n" + body + "end\nsection t\n  bar C\n    P: C4/2\nend\nplay s\nplay t\n"
        self.assertEqual(errs(text), [("E003", 7), ("E018", 8), ("E003", 15)])
        other = H + "section s\n  bar C tempo=x\n    P: C4/1\n  bar C\n    P: C4/2\nend\nplay s\n"
        self.assertEqual(errs(other), [("E001", 6), ("E003", 9)])     # without 'meter=' the next bars are checked


class Key(unittest.TestCase):
    def test_scope_and_events(self):
        text = "loma 1.1\ntempo 120\nmeter 4/4\nkey C\ntrack P ch=1\n" \
               "section a\n  bar C\n    P: C4/1\n  bar D key=D\n    P: D4/1\n  bar D\n    P: D4/1\nend\n" \
               "section b\n  bar C\n    P: C4/1\nend\nplay a\nplay b\nplay a transpose=+1\n"
        self.assertEqual(events(text, "key"), [(1920, "key", (0, 2)), (5760, "key", (0, 0)), (9600, "key", (0, 2))])

    def test_no_key_in_the_header(self):
        text = H + "section a\n  bar C\n    P: C4/1\n  bar F key=Dm\n    P: F4/1\nend\nsection b\n  bar C\n    P: C4/1\nend\n" \
                   "play a\nplay b\nplay a\n"
        self.assertEqual(events(text, "key"), [(1920, "key", (1, -1))])
        self.assertIsNone(compile_text(text)[0].key)
        self.assertNotIn(b"\xff\x59", compile_text(text)[1][:40])

    def test_key_does_not_change_the_notes(self):
        plain = notes(song("  bar C\n    P: C4/1\n"))
        self.assertEqual(notes(song("  bar C key=F#\n    P: C4/1\n")), plain)


class AtSignatures(unittest.TestCase):
    BODY = "  bar C\n    P: C4/1\n  bar C meter=3/4 key=D\n    P: C4/2.\n"

    def test_last_one_wins_at_each_tick(self):
        text = song(self.BODY) + "at 1920 meter=5/8\nat 480 meter=7/8\nat 480 meter=7/16\nat 480 key=F#m\nat 480 tempo=90\n"
        self.assertEqual(events(text, "meter", "key", "tempo"),
                         [(0, "tempo", (120,)), (480, "meter", (16, 7)), (480, "key", (1, 3)), (480, "tempo", (90,)),
                          (1920, "meter", (8, 5)), (1920, "key", (0, 2))])

    def test_at_does_not_change_bar_lengths(self):
        compiled, _ = compile_text(song(self.BODY) + "at 0 meter=2/4\nat 0 key=Am\n")
        self.assertEqual(compiled.bars, [0, 1920])
        self.assertEqual((compiled.meter, compiled.key), ((2, 4), (0, 1)))

    def test_decompile_round_trip(self):
        text = "loma 1.1\ntitle \"T\"\ntempo 96\nmeter 6/8\nkey Gm\ntrack P ch=1 program=5\n" + \
               "section s\n" + self.BODY.replace("C4/1", "C4/2.") + "  bar F\n    P: F4/2.\n    P: A3/2.\nend\nplay s x2\nat 77 key=Cb\n"
        midi = compile_text(text)[1]
        source, warnings = decompile(midi)
        self.assertEqual(warnings, [])
        self.assertTrue(source.startswith("loma 1.1\n"))
        self.assertIn("at 1440 meter=3/4\n", source)
        self.assertIn("at 77 key=Cb\n", source)
        self.assertEqual(compile_text(source)[1], midi)

    def test_decompile_keeps_lyrics_of_a_drums_track_without_notes(self):
        text = "loma 1.0\ntempo 100\nmeter 4/4\ntrack P ch=1\ntrack K drums\n" \
               "section s\n  bar C\n    P: C4/1\nend\nplay s\nat 30 K \"la\"\nat 10 K \"li\"\n"
        midi = compile_text(text)[1]
        source, warnings = decompile(midi)
        self.assertEqual(warnings, [])
        self.assertIn('at 10 K "li"\nat 30 K "la"\n', source)
        self.assertEqual(compile_text(source)[1], midi)

    def test_decompile_stays_1_0_without_signature_changes(self):
        midi = compile_text(song("  bar C\n    P: C4/1\n    P: E4/1\n"))[1]
        self.assertTrue(decompile(midi)[0].startswith("loma 1.0\n"))


class Voices(unittest.TestCase):
    def test_each_voice_fills_the_bar(self):
        body = "  bar C\n    P{v=90}: E5/2 G5/2\n    P{v=50}: C3/1\n    P{v=30}: r/2 G3/2\n"
        self.assertEqual(notes(song(body)), [(0, 864, 76, 90), (0, 1728, 48, 50), (960, 1824, 55, 30), (960, 1824, 79, 90)])
        self.assertEqual(errs(song("  bar C\n    P: E5/1\n    P: C3/2\n")), [("E003", 8)])

    def test_ties_stay_inside_a_voice(self):
        body = "  bar C\n    P: E5/1~\n    P: C3/1~\n  bar C\n    P: E5/2 r/2\n    P: C3/1\n"
        # voice 0: 1920 + 960 = 2880 written, 90% = 2592; voice 1: 3840 written, 90% = 3456
        self.assertEqual(notes(song(body)), [(0, 2592, 76, 80), (0, 3456, 48, 80)])
        crossed = "  bar C\n    P: E5/1~\n    P: C3/1\n  bar C\n    P: C3/1\n    P: E5/1\n"
        self.assertEqual(errs(song(crossed)), [("E012", 7)])
        fewer = "  bar C\n    P: E5/1\n    P: C3/1~\n  bar C\n    P: C3/1\n"
        self.assertEqual(errs(song(fewer)), [("E012", 8)])

    def test_duplicates_and_overlaps_among_voices(self):
        self.assertEqual(errs(song("  bar C\n    P: C4/2 D4/2\n    P: E4/2 D4/2\n")), [("E017", 8)])
        cut = notes(song("  bar C\n    P: C4/1{a=leg}\n    P: r/2 C4/4 r/4\n"))
        self.assertEqual(cut, [(0, 960, 60, 80), (960, 1392, 60, 80)])

    def test_patterns_segments_and_drums(self):
        head = H + "track K drums\npattern arp base=3 dur=/4 : 1 3\n"
        body = "  bar C G\n    P: use arp\n    P: C5/2 | D5/4 r/4\n    K: kick/2 kick/2\n    K{v=40}: hat/4 hat/4 hat/4 hat/4\n"
        compiled, _ = compile_text(song(body, head=head))
        self.assertEqual(sum(1 for e in compiled.events if e.kind == "note_on"), 4 + 2 + 2 + 4)

    def test_events_are_numbered_voice_by_voice(self):
        body = "  bar C\n    P: cc1=1 C4/1\n    P: cc1=2 E4/1\n  bar C\n    P: cc1=3 C4/1\n    P: cc1=4 E4/1\n"
        compiled, _ = compile_text(song(body))
        seqs = {e.data["value"]: e.seq for e in compiled.events if e.kind == "cc"}
        self.assertEqual(seqs, {1: 0, 3: 3, 2: 6, 4: 9})     # voice 0: cc, note (2), cc, note (2); then voice 1

    def test_before_1_1(self):
        text = song("  bar C\n    P: C4/1\n    P: E4/1\n").replace("loma 1.1", "loma 1.0")
        try:
            compile_text(text)
            self.fail("no error")
        except LomaErrors as e:
            self.assertEqual([(x.code, x.line) for x in e.errors], [("E001", 8)])
            self.assertIn("loma 1.1", e.errors[0].message)


class Versions(unittest.TestCase):
    def test_new_constructs_need_1_1(self):
        old = H.replace("loma 1.1", "loma 1.0")
        self.assertEqual(errs(song("  bar C meter=3/4\n    P: C4/2.\n", head=old)), [("E020", 6)])
        self.assertEqual(errs(song("  bar C key=F\n    P: C4/1\n", head=old)), [("E020", 6)])
        self.assertEqual(errs(song("  bar C\n    P: C4/1\n", head=old) + "at 0 meter=3/4\nat 0 key=F\n"), [("E020", 10), ("E020", 11)])

    def test_older_files_give_the_same_bytes_when_they_declare_1_1(self):
        paths = [p for p in sorted(glob.glob(os.path.join(ROOT, "conformance", "valid", "*.loma")))
                 if os.path.basename(p)[0] in "0234"]
        self.assertGreaterEqual(len(paths), 90)
        checked = 0
        for path in paths:
            with open(path, "rb") as f:
                raw = f.read()
            lines = raw.split(b"\n")
            index = next(i for i, ln in enumerate(lines) if ln.lstrip(b"\xef\xbb\xbf \t").startswith(b"loma "))
            version = lines[index].split(b"#")[0].split()[1]
            lines[index] = lines[index].replace(version, b"1.1", 1)
            with open(path[:-5] + ".mid", "rb") as f:
                self.assertEqual(compile_text(b"\n".join(lines).decode("utf-8"))[1], f.read(), os.path.basename(path))
            checked += 1
        self.assertEqual(checked, len(paths))


if __name__ == "__main__":
    unittest.main()
