import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loma.api import compile_text, expand_json, sha256
from loma.errors import LomaErrors
from loma.util import floor_div, duration_ticks, vlq, bpm_to_us
from loma.errors import LomaError
from midi_reader import read_midi

HEAD = "loma 0.1\ntempo 120\nmeter 4/4\ntrack P ch=1 program=0\n"


def song(body, head=HEAD):
    return head + "section s\n" + body + "end\nplay s\n"


def codes(text):
    try:
        compile_text(text)
    except LomaErrors as e:
        return [x.code for x in e.errors]
    return []


def errs(text):
    try:
        compile_text(text)
    except LomaErrors as e:
        return e.errors
    return []


def midi_events(text):
    _, mid = compile_text(text)
    return read_midi(mid)


def notes_of(text, track=1):
    """[(start, end, pitch, vel)] for a track, using the independent reader."""
    _, _, tracks = midi_events(text)
    on, out = {}, []
    for tick, kind, st, d in tracks[track]:
        if kind != "midi":
            continue
        if st & 0xF0 == 0x90:
            on[d[0]] = (tick, d[1])
        elif st & 0xF0 == 0x80:
            s, v = on.pop(d[0])
            out.append((s, tick, d[0], v))
    return sorted(out)


class Arithmetic(unittest.TestCase):
    def test_floor_div_table(self):
        self.assertEqual(floor_div(7, 3), 2)
        self.assertEqual(floor_div(-7, 3), -3)
        self.assertEqual(floor_div(7, -3), -3)
        self.assertEqual(floor_div(-7, -3), 2)

    def test_durations(self):
        table = {"1": 1920, "2": 960, "4": 480, "8": 240, "16": 120, "32": 60, "64": 30,
                 "2.": 1440, "4.": 720, "8.": 360, "16.": 180, "32.": 90,
                 "2t": 640, "4t": 320, "8t": 160, "16t": 80, "32t": 40,
                 "4..": 840, "8..": 420, "16..": 210, "#210": 210, "64.": 45}
        for k, v in table.items():
            self.assertEqual(duration_ticks(k), v, k)
        for bad in ("64..", "3", "0", "#0"):
            with self.assertRaises(LomaError) as cm:
                duration_ticks(bad)
            self.assertEqual(cm.exception.code, "E007")

    def test_vlq_and_tempo(self):
        self.assertEqual(vlq(0), b"\x00")
        self.assertEqual(vlq(127), b"\x7f")
        self.assertEqual(vlq(128), b"\x81\x00")
        self.assertEqual(vlq(1920), b"\x8f\x00")
        self.assertEqual(vlq(0x0FFFFFFF), b"\xff\xff\xff\x7f")
        self.assertEqual([bpm_to_us(b) for b in (100, 92, 85, 77, 70)],
                         [600000, 652173, 705882, 779220, 857142])


class Bytes(unittest.TestCase):
    def test_minimal_file_byte_exact(self):
        """Expected bytes computed by hand (see README section 8)."""
        text = song("  bar C\n    P: C4/1\n")
        _, mid = compile_text(text)
        expected = bytes.fromhex(
            "4D546864 00000006 0001 0002 01E0"
            "4D54726B 00000014 00FF580404021808 00FF510307A120 8F00FF2F00"
            "4D54726B 00000016 00FF030150 00C000 00903C50 8D40803C40 8140FF2F00".replace(" ", ""))
        self.assertEqual(mid, expected)

    def test_reader_roundtrip_structure(self):
        fmt, div, tracks = midi_events(song("  bar C\n    P: C4/1\n"))
        self.assertEqual((fmt, div, len(tracks)), (1, 480, 2))


class Determinism(unittest.TestCase):
    def test_100_runs_same_hash(self):
        with open(os.path.join(ROOT, "examples", "example.loma"), encoding="utf-8") as f:
            text = f.read()
        hashes = {sha256(compile_text(text)[1]) for _ in range(100)}
        self.assertEqual(len(hashes), 1)

    def test_other_hash_seeds(self):
        path = os.path.join(ROOT, "examples", "example.loma")
        out = set()
        for seed in ("0", "1", "42", "random"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            r = subprocess.run([sys.executable, "-m", "loma", "hash", path], cwd=ROOT, env=env,
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            out.add(r.stdout.strip())
        self.assertEqual(len(out), 1)


class Tempo(unittest.TestCase):
    RAMP = song("  bar C tempo=100>70\n    P: C4/1\n  bar C\n    P: C4/1\n", HEAD.replace("tempo 120", "tempo 100"))

    def tempos(self, text):
        _, _, tracks = midi_events(text)
        return [(t, int.from_bytes(d, "big")) for t, k, kind, d in tracks[0] if k == "meta" and kind == 0x51]

    def test_ramp_values(self):
        got = self.tempos(self.RAMP)
        self.assertEqual(got, [(0, 600000), (480, 652173), (960, 705882), (1440, 779220), (1920, 857142)])

    def test_ramp_holds_final_tempo(self):
        got = self.tempos(self.RAMP)
        self.assertEqual(got[-1], (1920, 857142))       # second bar stays at 70 BPM

    def test_same_tick_last_wins(self):
        text = song("  bar C tempo=100>70\n    P: C4/1\n  bar C tempo=90\n    P: C4/1\n")
        got = self.tempos(text)
        self.assertEqual([t for t, _ in got].count(1920), 1)
        self.assertEqual(dict(got)[1920], bpm_to_us(90))

    def test_first_bar_overrides_initial_tempo(self):
        text = song("  bar C tempo=80\n    P: C4/1\n")
        self.assertEqual(self.tempos(text), [(0, bpm_to_us(80))])

    def test_accelerando_uses_floor(self):
        text = song("  bar C tempo=70>100\n    P: C4/1\n")
        self.assertEqual([b for _, b in self.tempos(text)], [bpm_to_us(x) for x in (70, 77, 85, 92, 100)])

    def test_ramp_in_3_8(self):
        text = song("  bar C tempo=100>70\n    P: C4/4.\n", HEAD.replace("4/4", "3/8"))
        # 720 ticks: events at 0 and 480, then final at 720
        self.assertEqual([t for t, _ in self.tempos(text)], [0, 480, 720])


class Notes(unittest.TestCase):
    def test_articulation_and_gate(self):
        text = song("  bar C\n    P: C4/4 C4/4{a=leg} C4/4{a=stac} C4/4{d=100}\n")
        n = notes_of(text)
        self.assertEqual([e - s for s, e, p, v in n], [432, 480, 240, 100])

    def test_offset_and_clamp(self):
        text = song("  bar C\n    P: C4/4{o=-10} D4/4{o=7} E4/2\n")
        n = notes_of(text)
        self.assertEqual(n[0][0], 0)                      # clamped to 0
        self.assertEqual(n[1][0], 487)
        self.assertEqual(n[2][0], 960)                    # cursor not moved by offsets

    def test_velocity_precedence(self):
        text = song("  bar C\n    P{v=50}: [C4 E4{v=70} G4]/1{v=60}\n")
        vel = {p: v for s, e, p, v in notes_of(text)}
        self.assertEqual(vel, {60: 60, 64: 70, 67: 60})

    def test_tie_merges(self):
        text = song("  bar C\n    P: C4/2~ C4/4~ C4/4\n")
        n = notes_of(text)
        self.assertEqual(len(n), 1)
        self.assertEqual((n[0][0], n[0][1]), (0, 1728))   # 1920 * 90 // 100

    def test_tie_across_bars(self):
        text = song("  bar C\n    P: r/2 C4/2~\n  bar C\n    P: C4/1\n")
        n = notes_of(text)
        self.assertEqual(len(n), 1)

    def test_overlap_trims_previous(self):
        text = song("  bar C\n    P: C4/4{a=leg} C4/4{o=-12} r/2\n")
        n = notes_of(text)
        self.assertEqual(n[0][1], n[1][0])                # first note ends where the second starts

    def test_pedal_events(self):
        _, _, tracks = midi_events(song("  bar C\n    P: pedal+ C4/1 pedal-\n"))
        cc = [(t, d) for t, k, st, d in tracks[1] if k == "midi" and st & 0xF0 == 0xB0]
        self.assertEqual(cc, [(0, (64, 127)), (1920, (64, 0))])

    def test_drums(self):
        head = HEAD + "track D drums\n"
        text = song("  bar C\n    D: kick/4 hat/8 hat/8 snare/4 hat/4\n", head)
        _, _, tracks = midi_events(text)
        pitches = [d[0] for t, k, st, d in tracks[2] if k == "midi" and st == 0x99]
        self.assertEqual(pitches, [36, 42, 42, 38, 42])

    def test_transpose_and_repeat(self):
        text = HEAD + "section a\n  bar C\n    P: C4/1\nend\nplay a x2 transpose=+2\n"
        n = notes_of(text)
        self.assertEqual([(s, p) for s, e, p, v in n], [(0, 62), (1920, 62)])

    def test_at_event(self):
        text = song("  bar C\n    P: C4/1\n") + "at 3840 P E4 d=200 v=90\n"
        n = notes_of(text)
        self.assertIn((3840, 4040, 64, 90), n)

    def test_chord_tones_sus4(self):
        # tone 3 is the SECOND chord note (F in Csus4), not a scale degree
        text = HEAD + "pattern p base=4 dur=/1 : 3\nsection a\n  bar Csus4\n    P: use p\nend\nplay a\n"
        self.assertEqual([p for s, e, p, v in notes_of(text)], [65])


class MultiChordBars(unittest.TestCase):
    def test_pattern_restarts_per_segment(self):
        text = HEAD + "pattern p base=3 dur=/4 : 1 3\nsection a\n  bar Cm Ab\n    P: use p\nend\nplay a\n"
        n = notes_of(text)
        self.assertEqual([(s, p) for s, e, p, v in n],
                         [(0, 48), (480, 51), (960, 56), (1440, 60)])

    def test_three_chords_640(self):
        text = HEAD + "pattern p base=3 dur=/4t : 1\nsection a\n  bar C F G\n    P: use p\nend\nplay a\n"
        n = notes_of(text)
        # 1920 / 3 = 640 ticks per chord; the 320-tick pattern repeats twice in each
        self.assertEqual([s for s, e, p, v in n], [0, 320, 640, 960, 1280, 1600])
        self.assertEqual([p for s, e, p, v in n], [48, 48, 53, 53, 55, 55])

    def test_explicit_notes_cross_boundary(self):
        text = song("  bar Cm Ab\n    P: C4/1\n")
        self.assertEqual(len(notes_of(text)), 1)


class Errors(unittest.TestCase):
    def test_E001_syntax(self):
        self.assertIn("E001", codes("tempo 120\n"))
        self.assertIn("E001", codes(song("  bar C\n    P: C4/4C4/4\n")))
        self.assertIn("E001", codes(song("  bar C\n    P: C4\n")))
        self.assertIn("E001", codes(song("  bar C\n    P: H4/1\n")))
        self.assertIn("E001", codes(song("  bar C\n    P: C4/1{x=1}\n")))

    def test_E002_unknown_command(self):
        self.assertIn("E002", codes(HEAD + "banana 3\n"))

    def test_E003_with_numbers(self):
        e = errs(song("  bar C\n    P: C4/2 C4/4 C4/8\n"))[0]
        self.assertEqual(e.code, "E003")
        self.assertEqual((e.ctx["expected"], e.ctx["got"], e.ctx["missing"]), (1920, 1680, 240))
        self.assertEqual(e.ctx["duration"], "/8")
        self.assertIn("Missing 240 ticks (= /8)", e.message)
        self.assertIn("E003 line 7 bar 1 (C) track P:", e.format())

    def test_E003_excess(self):
        e = errs(song("  bar C\n    P: C4/1 C4/4\n"))[0]
        self.assertEqual(e.ctx["excess"], 480)

    def test_E004(self):
        self.assertIn("E004", codes(song("  bar C\n    P: use nope\n")))
        self.assertIn("E004", codes(HEAD + "play nothing\n"))

    def test_E005(self):
        self.assertIn("E005", codes(song("  bar Cxyz\n    P: C4/1\n")))

    def test_E006(self):
        self.assertIn("E006", codes(song("  bar C\n    P: C10/1\n")))
        text = HEAD + "section a\n  bar C\n    P: C4/1\nend\nplay a transpose=+80\n"
        self.assertIn("E006", codes(text))

    def test_E007(self):
        self.assertIn("E007", codes(song("  bar C\n    P: C4/64..\n")))
        self.assertIn("E007", codes(song("  bar C\n    P: C4/3\n")))

    def test_E008(self):
        self.assertIn("E008", codes(song("  bar C\n    X: C4/1\n")))

    def test_E009(self):
        text = HEAD + "pattern p base=3 dur=/4 : 1 3 5\nsection a\n  bar C\n    P: use p\nend\nplay a\n"
        self.assertIn("E009", codes(text))

    def test_E010(self):
        text = HEAD + "pattern p base=3 dur=/1 : 7\nsection a\n  bar C\n    P: use p\nend\nplay a\n"
        self.assertIn("E010", codes(text))
        self.assertIn("E010", codes(HEAD + "pattern p base=3 dur=/1 : 4\n"))

    def test_E011(self):
        self.assertIn("E011", codes(HEAD + "track Q ch=1\n"))
        self.assertIn("E011", codes(HEAD + "track Q ch=10\n"))
        self.assertIn("E011", codes(HEAD + "track D drums\ntrack E drums\n"))

    def test_E012(self):
        self.assertIn("E012", codes(song("  bar C\n    P: C4/2~ D4/2\n")))                      # different pitch
        self.assertIn("E012", codes(song("  bar C\n    P: C4/2~ C4/2{v=90}\n")))            # attrs on tied note
        self.assertIn("E012", codes(song("  bar C\n    P: C4/2 C4/2~\n")))                  # no next note
        self.assertIn("E012", codes(song("  bar C\n    P: C4/4~ r/4 C4/2\n")))              # not contiguous
        self.assertIn("E012", codes(song("  bar C\n    P: C4/2 r/4 r/8 r/8~\n")))           # tied rest

    def test_E012_across_plays(self):
        text = HEAD + "section a\n  bar C\n    P: C4/1~\nend\nsection b\n  bar C\n    P: C4/1\nend\nplay a\nplay b\n"
        self.assertIn("E012", codes(text))

    def test_E013(self):
        self.assertIn("E013", codes(HEAD + "key G#\n"))
        self.assertIn("E013", codes(HEAD + "key H\n"))

    def test_E014(self):
        text = HEAD + "section a\n  bar C F len=/#7\n    P: C4/#7\nend\nplay a\n"
        self.assertIn("E014", codes(text))

    def test_E015(self):
        self.assertIn("E015", codes("loma 0.1\ntempo 500\n"))
        self.assertIn("E015", codes(song("  bar C tempo=100>2\n    P: C4/1\n")))

    def test_E016(self):
        text = HEAD + "pattern p base=3 dur=/4 : 1\nsection a\n  bar C\n    P: use p C4/4\nend\nplay a\n"
        self.assertIn("E016", codes(text))
        text = HEAD + "pattern p base=3 dur=/4 : 1\nsection a\n  bar C\n    P: C4/4 use p\nend\nplay a\n"
        self.assertIn("E016", codes(text))

    def test_E017(self):
        self.assertIn("E017", codes(song("  bar C\n    P: [C4 C4]/1\n")))

    def test_E018(self):
        self.assertIn("E018", codes(HEAD.replace("4/4", "4/3")))
        self.assertIn("E018", codes(HEAD.replace("4/4", "65/4")))
        self.assertIn("E018", codes(HEAD + "section a\n  bar C\n    P: C4/1\nend\nplay a x1001\n"))
        self.assertIn("E018", codes(song("  bar C\n    P: C4/1\n") + "at 268435456 P C4 d=1\n"))

    def test_E019(self):
        self.assertIn("E019", codes(HEAD + "track P ch=2\n"))
        self.assertIn("E019", codes(HEAD + "section a\nend\nsection a\nend\n"))
        self.assertIn("E019", codes(HEAD + "track 1bad ch=3\n"))

    def test_reports_all_errors_at_once(self):
        # semantic errors: all reported together, one per bar
        text = song("  bar C\n    P: C4/2\n  bar C\n    P: use nope\n  bar C\n    P: C4/1 C4/4\n")
        self.assertEqual(sorted(codes(text)), ["E003", "E003", "E004"])
        # syntax errors and the bar checks on the readable lines: reported in the same round
        text = song("  bar Cxyz\n    P: C4/1\n  bar C\n    P: H4/1\n  bar C\n    P: C4/2\n")
        self.assertEqual(sorted(codes(text)), ["E001", "E003", "E005"])

    def test_json_error_form(self):
        import json
        e = errs(song("  bar C\n    P: C4/2 C4/4 C4/8\n"))[0]
        d = json.loads(json.dumps(e.to_dict()))
        self.assertEqual((d["code"], d["track"], d["expected"], d["got"], d["missing"]), ("E003", "P", 1920, 1680, 240))


class Misc(unittest.TestCase):
    def test_sharp_is_not_a_comment(self):
        text = song("  bar C  # a comment\n    P: F#3/1 # another\n")
        self.assertEqual([p for s, e, p, v in notes_of(text)], [54])

    def test_key_signature_bytes(self):
        text = song("  bar C\n    P: C4/1\n").replace("tempo 120", "tempo 120\nkey Cm")
        _, _, tracks = midi_events(text)
        ks = [d for t, k, kind, d in tracks[0] if k == "meta" and kind == 0x59]
        self.assertEqual(ks, [bytes([0xFD, 1])])          # -3 flats, minor

    def test_title_in_conductor(self):
        text = song("  bar C\n    P: C4/1\n").replace("tempo 120", 'title "Prova"\ntempo 120')
        _, _, tracks = midi_events(text)
        self.assertEqual(tracks[0][0], (0, "meta", 0x03, b"Prova"))

    def test_end_of_track_everywhere_same_tick(self):
        _, _, tracks = midi_events(song("  bar C\n    P: C4/1\n") + "track Q ch=3\n")
        ends = {t[-1][0] for t in tracks}
        self.assertEqual(len(ends), 1)

    def test_expand_json_canonical(self):
        out = expand_json(song("  bar C\n    P{v=70}: C4/1\n"))
        self.assertTrue(out.startswith('[{"bpm":120,"tick":0,"type":"tempo"},{"ch":1,"pitch":60,"tick":0,"track":"P","type":"note_on","vel":70}'))
        self.assertTrue(out.endswith("]\n"))

    def test_unplayed_section_is_validated(self):
        text = HEAD + "section a\n  bar C\n    P: C4/2\nend\n"
        self.assertEqual(codes(text), ["E003"])

    def test_sequence_numbers_per_track(self):
        c, _ = compile_text(song("  bar C\n    P: C4/2 D4/2\n"))
        seqs = [(e.kind, e.seq) for e in c.events if e.track == 0]
        self.assertEqual(seqs, [("note_on", 0), ("note_off", 1), ("note_on", 2), ("note_off", 3)])


if __name__ == "__main__":
    unittest.main()
