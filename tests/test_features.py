"""Features added after 0.1. Expected values are computed by hand from the specification."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loma.api import compile_text, expand_json, sha256
from loma.errors import LomaError, LomaErrors
from loma.util import duration_ticks
from midi_reader import read_midi

H = "loma 1.0\ntempo 120\nmeter 4/4\ntrack P ch=1 program=0\n"


def song(body, head=H, extra=""):
    return head + extra + "section s\n" + body + "end\nplay s\n"


def errs(text):
    try:
        compile_text(text)
    except LomaErrors as e:
        return e.errors
    return []


def codes(text):
    return [e.code for e in errs(text)]


def tracks_of(text):
    return read_midi(compile_text(text)[1])[2]


def notes_of(text, track=1):
    on, out = {}, []
    for tick, kind, st, d in tracks_of(text)[track]:
        if kind != "midi":
            continue
        if st & 0xF0 == 0x90:
            on[d[0]] = (tick, d[1])
        elif st & 0xF0 == 0x80:
            s, v = on.pop(d[0])
            out.append((s, tick, d[0], v))
    return sorted(out)


def channel_events(text, hi, track=1):
    return [(t, d) for t, k, st, d in tracks_of(text)[track] if k == "midi" and st & 0xF0 == hi]


class Controls(unittest.TestCase):
    def test_cc_single(self):
        self.assertEqual(channel_events(song("  bar C\n    P: cc7=100 C4/2 cc7=64 C4/2\n"), 0xB0),
                         [(0, (7, 100)), (960, (7, 64))])

    def test_cc_ramp_up(self):
        got = channel_events(song("  bar C\n    P: cc11=0>120/2 C4/1\n"), 0xB0)
        self.assertEqual([t for t, _ in got], [60 * k for k in range(16)] + [960])
        self.assertEqual([d[1] for _, d in got],
                         [0, 7, 15, 22, 30, 37, 45, 52, 60, 67, 75, 82, 90, 97, 105, 112, 120])

    def test_cc_ramp_down_uses_floor(self):
        got = channel_events(song("  bar C\n    P: cc1=10>0/4 C4/1\n"), 0xB0)
        self.assertEqual([d[1] for _, d in got], [10, 8, 7, 6, 5, 3, 2, 1, 0])
        self.assertEqual(got[-1][0], 480)

    def test_ramp_does_not_move_the_cursor(self):
        n = notes_of(song("  bar C\n    P: cc7=0>100/1 C4/2 D4/2\n"))
        self.assertEqual([s for s, e, p, v in n], [0, 960])

    def test_bend_bytes(self):
        got = channel_events(song("  bar C\n    P: bend=0 C4/4 bend=8191 C4/4 bend=-8192 C4/4 bend=-1 C4/4\n"), 0xE0)
        self.assertEqual([d for _, d in got], [(0, 64), (127, 127), (0, 0), (127, 63)])

    def test_control_ranges(self):
        self.assertIn("E001", codes(song("  bar C\n    P: cc128=1 C4/1\n")))
        self.assertIn("E001", codes(song("  bar C\n    P: cc7=128 C4/1\n")))
        self.assertIn("E001", codes(song("  bar C\n    P: bend=8192 C4/1\n")))
        self.assertIn("E001", codes(song("  bar C\n    P: cc7=1>2 C4/1\n")))       # ramp needs a duration

    def test_pedal_is_cc64(self):
        self.assertEqual(expand_json(song("  bar C\n    P: pedal+ C4/1\n")),
                         expand_json(song("  bar C\n    P: cc64=127 C4/1\n")))

    def test_control_before_note_on_same_tick(self):
        kinds = [st & 0xF0 for t, k, st, d in tracks_of(song("  bar C\n    P: C4/2 cc7=1 C4/2\n"))[1] if k == "midi" and t == 960]
        self.assertEqual(kinds, [0xB0, 0x90])


class Dynamics(unittest.TestCase):
    def test_velocity_ramp(self):
        n = notes_of(song("  bar C\n    P{v=60>100}: C4/4 D4/4 E4/4{v=30} F4/4\n"))
        self.assertEqual([v for s, e, p, v in n], [60, 70, 30, 90])

    def test_velocity_ramp_down_floor(self):
        n = notes_of(song("  bar C\n    P{v=100>65}: C4/4 D4/4 E4/4 F4/4\n"))
        self.assertEqual([v for s, e, p, v in n], [100, 91, 82, 73])     # -8.75 -> -9, -26.25 -> -27

    def test_velocity_ramp_on_pattern(self):
        text = H + "pattern p base=3 dur=/4 : 1 3 5 3\nsection s\n  bar C\n    P{v=40>80}: use p\nend\nplay s\n"
        self.assertEqual([v for s, e, p, v in notes_of(text)], [40, 50, 60, 70])

    def test_swing_table(self):
        text = song("  bar C\n    P{swing=sh}: C4/8 D4/8{o=-10} E4/8 F4/8 G4/2\n", extra="swing sh grid=/8 : 0 40\n")
        self.assertEqual([s for s, e, p, v in notes_of(text)], [0, 270, 480, 760, 960])

    def test_swing_ignores_off_grid_notes(self):
        text = song("  bar C\n    P{swing=sh}: C4/8 D4/8 E4/2.\n", extra="swing sh grid=/4 : 30\n")
        self.assertEqual([s for s, e, p, v in notes_of(text)], [30, 240, 510])

    def test_swing_undefined(self):
        self.assertEqual(codes(song("  bar C\n    P{swing=nope}: C4/1\n")), ["E004"])

    def test_ramp_and_swing_only_at_line_level(self):
        self.assertIn("E001", codes(song("  bar C\n    P: C4/1{v=1>9}\n")))
        self.assertIn("E001", codes(song("  bar C\n    P: C4/1{swing=x}\n")))


class Layout(unittest.TestCase):
    def test_multi_line_content(self):
        one = song("  bar C\n    P{v=70}: C4/4 D4/4 E4/4 F4/4\n")
        many = song("  bar C\n    P{v=70}:\n      C4/4 D4/4\n      E4/4\n      F4/4\n")
        self.assertEqual(expand_json(one), expand_json(many))

    def test_error_line_of_continuation(self):
        e = errs(song("  bar C\n    P:\n      C4/4 D4/4\n      E4/4\n"))[0]
        self.assertEqual((e.code, e.line, e.ctx["missing"]), ("E003", 9, 480))

    def test_segments(self):
        n = notes_of(song("  bar C F\n    P: C4/2 | F4/4 A4/4\n"))
        self.assertEqual([(s, p) for s, e, p, v in n], [(0, 60), (960, 65), (1440, 69)])

    def test_segment_mixes_pattern_and_notes(self):
        text = H + "pattern p base=3 dur=/4 : 1 3\nsection s\n  bar C F\n    P: use p | C4/2\nend\nplay s\n"
        self.assertEqual([(s, p) for s, e, p, v in notes_of(text)], [(0, 48), (480, 52), (960, 60)])
        text = H + "pattern p base=3 dur=/4 : 1 3\nsection s\n  bar C F\n    P: C4/2 | use p\nend\nplay s\n"
        self.assertEqual([(s, p) for s, e, p, v in notes_of(text)], [(0, 60), (960, 53), (1440, 57)])

    def test_segment_errors(self):
        e = errs(song("  bar C F\n    P: C4/2 | F4/4\n"))[0]
        self.assertEqual((e.code, e.ctx["expected"], e.ctx["got"]), ("E003", 960, 480))
        e = errs(song("  bar C F\n    P: C4/4 | F4/4 | G4/2\n"))[0]
        self.assertEqual((e.code, e.ctx["expected"], e.ctx["got"]), ("E021", 2, 3))
        self.assertEqual(codes(song("  bar C\n    P: C4/2 | C4/2\n")), ["E021"])
        self.assertEqual(codes(song("  bar C F\n    P: use p C4/4 | F4/2\n")), ["E016"])

    def test_pattern_list(self):
        text = H + "pattern a base=3 dur=/4 : 1\npattern b base=3 dur=/4 : 5\nsection s\n  bar C\n    P: use a,b\nend\nplay s\n"
        self.assertEqual([(s, p) for s, e, p, v in notes_of(text)], [(0, 48), (480, 55), (960, 48), (1440, 55)])

    def test_pattern_list_must_fit(self):
        text = H + "pattern a base=3 dur=/4 : 1\npattern b base=3 dur=/2 : 5\nsection s\n  bar C len=/#2400\n    P: use a,b\nend\nplay s\n"
        self.assertEqual(codes(text), ["E009"])

    def test_pattern_from(self):
        text = H + "pattern a base=3 dur=/4 : 1 3 5 3\npattern b from a : 4=8 2=r\nsection s\n  bar C\n    P: use b\nend\nplay s\n"
        self.assertEqual([(s, p) for s, e, p, v in notes_of(text)], [(0, 48), (960, 55), (1440, 60)])

    def test_pattern_from_keeps_duration_unless_given(self):
        text = H + "pattern a base=3 dur=/4 : 1 3 5 3\npattern b from a base=4 : 1=(1 5)/2{v=99}\nsection s\n  bar C len=/#2400\n    P: use b\nend\nplay s\n"
        n = notes_of(text)
        self.assertEqual([(s, p, v) for s, e, p, v in n][:3], [(0, 60, 99), (0, 67, 99), (960, 64, 80)])

    def test_pattern_from_errors(self):
        self.assertEqual(codes(H + "pattern b from a : 1=3\n"), ["E004"])
        self.assertEqual(codes(H + "pattern a base=3 dur=/4 : 1 3\npattern b from a : 3=1\n"), ["E001"])

    def test_tuplets(self):
        self.assertEqual(duration_ticks("8q"), 192)
        self.assertEqual(duration_ticks("16q"), 96)
        self.assertEqual(duration_ticks("4x5/4"), 384)
        self.assertEqual(duration_ticks("4x3/2"), duration_ticks("4t"))
        for bad in ("8x7/4", "4x0/1", "16x9/8"):
            with self.assertRaises(LomaError) as cm:
                duration_ticks(bad)
            self.assertEqual(cm.exception.code, "E007", bad)
        n = notes_of(song("  bar C\n    P: C4/8q D4/8q E4/8q F4/8q G4/8q C4/2\n"))
        self.assertEqual([s for s, e, p, v in n], [0, 192, 384, 576, 768, 960])

    def test_repeat_blocks(self):
        body = "  repeat 2\n    bar C\n      P: C4/1\n    repeat 2\n      bar F\n        P: F4/1\n    end\n  end\n  bar G\n    P: G4/1\n"
        n = notes_of(song(body))
        self.assertEqual([p for s, e, p, v in n], [60, 65, 65, 60, 65, 65, 67])
        self.assertEqual([s for s, e, p, v in n], [1920 * k for k in range(7)])

    def test_repeat_errors(self):
        self.assertEqual(codes(song("  repeat 1001\n    bar C\n      P: C4/1\n  end\n")), ["E018"])
        self.assertEqual(codes(song("  repeat\n    bar C\n      P: C4/1\n  end\n")), ["E001"])
        self.assertEqual(codes(H + "section s\n  repeat 2\n    bar C\n      P: C4/1\nend\n"), ["E001"])

    def test_bar_limit(self):
        body = "  repeat 1000\n    repeat 101\n      bar C\n        P: C4/1\n    end\n  end\n"
        self.assertEqual(codes(song(body)), ["E018"])

    def test_error_bar_numbers_are_static(self):
        body = "  repeat 3\n    bar C\n      P: C4/1\n    bar F\n      P: F4/2\n  end\n"
        e = errs(song(body))
        self.assertEqual([(x.code, x.ctx["bar"]) for x in e], [("E003", 2)])


class Harmony(unittest.TestCase):
    def pattern(self, chord, tones, base=3):
        text = H + "pattern p base=%d dur=/1 : (%s)\nsection s\n  bar %s\n    P: use p\nend\nplay s\n" % (base, tones, chord)
        return [p for s, e, p, v in notes_of(text)]

    def test_extended_chords(self):
        self.assertEqual(self.pattern("Cmaj9", "1 3 5 7 9"), [48, 52, 55, 59, 62])
        self.assertEqual(self.pattern("C13", "1 11"), [48, 69])
        self.assertEqual(self.pattern("Dm7b5", "1 3 5 7"), [50, 53, 56, 60])
        self.assertEqual(self.pattern("C5", "1 3"), [48, 55])
        self.assertEqual(self.pattern("C7#9", "9"), [63])
        self.assertEqual(self.pattern("Cmaj9", "16"), [74])

    def test_tone_out_of_chord(self):
        text = H + "pattern p base=3 dur=/1 : 9\nsection s\n  bar C7\n    P: use p\nend\nplay s\n"
        self.assertEqual(codes(text), ["E010"])
        self.assertEqual(codes(H + "pattern p base=3 dur=/1 : 13\n"), ["E010"])
        self.assertEqual(codes(H + "pattern p base=3 dur=/1 : 2\n"), ["E010"])

    def test_slash_chord_and_bass_tone(self):
        self.assertEqual(self.pattern("C/E", "0 1 3 5"), [40, 48, 52, 55])
        self.assertEqual(self.pattern("C", "0"), [36])
        self.assertEqual(self.pattern("Am7/G", "0"), [43])
        self.assertEqual(self.pattern("C/Bb", "0"), [46])

    def test_inversions(self):
        self.assertEqual(self.pattern("C^1", "1 3 5"), [52, 55, 60])
        self.assertEqual(self.pattern("C^2", "1 3 5"), [55, 60, 64])
        self.assertEqual(self.pattern("C^1", "0"), [40])              # the bass follows the inversion
        self.assertEqual(self.pattern("Cmaj7^3/G", "0 1"), [43, 59])
        self.assertEqual(codes(song("  bar C^3\n    P: C4/1\n")), ["E005"])

    def test_octave_marks_values(self):
        text = H + "pattern p base=3 dur=/4 : 1- 5+ 8-- 3\nsection s\n  bar C\n    P: use p\nend\nplay s\n"
        self.assertEqual([p for s, e, p, v in notes_of(text)], [36, 67, 36, 52])

    def test_voicing(self):
        text = song("  bar Cm F\n    P{v=64}: *open/2 *open/2\n", extra="voicing open base=3 : 1 5 10\n")
        self.assertEqual([(s, p) for s, e, p, v in notes_of(text)],
                         [(0, 48), (0, 55), (0, 63), (960, 53), (960, 60), (960, 69)])

    def test_voicing_tie_and_transpose(self):
        text = H + "voicing v base=4 : 1 5\nsection s\n  bar C\n    P: *v/2~ *v/2\nend\nplay s transpose=+2\n"
        self.assertEqual([(s, e, p) for s, e, p, v in notes_of(text)], [(0, 1728, 62), (0, 1728, 69)])

    def test_voicing_errors(self):
        self.assertEqual(codes(song("  bar C\n    P: *nope/1\n")), ["E004"])
        self.assertEqual(codes(song("  bar C\n    P: *v/1\n", extra="voicing v base=3 : 7\n")), ["E010"])
        self.assertEqual(codes(song("  bar C\n    P: *v/1\n", extra="voicing v base=9 : 8\n")), ["E006"])

    def test_unknown_quality(self):
        self.assertEqual(codes(song("  bar Cmaj13\n    P: C4/1\n")), ["E005"])
        self.assertEqual(codes(song("  bar C/H\n    P: C4/1\n")), ["E005"])


class Versions(unittest.TestCase):
    def gate(self, version, body, extra=""):
        return [(e.code, e.ctx.get("requires")) for e in errs(song(body, H.replace("loma 1.0", "loma " + version), extra))]

    def test_0_2_features_need_0_2(self):
        for body in ("  bar C\n    P: cc7=1 C4/1\n", "  bar C\n    P: bend=0 C4/1\n", "  bar C\n    P{v=1>9}: C4/1\n",
                     "  bar C\n    P:\n      C4/1\n", "  bar C F\n    P: C4/2 | F4/2\n", "  bar C\n    P: C4/4x5/4 r/#1536\n",
                     "  repeat 2\n    bar C\n      P: C4/1\n  end\n"):
            self.assertEqual(self.gate("0.1", body), [("E020", "0.2")], body)
            self.assertEqual(self.gate("0.2", body), [], body)
        self.assertEqual(self.gate("0.1", "", "swing s grid=/8 : 0 1\n"), [("E020", "0.2")])

    def test_0_3_features_need_0_3(self):
        for body in ("  bar C/E\n    P: C4/1\n", "  bar C9\n    P: C4/1\n", "  bar C^1\n    P: C4/1\n"):
            self.assertEqual(self.gate("0.2", body), [("E020", "0.3")], body)
            self.assertEqual(self.gate("0.3", body), [], body)
        self.assertEqual(self.gate("0.2", "", "voicing v base=3 : 1\n"), [("E020", "0.3")])
        self.assertEqual(self.gate("0.2", "", "pattern p base=3 dur=/4 : 0\n"), [("E020", "0.3")])
        self.assertEqual(self.gate("0.2", "", "pattern p base=3 dur=/4 : 1+\n"), [("E020", "0.3")])

    def test_1_0_features_need_1_0(self):
        for body in ('  bar C\n    P: "la" C4/1\n', "  bar C\n    P: m60/1\n"):
            self.assertEqual(self.gate("0.3", body), [("E020", "1.0")], body)
        head = H.replace("loma 1.0", "loma 0.3")
        self.assertEqual(codes(song("  bar C\n    P: C4/1\n", head) + "at 0 tempo=90\n"), ["E020"])
        self.assertEqual(codes(song("  bar C\n    P: C4/1\n", head) + "at 0 P cc7=1\n"), ["E020"])
        self.assertEqual(codes(song("  bar C\n    P: C4/1\n", head) + "at 0 P E4 d=10\n"), [])

    def test_unknown_version(self):
        self.assertEqual(codes("loma 2.0\n"), ["E001"])
        self.assertEqual(codes("loma\n"), ["E001"])


class OneZero(unittest.TestCase):
    def test_lyrics(self):
        tr = tracks_of(song('  bar C\n    P: "Do re" C4/2 "mi" C4/2\n'))[1]
        self.assertEqual([(t, d) for t, k, kind, d in tr if k == "meta" and kind == 0x05], [(0, b"Do re"), (960, b"mi")])

    def test_lyric_with_special_characters(self):
        tr = tracks_of(song('  bar C\n    P: "a | b # c: d{e}" C4/1\n'))[1]
        self.assertEqual([d for t, k, kind, d in tr if k == "meta" and kind == 0x05], ["a | b # c: d{e}".encode()])
        tr = tracks_of(song('  bar C\n    P: "più" C4/1\n'))[1]
        self.assertEqual([d for t, k, kind, d in tr if k == "meta" and kind == 0x05], ["più".encode("utf-8")])

    def test_numeric_pitch(self):
        head = H + "track D drums\n"
        text = song("  bar C\n    P: m60/2 [m61 m62]/2\n    D: m35/2 kick/2\n", head)
        self.assertEqual([p for s, e, p, v in notes_of(text)], [60, 61, 62])
        self.assertEqual([p for s, e, p, v in notes_of(text, 2)], [35, 36])
        self.assertEqual(codes(song("  bar C\n    P: m128/1\n")), ["E006"])

    def test_at_forms(self):
        text = song("  bar C\n    P: C4/1\n") + 'at 100 P cc7=90\nat 100 P bend=-100\nat 200 P "la"\nat 960 tempo=90\nat 0 tempo=100\n'
        tr = tracks_of(text)
        self.assertEqual([(t, int.from_bytes(d, "big")) for t, k, kind, d in tr[0] if k == "meta" and kind == 0x51],
                         [(0, 600000), (960, 666666)])
        self.assertIn((100, "midi", 0xB0, (7, 90)), tr[1])
        self.assertIn((100, "midi", 0xE0, (28, 63)), tr[1])
        self.assertIn((200, "meta", 0x05, b"la"), tr[1])

    def test_at_errors(self):
        base = song("  bar C\n    P: C4/1\n")
        self.assertEqual(codes(base + "at 0 P cc7=1>9\n"), ["E001"])
        self.assertEqual(codes(base + "at 0 tempo=1\n"), ["E015"])
        self.assertEqual(codes(base + 'at 0 P ""\n'), ["E001"])
        self.assertEqual(codes(base + "at 0 X C4 d=1\n"), ["E008"])
        self.assertEqual(codes(base + "at 0 P\n"), ["E001"])
        self.assertEqual(codes(base + "at 0 P C4\n"), ["E001"])

    def test_number_too_large(self):
        base = song("  bar C\n    P: C4/1\n")
        self.assertEqual(codes(base + "at 99999999999999999999 P C4 d=1\n"), ["E018"])
        self.assertEqual(codes(song("  bar C\n    P: C4/#9999999999\n")), ["E018"])
        self.assertEqual(codes(song("  bar C\n    P: C4/1{o=12345678901}\n")), ["E018"])

    def test_reserved_names(self):
        for name in ("bar", "use", "r", "play", "repeat", "drums"):
            self.assertEqual(codes(H + "track %s ch=2\n" % name), ["E019"], name)
        self.assertEqual(codes(H + "pattern end base=3 dur=/4 : 1\n"), ["E019"])
        self.assertEqual(codes(H + "section tempo\nend\n"), ["E019"])


class Robustness(unittest.TestCase):
    BASE = song("  bar C\n    P: C4/2 D4/2\n")

    def test_crlf_and_bom_give_the_same_bytes(self):
        ref = sha256(compile_text(self.BASE)[1])
        self.assertEqual(sha256(compile_text(self.BASE.replace("\n", "\r\n"))[1]), ref)
        self.assertEqual(sha256(compile_text("\ufeff" + self.BASE)[1]), ref)
        self.assertEqual(sha256(compile_text(self.BASE.replace("    P:", "\tP:\t").replace("C4/2 D4/2", "C4/2\t D4/2"))[1]), ref)

    def test_only_space_and_tab_are_whitespace(self):
        self.assertEqual(codes(self.BASE.replace("C4/2 D4/2", "C4/2\u00a0D4/2")), ["E001"])
        self.assertEqual(codes(self.BASE.replace("C4/2 D4/2", "C4/2\u3000D4/2")), ["E001"])

    def test_only_ascii_digits(self):
        self.assertEqual(codes(self.BASE.replace("tempo 120", "tempo \u0661\u0662\u0660")), ["E001"])
        self.assertEqual(codes(self.BASE.replace("C4/2 D4/2", "C\u0664/2 D4/2")), ["E001"])

    def test_missing_end_reports_once(self):
        text = H + "section a\n  bar C\n    P: C4/1\nsection b\n  bar C\n    P: C4/1\nend\nplay a\nplay b\n"
        e = errs(text)
        self.assertEqual([(x.code, x.line) for x in e], [("E001", 8)])

    def test_unclosed_section_at_eof(self):
        e = errs(H + "section a\n  bar C\n    P: C4/1\n")
        self.assertEqual([(x.code, x.line) for x in e], [("E001", 5)])

    def test_bad_bar_does_not_cascade(self):
        e = errs(song("  bar Cxyz\n    P: C4/1\n    Q: C4/1\n      C4/4\n  bar C\n    P: C4/1\n"))
        self.assertEqual([(x.code, x.line) for x in e], [("E005", 6)])

    def test_bad_track_line_does_not_cascade(self):
        e = errs(song("  bar C\n    X:\n      C4/1\n      C4/1\n"))
        self.assertEqual([(x.code, x.line) for x in e], [("E008", 7)])

    def test_empty_track_line(self):
        self.assertEqual(codes(song("  bar C\n    P:\n")), ["E001"])

    def test_empty_section_and_empty_song(self):
        _, mid = compile_text(H + "section a\nend\nplay a\n")
        tracks = read_midi(mid)[2]
        self.assertEqual(tracks[0][-1][0], 0)
        compile_text(H)

    def test_errors_are_sorted_and_unique(self):
        text = song("  bar C\n    P: C4/2\n") + "play nope\nplay s\n"
        e = errs(text)
        self.assertEqual([(x.code, x.line) for x in e], [("E003", 7), ("E004", 10)])

    def test_note_limit(self):
        text = H + "pattern p base=3 dur=/#1 : 1\nsection s\n  bar C len=/#1000001\n    P: use p\nend\nplay s\n"
        self.assertEqual(codes(text), ["E018"])

    def test_cli(self):
        path = os.path.join(ROOT, "examples", "example.loma")
        run = lambda *a, **k: subprocess.run([sys.executable, "-m", "loma"] + list(a), cwd=ROOT, capture_output=True, **k)
        self.assertEqual(run("check", path).returncode, 0)
        with open(path, "rb") as f:
            src = f.read()
        self.assertEqual(run("hash", "-", input=src).stdout, run("hash", path).stdout)
        bad = run("check", "-", "--json", input=b"loma 1.0\nbanana\n")
        self.assertEqual(bad.returncode, 1)
        self.assertIn(b'"code": "E002"', bad.stdout)
        self.assertEqual(run("check", "-", "--json", input=b"loma 1.0\n\xff\n").returncode, 1)
        self.assertEqual(run("check", "/nonexistent/file.loma").returncode, 2)
        self.assertEqual(run("test-determinism", path, "--runs", "5").returncode, 0)


def pairs(text):
    return [(e.code, e.line) for e in errs(text)]


class OneRound(unittest.TestCase):
    """SPEC 13.1: syntax errors and the bar checks on the readable lines are reported together."""
    H2 = H + "track Q ch=2 program=0\n"                 # lines 1-5

    def test_bar_checks_run_beside_syntax_errors(self):
        text = song("  bar C\n    P: C4/2\n  bar C\n    P: H4/1\n")
        self.assertEqual(pairs(text), [("E003", 7), ("E001", 9)])

    def test_failed_line_is_skipped_and_the_rest_of_the_bar_is_checked(self):
        text = song("  bar C\n    P: H4/1\n    Q: C4/2\n  bar C\n    P:\n    Q: C4/1\n", head=self.H2)
        self.assertEqual(pairs(text), [("E001", 8), ("E003", 9), ("E001", 11)])

    def test_failed_definitions_are_not_reported_where_they_are_used(self):
        extra = "pattern arp base=3 dur=/5 : 1 3\npattern two from arp : 1=5\nswing sw grid=/8 : x\nvoicing vo base=3 : 99\n"
        body = "  bar C\n    P{swing=sw}: use arp\n    Q: *vo/1\n  bar C\n    P: use two\n    Q: use missing\n"
        self.assertEqual(pairs(song(body, head=self.H2, extra=extra)), [("E007", 6), ("E001", 8), ("E010", 9), ("E004", 16)])

    def test_section_with_a_wrong_header(self):
        text = self.H2 + "section bar\n  bar C\n    P: C4/2\nend\nplay bar\nplay nowhere\n"
        self.assertEqual(pairs(text), [("E019", 6), ("E003", 8), ("E004", 11)])

    def test_ties_duplicates_and_limits_wait_for_clean_syntax(self):
        body = "  bar C\n    P: C4/1~\n  bar C\n    P: D4/1\n"
        self.assertEqual(codes(song(body)), ["E012"])
        self.assertEqual(codes(song(body + "  bar Zz\n    P: C4/1\n")), ["E005"])
        dup = "at 0 P C4 d=10\nat 0 P C4 d=10\n"
        self.assertEqual(codes(song("  bar C\n    P: r/1\n") + dup), ["E017"])
        self.assertEqual(codes(song("  bar C\n    P: r/1\n") + dup + "banana\n"), ["E002"])

    def test_wrong_meter_or_header_stops_the_bar_checks(self):
        text = song("  bar C\n    P: C4/2\n").replace("meter 4/4", "meter 4/3")
        self.assertEqual(codes(text), ["E018"])
        self.assertEqual(codes("loma 7\n" + song("  bar C\n    P: C4/2\n")), ["E001"])

    def test_limit_in_the_reduced_phase_drops_its_errors(self):
        body = "  bar C\n    P: C4/2\n  bar C len=/#1000001\n    P: use p\n"
        text = H + "pattern p base=3 dur=/#1 : 1\nbanana\n" + "section s\n" + body + "end\nplay s\n"
        self.assertEqual(codes(text), ["E002"])

    def test_each_play_is_checked_with_its_transposition(self):
        text = song("  bar C\n    P: G9/1\n  bar C\n    P: C4/1 oops\n") + "play s transpose=+1\n"
        self.assertEqual(pairs(text), [("E006", 7), ("E001", 9)])

    def test_valid_files_are_untouched(self):
        for name in ("example", "brano1", "brano2", "brano3", "showcase"):
            with open(os.path.join(ROOT, "examples", name + ".loma"), encoding="utf-8") as f:
                compile_text(f.read())


class Suggestions(unittest.TestCase):
    def hint(self, text, code=None):
        e = errs(text)[0]
        if code:
            self.assertEqual(e.code, code)
        return e.ctx.get("did_you_mean")

    def test_chords(self):
        for wrong, right in (("Cmaj", "C"), ("Amin", "Am"), ("DM7", "Dmaj7"), ("Gmin7", "Gm7"), ("am", "Am"), ("bb7", "Bb7"),
                             ("F#-7", "F#m7"), ("Csus", "Csus4"), ("C+", "Caug"), ("Ebmaj", "Eb"), ("Cmaj7/e", "Cmaj7/E"),
                             ("CMaj7^1", "Cmaj7^1"), ("Cmaj77", "Cmaj7"), ("Bo7", "Bdim7"), ("Dmin7b5/Ab", "Dm7b5/Ab")):
            self.assertEqual(self.hint(song("  bar %s\n    P: r/1\n" % wrong), "E005"), right, wrong)
            compile_text(song("  bar %s\n    P: r/1\n" % right))
        for wrong in ("H", "Cxyzzy", "X7", "C^", "1", "C/"):
            self.assertIsNone(self.hint(song("  bar %s\n    P: r/1\n" % wrong), "E005"), wrong)

    def test_names(self):
        self.assertEqual(self.hint(song("  bar C\n    p: C4/1\n"), "E008"), "P")
        self.assertEqual(self.hint(song("  bar C\n    P: use arpp\n", extra="pattern arp base=3 dur=/4 : 1\n"), "E004"), "arp")
        self.assertEqual(self.hint(song("  bar C\n    P{swing=ligt}: C4/1\n", extra="swing light grid=/8 : 0 10\n"), "E004"), "light")
        self.assertEqual(self.hint(song("  bar C\n    P: *opn/1\n", extra="voicing open base=3 : 1 5\n"), "E004"), "open")
        self.assertEqual(self.hint(song("  bar C\n    P: C4/1\n").replace("play s", "play S"), "E004"), "s")
        self.assertEqual(self.hint(H + "pattern a base=3 dur=/4 : 1\npattern b from A : 1=3\n", "E004"), "a")
        self.assertEqual(self.hint(H + "sektion s\n", "E002"), "section")
        drums = H + "track K drums\n" + "section s\n  bar C\n    K: Snare/1\nend\nplay s\n"
        self.assertEqual(self.hint(drums, "E001"), "snare")

    def test_no_suggestion_when_nothing_is_close(self):
        self.assertIsNone(self.hint(song("  bar C\n    Zzzzzz: C4/1\n"), "E008"))
        self.assertIsNone(self.hint(song("  bar C\n    P: use q\n", extra="pattern a base=3 dur=/4 : 1\n"), "E004"))
        self.assertIsNone(self.hint(H + "banana\n", "E002"))

    def test_rule(self):
        from loma.util import closest
        self.assertEqual(closest("snar", ["snare", "kick"]), "snare")
        self.assertEqual(closest("ab", ["aa", "ac"]), "aa")            # tie: first in code point order
        self.assertEqual(closest("VERSE", ["verse", "chorus"]), "verse")
        self.assertIsNone(closest("a", ["b"]))                          # the edits must be fewer than both lengths
        self.assertIsNone(closest("hh", ["hat"]))
        self.assertIsNone(closest("abcdef", ["abc"]))                   # more than 2 edits
        self.assertIsNone(closest("", ["a"]))
        self.assertIsNone(closest("x" * 65, ["x" * 64]))

    def test_missing_colon_message(self):
        e = errs(song("  bar C\n    P C4/1\n"))[0]
        self.assertEqual(e.code, "E002")
        self.assertIn("needs ':'", e.message)

    def test_suggestion_in_json_and_text(self):
        e = errs(song("  bar Cmaj\n    P: r/1\n"))[0]
        self.assertEqual(e.to_dict()["did_you_mean"], "C")
        self.assertTrue(e.format().endswith("unknown chord 'Cmaj'. Did you mean 'C'?"))


if __name__ == "__main__":
    unittest.main()
