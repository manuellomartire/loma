"""Text -> Song. Reports at most one syntax error per source line and keeps going."""
import re

from .errors import LomaError, LomaErrors
from .model import (Song, Track, PStep, Pattern, Swing, Voicing, Chord, Item, Part, TrackLine,
                    Bar, Repeat, Section, Play, AtEvent, PITCH_CLASS, DRUMS, CHORD_INTERVALS,
                    CHORDS_01, TONES_01, tone_spec, KEY_MAJOR, KEY_MINOR, VALID_DENOMINATORS,
                    MAX_TICK, MAX_REPEAT, MAX_DEPTH, DEFAULT_VEL, GATE_PCT, VERSIONS, RESERVED)
from .util import duration_ticks, to_int, closest, hint, ascii_upper

WS = " \t"
NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
PITCH_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9#\-]*")
INT_RE = re.compile(r"[0-9]+")
SINT_RE = re.compile(r"[+-]?[0-9]+")
DUR_TOKEN = re.compile(r"#[0-9]+|[0-9]+(?:\.\.|\.|t|q|x[0-9]+/[0-9]+)?")
PITCH_RE = re.compile(r"([A-G])([#b]?)(-?[0-9]+)")
MIDI_PITCH_RE = re.compile(r"m([0-9]+)")
TRACK_LINE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)(\{[^}]*\})?[ \t]*:(.*)")
CC_RE = re.compile(r"cc([0-9]+)=([0-9]+)(?:>([0-9]+))?")
BEND_RE = re.compile(r"bend=(-?[0-9]+)(?:>(-?[0-9]+))?")
CHORD_RE = re.compile(r"([A-G])([#b]?)([^/^]*)(?:\^([0-9]+))?(?:/([A-G])([#b]?))?")
TOP_KEYWORDS = ("title", "tempo", "meter", "key", "track", "pattern", "swing", "voicing",
                "section", "play", "at")
COMMANDS = TOP_KEYWORDS + ("bar", "end", "repeat")
CHORD_LOOSE = re.compile(r"([A-Ga-g])([#b]?)([^/^]*)((?:\^[0-9]+)?)((?:/[A-Ga-g][#b]?)?)")
# spellings that other notations use for the qualities of LOMA
CHORD_ALIASES = {"maj": "", "major": "", "M": "", "min": "m", "minor": "m", "mi": "m", "-": "m",
                 "M7": "maj7", "Maj7": "maj7", "ma7": "maj7", "major7": "maj7", "min7": "m7", "mi7": "m7",
                 "-7": "m7", "minor7": "m7", "dom7": "7", "+": "aug", "o": "dim", "o7": "dim7",
                 "m7-5": "m7b5", "min7b5": "m7b5", "sus": "sus4", "7sus": "7sus4", "M9": "maj9",
                 "Maj9": "maj9", "min9": "m9", "min6": "m6", "min11": "m11", "mM7": "mmaj7",
                 "mMaj7": "mmaj7", "minmaj7": "mmaj7", "add2": "add9"}


def chord_hint(text):
    """The valid chord symbol that a wrong one most likely stands for, or None."""
    m = CHORD_LOOSE.fullmatch(text)
    if not m:
        return None
    quality = m.group(3)
    if quality not in CHORD_INTERVALS:
        quality = CHORD_ALIASES[quality] if quality in CHORD_ALIASES else closest(quality, CHORD_INTERVALS)
    if quality is None:
        return None
    fixed = ascii_upper(m.group(1)) + m.group(2) + quality + m.group(4) + ascii_upper(m.group(5)[:2]) + m.group(5)[2:]
    return fixed if fixed != text and CHORD_RE.fullmatch(fixed) else None


def split_words(text):
    return [w for w in re.split(r"[ \t]+", text) if w]


def strip_comment(line):
    """'#' starts a comment only at line start or after a space/tab, and never inside quotes."""
    in_quote = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_quote = not in_quote
        elif ch == "#" and not in_quote and (i == 0 or line[i - 1] in WS):
            return line[:i]
    return line


def split_segments(text):
    """Split on '|' outside quotes."""
    parts, cur, in_quote = [], [], False
    for ch in text:
        if ch == '"':
            in_quote = not in_quote
        if ch == "|" and not in_quote:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def accidental(acc):
    return 1 if acc == "#" else -1 if acc == "b" else 0


class _Skip(Exception):
    """A line that depends on a declaration that already failed: skipped without a second error."""


class Scanner:
    def __init__(self, parser, text, line):
        self.p = parser
        self.t = text
        self.i = 0
        self.line = line

    def ws(self):
        while self.i < len(self.t) and self.t[self.i] in WS:
            self.i += 1

    def eof(self):
        self.ws()
        return self.i >= len(self.t)

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else ""

    def take(self, rx):
        m = rx.match(self.t, self.i)
        if not m:
            return None
        self.i = m.end()
        return m.group(0)

    def near(self):
        return self.t[self.i:self.i + 12].strip(WS)

    def attrs(self):
        if self.peek() != "{":
            return {}
        j = self.t.find("}", self.i)
        if j < 0:
            raise LomaError("E001", "unclosed '{' in attributes", self.line)
        body = self.t[self.i + 1:j]
        self.i = j + 1
        return self.p.parse_attrs(body, self.line, False)

    def duration(self):
        if self.peek() != "/":
            raise LomaError("E001", "missing duration (expected '/' followed by e.g. 4, 8, 8., 8t, #210) near '%s'" % self.near(), self.line)
        self.i += 1
        spec = self.take(DUR_TOKEN)
        if spec is None:
            raise LomaError("E001", "invalid duration after '/'", self.line)
        if "q" in spec or "x" in spec:
            self.p.need("0.2", "tuplet duration '/%s'" % spec, self.line)
        return duration_ticks(spec, self.line)

    def tie(self):
        if self.peek() == "~":
            self.i += 1
            return True
        return False

    def boundary(self, extra=""):
        c = self.peek()
        if c == "" or c in WS or (c in extra):
            return
        if c == "~":
            raise LomaError("E001", "tie '~' must come right after the duration, before any '{...}'", self.line)
        raise LomaError("E001", "unexpected '%s' (tokens must be separated by spaces)" % self.near(), self.line)


class Parser:
    def __init__(self):
        self.song = Song()
        self.errors = []
        self.seen = set()
        self.version = None
        self.section = None
        self.stack = []          # open bodies: section body, then nested repeats
        self.repeats = []        # lines of the open 'repeat' blocks
        self.bar = None
        self.tl = None           # track line being continued
        self.after_tl = False    # a track line (valid or not) was seen in the current bar
        self.skip_bar = False
        self.bar_count = 0
        self.bad_tracks = set()  # names whose 'track' declaration failed
        self.cur_meter = self.cur_key = None
        self.meter_lost = False
        self.meter_failed = False

    # ------------------------------------------------------------------ helpers
    def need(self, ver, feature, line):
        if self.version < VERSIONS[ver]:
            raise LomaError("E020", "%s requires 'loma %s' or later (this file declares 'loma %s')" % (
                feature, ver, self.song.version), line, feature=feature, requires=ver)

    def new_name(self, name, kind, table, line):
        if not name or not NAME_RE.fullmatch(name):
            raise LomaError("E019", "invalid %s name '%s' (letters, digits, _; must start with a letter)" % (kind, name or ""), line)
        if name in RESERVED:
            raise LomaError("E019", "'%s' is a reserved word and cannot be a %s name" % (name, kind), line)
        if name in table:
            raise LomaError("E019", "duplicate %s name '%s'" % (kind, name), line)
        return name

    def track_by_name(self, name, line):
        for t in self.song.tracks:
            if t.name == name:
                return t
        if name in self.bad_tracks:
            raise _Skip()
        text, extra = hint(name, [t.name for t in self.song.tracks])
        raise LomaError("E008", "track '%s' is not declared (declare it with 'track' before using it).%s" % (name, text), line, **extra)

    def once(self, key, line):
        if key in self.seen:
            raise LomaError("E001", "'%s' is declared more than once" % key, line)
        self.seen.add(key)

    def parse_attrs(self, body, line, line_level):
        attrs = {}
        for tok in split_words(body):
            if "=" not in tok:
                raise LomaError("E001", "invalid attribute '%s' (expected key=value)" % tok, line)
            k, v = tok.split("=", 1)
            if k == "a":
                if v not in GATE_PCT:
                    raise LomaError("E001", "invalid articulation '%s' (allowed: leg, norm, stac)" % v, line)
                attrs[k] = v
            elif k == "swing" and line_level:
                self.need("0.2", "swing", line)
                if not NAME_RE.fullmatch(v):
                    raise LomaError("E001", "invalid swing name '%s'" % v, line)
                attrs[k] = v
            elif k == "v" and line_level and ">" in v:
                self.need("0.2", "velocity ramp 'v=N>M'", line)
                m = re.fullmatch(r"([0-9]+)>([0-9]+)", v)
                if not m:
                    raise LomaError("E001", "velocity ramp must be v=N>M, got '%s'" % v, line)
                lo, hi = to_int(m.group(1), line), to_int(m.group(2), line)
                for x in (lo, hi):
                    if not 1 <= x <= 127:
                        raise LomaError("E001", "velocity must be 1-127, got %d" % x, line)
                attrs[k] = (lo, hi)
            elif k in ("v", "o", "d"):
                if not SINT_RE.fullmatch(v):
                    raise LomaError("E001", "attribute %s needs an integer, got '%s'" % (k, v), line)
                n = to_int(v, line)
                if k == "v" and not 1 <= n <= 127:
                    raise LomaError("E001", "velocity must be 1-127, got %d" % n, line)
                if k == "d" and n < 1:
                    raise LomaError("E001", "d must be at least 1 tick, got %d" % n, line)
                attrs[k] = n
            else:
                allowed = "v, o, d, a, swing" if line_level else "v, o, d, a"
                raise LomaError("E001", "unknown attribute '%s' (allowed: %s)" % (k, allowed), line)
        return attrs

    def pitch(self, name, track, line):
        m = MIDI_PITCH_RE.fullmatch(name)
        if m:
            self.need("1.0", "numeric pitch '%s'" % name, line)
            value = to_int(m.group(1), line)
            if value > 127:
                raise LomaError("E006", "pitch %s is outside the MIDI range 0-127" % name, line)
            return value
        if track.kind == "drums":
            if name not in DRUMS:
                text, extra = hint(name, DRUMS)
                raise LomaError("E001", "unknown drum name '%s' (known: %s).%s" % (name, ", ".join(sorted(DRUMS)), text), line, **extra)
            return DRUMS[name]
        if name in DRUMS:
            raise LomaError("E001", "'%s' is a drum name but track %s is not a drums track" % (name, track.name), line)
        m = PITCH_RE.fullmatch(name)
        if not m:
            raise LomaError("E001", "invalid pitch name '%s'" % name, line)
        value = 12 * (to_int(m.group(3), line) + 1) + PITCH_CLASS[m.group(1)] + accidental(m.group(2))
        if not 0 <= value <= 127:
            raise LomaError("E006", "pitch %s is outside the MIDI range 0-127 (value %d)" % (name, value), line)
        return value

    def chord(self, text, line):
        m = CHORD_RE.fullmatch(text)
        if not m or m.group(3) not in CHORD_INTERVALS:
            fixed = chord_hint(text)
            if fixed is None:
                raise LomaError("E005", "unknown chord '%s'" % text, line)
            raise LomaError("E005", "unknown chord '%s'. Did you mean '%s'?" % (text, fixed), line, did_you_mean=fixed)
        letter, acc, quality, inv, bass_letter, bass_acc = m.groups()
        if quality not in CHORDS_01:
            self.need("0.3", "chord quality '%s'" % quality, line)
        root_pc = PITCH_CLASS[letter] + accidental(acc)
        intervals = list(CHORD_INTERVALS[quality])
        if inv is not None:
            self.need("0.3", "chord inversion '^%s'" % inv, line)
            k = to_int(inv, line)
            if k >= len(intervals):
                raise LomaError("E005", "chord '%s': inversion %d is not possible on a %d-note chord" % (text, k, len(intervals)), line)
            for i in range(k):
                intervals[i] += 12
            intervals.sort()
        if bass_letter is not None:
            self.need("0.3", "slash chord", line)
            bass_pc = PITCH_CLASS[bass_letter] + accidental(bass_acc)
        else:
            bass_pc = root_pc + intervals[0]
        return Chord(text, root_pc, tuple(intervals), bass_pc)

    # ------------------------------------------------------------------ content
    def control_value(self, text, lo, hi, what, line):
        n = to_int(text, line)
        if not lo <= n <= hi:
            raise LomaError("E001", "%s must be %d..%d, got %d" % (what, lo, hi, n), line)
        return n

    def control(self, sc):
        """cc / bend at the scanner position; returns (kind, num, a, b) or None."""
        m = CC_RE.match(sc.t, sc.i)
        if m:
            sc.i = m.end()
            num = self.control_value(m.group(1), 0, 127, "controller number", sc.line)
            a = self.control_value(m.group(2), 0, 127, "controller value", sc.line)
            b = None if m.group(3) is None else self.control_value(m.group(3), 0, 127, "controller value", sc.line)
            return ("cc", num, a, b)
        m = BEND_RE.match(sc.t, sc.i)
        if m:
            sc.i = m.end()
            a = self.control_value(m.group(1), -8192, 8191, "pitch bend", sc.line)
            b = None if m.group(2) is None else self.control_value(m.group(2), -8192, 8191, "pitch bend", sc.line)
            return ("bend", 0, a, b)
        return None

    def lyric(self, sc):
        j = sc.t.find('"', sc.i + 1)
        if j < 0:
            raise LomaError("E001", "unclosed '\"' in lyric", sc.line)
        text = sc.t[sc.i + 1:j]
        sc.i = j + 1
        if not text:
            raise LomaError("E001", "empty lyric", sc.line)
        return text

    def parse_content(self, text, track, line):
        sc = Scanner(self, text, line)
        items = []
        while not sc.eof():
            c = sc.peek()
            if c == '"':
                self.need("1.0", "lyrics", line)
                items.append(Item("lyric", line, text=self.lyric(sc)))
            elif sc.t.startswith("pedal+", sc.i) or sc.t.startswith("pedal-", sc.i):
                if track.kind == "drums":
                    raise LomaError("E001", "pedal is not available on drum tracks", line)
                items.append(Item("cc", line, num=64, a=127 if sc.t[sc.i + 5] == "+" else 0))
                sc.i += 6
            elif c == "[":
                sc.i += 1
                notes = []
                while True:
                    sc.ws()
                    if sc.peek() == "]":
                        sc.i += 1
                        break
                    if sc.i >= len(sc.t):
                        raise LomaError("E001", "unclosed '[' in chord", line)
                    name = sc.take(PITCH_TOKEN)
                    if not name:
                        raise LomaError("E001", "invalid character '%s' inside chord" % sc.peek(), line)
                    value = self.pitch(name, track, line)
                    attrs = sc.attrs()
                    sc.boundary("]")
                    notes.append((value, attrs))
                if not notes:
                    raise LomaError("E001", "empty chord '[]'", line)
                dur = sc.duration()
                tie = sc.tie()
                items.append(Item("chord", line, dur=dur, notes=notes, tie=tie, attrs=sc.attrs()))
            elif c == "*":
                self.need("0.3", "voicing '*NAME'", line)
                if track.kind == "drums":
                    raise LomaError("E001", "voicings cannot be used on drum tracks", line)
                sc.i += 1
                name = sc.take(NAME_RE)
                if not name:
                    raise LomaError("E001", "'*' must be followed by a voicing name", line)
                dur = sc.duration()
                tie = sc.tie()
                items.append(Item("voiced", line, dur=dur, name=name, tie=tie, attrs=sc.attrs()))
            else:
                ctl = self.control(sc)
                if ctl is not None:
                    kind, num, a, b = ctl
                    self.need("0.2", "control change" if kind == "cc" else "pitch bend", line)
                    items.append(Item(kind, line, num=num, a=a, b=b, dur=0 if b is None else sc.duration()))
                else:
                    name = sc.take(PITCH_TOKEN)
                    if not name:
                        raise LomaError("E001", "unexpected character '%s'" % c, line)
                    if name == "use":
                        raise LomaError("E016", "'use PATTERN' cannot be mixed with explicit notes in the same segment", line)
                    if name == "r":
                        dur = sc.duration()
                        if sc.tie():
                            raise LomaError("E012", "a rest cannot be tied", line)
                        if sc.attrs():
                            raise LomaError("E001", "a rest cannot have attributes", line)
                        items.append(Item("rest", line, dur=dur))
                    else:
                        value = self.pitch(name, track, line)
                        dur = sc.duration()
                        tie = sc.tie()
                        items.append(Item("note", line, dur=dur, notes=[(value, {})], tie=tie, attrs=sc.attrs()))
            sc.boundary()
        return items

    # ------------------------------------------------------------------ patterns, swings, voicings
    def tone(self, sc):
        tok = sc.take(INT_RE)
        if tok is None:
            return None
        n = to_int(tok, sc.line)
        spec = tone_spec(n)
        if spec is None:
            raise LomaError("E010", "tone %d does not exist (valid tones: 0, 1 3 5 7 9 11, 8 10 12 14 16 18)" % n, sc.line)
        if n not in TONES_01:
            self.need("0.3", "tone %d" % n, sc.line)
        shift = 0
        while sc.peek() in ("+", "-"):
            self.need("0.3", "octave marks on tones", sc.line)
            shift += 12 if sc.peek() == "+" else -12
            sc.i += 1
        return (spec[0], spec[1] + shift)

    def step(self, sc, default_dur):
        if sc.peek() == "(":
            sc.i += 1
            tones = []
            while True:
                sc.ws()
                if sc.peek() == ")":
                    sc.i += 1
                    break
                t = self.tone(sc)
                if t is None:
                    raise LomaError("E001", "invalid group in pattern (expected tone numbers and ')')", sc.line)
                tones.append(t)
            if not tones:
                raise LomaError("E001", "empty group '()' in pattern", sc.line)
            kind = "tones"
        elif sc.peek() == "r":
            sc.i += 1
            tones, kind = [], "rest"
        else:
            t = self.tone(sc)
            if t is None:
                raise LomaError("E001", "invalid pattern step near '%s'" % sc.near(), sc.line)
            tones, kind = [t], "tones"
        dur = sc.duration() if sc.peek() == "/" else default_dur
        attrs = sc.attrs()
        if kind == "rest" and attrs:
            raise LomaError("E001", "a rest cannot have attributes", sc.line)
        sc.boundary()
        return PStep(kind, tuple(tones), dur, attrs)

    def options(self, words, allowed, line, what):
        opts = {}
        for w in words:
            k, sep, v = w.partition("=")
            if not sep or k not in allowed:
                raise LomaError("E001", "invalid %s option '%s' (allowed: %s)" % (what, w, " ".join(allowed)), line)
            opts[k] = v
        return opts

    def base_option(self, v, line):
        if not re.fullmatch(r"-?[0-9]+", v):
            raise LomaError("E001", "base needs an octave number, got '%s'" % v, line)
        base = to_int(v, line)
        if not -1 <= base <= 9:
            raise LomaError("E006", "base octave %d is outside -1..9" % base, line)
        return base

    def dur_option(self, v, line, what):
        if not v.startswith("/"):
            raise LomaError("E001", "%s needs a duration like /4, got '%s'" % (what, v), line)
        spec = v[1:]
        if "q" in spec or "x" in spec:
            self.need("0.2", "tuplet duration '/%s'" % spec, line)
        return duration_ticks(spec, line)

    def cmd_pattern(self, code, line):
        head, sep, body = code.partition(":")
        if not sep:
            raise LomaError("E001", "usage: pattern NAME base=O dur=/D : steps", line)
        words = split_words(head)
        name = self.new_name(words[1] if len(words) > 1 else "", "pattern", self.song.patterns, line)
        sc = Scanner(self, body, line)
        if len(words) > 2 and words[2] == "from":
            self.need("0.2", "'pattern ... from'", line)
            if len(words) < 4:
                raise LomaError("E001", "usage: pattern NAME from OTHER [base=O] : INDEX=STEP ...", line)
            src = self.song.patterns.get(words[3])
            if src is None:
                if words[3] in self.song.failed["pattern"]:
                    raise _Skip()
                text, extra = hint(words[3], self.song.patterns)
                raise LomaError("E004", "pattern '%s' is not defined (it must be defined before this line).%s" % (words[3], text), line, **extra)
            opts = self.options(words[4:], ("base",), line, "pattern")
            base = self.base_option(opts["base"], line) if "base" in opts else src.base
            steps = list(src.steps)
            while not sc.eof():
                tok = sc.take(INT_RE)
                if tok is None or sc.peek() != "=":
                    raise LomaError("E001", "expected INDEX=STEP near '%s'" % sc.near(), line)
                idx = to_int(tok, line)
                if not 1 <= idx <= len(steps):
                    raise LomaError("E001", "step index %d is outside 1..%d" % (idx, len(steps)), line)
                sc.i += 1
                st = self.step(sc, None)
                if st.dur is None:
                    st.dur = steps[idx - 1].dur
                steps[idx - 1] = st
        else:
            opts = self.options(words[2:], ("base", "dur"), line, "pattern")
            if "base" not in opts or "dur" not in opts:
                raise LomaError("E001", "pattern needs both base=OCTAVE and dur=/DURATION", line)
            base = self.base_option(opts["base"], line)
            dur = self.dur_option(opts["dur"], line, "dur")
            steps = []
            while not sc.eof():
                steps.append(self.step(sc, dur))
            if not steps:
                raise LomaError("E001", "pattern has no steps", line)
        self.song.patterns[name] = Pattern(name, base, steps, sum(s.dur for s in steps), line)

    def cmd_swing(self, code, line):
        self.need("0.2", "swing", line)
        head, sep, body = code.partition(":")
        if not sep:
            raise LomaError("E001", "usage: swing NAME grid=/D : OFFSET OFFSET ...", line)
        words = split_words(head)
        name = self.new_name(words[1] if len(words) > 1 else "", "swing", self.song.swings, line)
        opts = self.options(words[2:], ("grid",), line, "swing")
        if "grid" not in opts:
            raise LomaError("E001", "swing needs grid=/DURATION", line)
        grid = self.dur_option(opts["grid"], line, "grid")
        table = []
        for w in split_words(body):
            if not SINT_RE.fullmatch(w):
                raise LomaError("E001", "swing offsets must be integers, got '%s'" % w, line)
            table.append(to_int(w, line))
        if not table:
            raise LomaError("E001", "swing has no offsets", line)
        self.song.swings[name] = Swing(name, grid, tuple(table), line)

    def cmd_voicing(self, code, line):
        self.need("0.3", "voicing", line)
        head, sep, body = code.partition(":")
        if not sep:
            raise LomaError("E001", "usage: voicing NAME base=O : TONE TONE ...", line)
        words = split_words(head)
        name = self.new_name(words[1] if len(words) > 1 else "", "voicing", self.song.voicings, line)
        opts = self.options(words[2:], ("base",), line, "voicing")
        if "base" not in opts:
            raise LomaError("E001", "voicing needs base=OCTAVE", line)
        base = self.base_option(opts["base"], line)
        sc = Scanner(self, body, line)
        tones = []
        while not sc.eof():
            t = self.tone(sc)
            if t is None:
                raise LomaError("E001", "invalid voicing tone near '%s'" % sc.near(), line)
            sc.boundary()
            tones.append(t)
        if not tones:
            raise LomaError("E001", "voicing has no tones", line)
        self.song.voicings[name] = Voicing(name, base, tuple(tones), line)

    # ------------------------------------------------------------------ top-level statements
    def header(self, words, line):
        if len(words) != 2 or words[0] != "loma":
            raise LomaError("E001", "the file must start with 'loma VERSION' (e.g. 'loma 1.0')", line)
        if words[1] not in VERSIONS:
            raise LomaError("E001", "unsupported version '%s' (supported: %s)" % (words[1], ", ".join(sorted(VERSIONS))), line)
        self.song.version = words[1]
        self.version = VERSIONS[words[1]]

    def cmd_title(self, code, line):
        self.once("title", line)
        m = re.fullmatch(r'title[ \t]+"([^"]*)"', code)
        if not m:
            raise LomaError("E001", "title needs a quoted string without inner quotes: title \"Name\"", line)
        self.song.title = m.group(1)

    def cmd_tempo(self, words, line):
        self.once("tempo", line)
        if len(words) != 2 or not INT_RE.fullmatch(words[1]):
            raise LomaError("E001", "usage: tempo BPM (integer)", line)
        bpm = to_int(words[1], line)
        if not 4 <= bpm <= 400:
            raise LomaError("E015", "tempo %d is outside the range 4-400 BPM" % bpm, line)
        self.song.tempo = bpm

    def meter_value(self, text, line, usage):
        m = re.fullmatch(r"([0-9]+)/([0-9]+)", text)
        if not m:
            raise LomaError("E001", usage, line)
        num, den = to_int(m.group(1), line), to_int(m.group(2), line)
        if not 1 <= num <= 64 or den not in VALID_DENOMINATORS:
            raise LomaError("E018", "meter %d/%d is outside the limits (numerator 1-64, denominator 1, 2, 4, 8, 16, 32, 64)" % (num, den), line)
        return (num, den)

    def key_value(self, text, line):
        m = re.fullmatch(r"([A-G][#b]?)(m?)", text)
        if m:
            table = KEY_MINOR if m.group(2) else KEY_MAJOR
            if m.group(1) in table:
                return (table[m.group(1)], 1 if m.group(2) else 0)
        raise LomaError("E013", "invalid key '%s' (examples: C, Cm, F#m, Bb)" % text, line)

    def cmd_meter(self, words, line):
        self.once("meter", line)
        self.song.meter = self.meter_value(words[1] if len(words) == 2 else "", line, "usage: meter N/D, e.g. meter 4/4")

    def cmd_key(self, words, line):
        self.once("key", line)
        if len(words) != 2:
            raise LomaError("E013", "invalid key '%s' (examples: C, Cm, F#m, Bb)" % (words[1] if len(words) > 1 else ""), line)
        self.song.key = self.key_value(words[1], line)

    def cmd_track(self, words, line):
        try:
            self.declare_track(words, line)
        except LomaError:
            name = words[1] if len(words) > 1 else ""
            if all(t.name != name for t in self.song.tracks):
                self.bad_tracks.add(name)
            raise

    def declare_track(self, words, line):
        name = self.new_name(words[1] if len(words) > 1 else "", "track", [t.name for t in self.song.tracks], line)
        drums = "drums" in words[2:]
        opts = self.options([w for w in words[2:] if w != "drums"], ("ch", "program"), line, "track")
        for k in opts:
            if not INT_RE.fullmatch(opts[k]):
                raise LomaError("E001", "track option %s needs an integer, got '%s'" % (k, opts[k]), line)
            opts[k] = to_int(opts[k], line)
        if drums:
            if opts:
                raise LomaError("E001", "a drums track takes no ch/program options", line)
            if any(t.kind == "drums" for t in self.song.tracks):
                raise LomaError("E011", "only one drums track is allowed (channel 10 is exclusive)", line)
            ch, program, kind = 10, 0, "drums"
        else:
            if "ch" not in opts:
                raise LomaError("E001", "melodic track needs ch=N (1-16)", line)
            ch, program, kind = opts["ch"], opts.get("program", 0), "melodic"
            if not 1 <= ch <= 16:
                raise LomaError("E001", "ch must be 1-16, got %d" % ch, line)
            if not 0 <= program <= 127:
                raise LomaError("E001", "program must be 0-127, got %d" % program, line)
            if ch == 10:
                raise LomaError("E011", "channel 10 is reserved for drums", line)
            for t in self.song.tracks:
                if t.kind == "melodic" and t.ch == ch:
                    raise LomaError("E011", "channel %d is already used by track %s" % (ch, t.name), line)
        self.song.tracks.append(Track(name, kind, ch, program, len(self.song.tracks), line))

    def cmd_section(self, words, line):
        self.section = Section(words[1] if len(words) > 1 else "", [], line)
        self.stack = [self.section.body]
        self.repeats = []
        self.bar = self.tl = None
        self.skip_bar = False
        self.bar_count = 0
        self.cur_meter = self.cur_key = None    # every section starts in the meter and key of the header
        self.meter_lost = False
        if len(words) != 2:             # the body is still parsed, but the section is not registered
            raise LomaError("E001", "usage: section NAME", line)
        name = self.new_name(words[1], "section", self.song.sections, line)
        self.song.sections[name] = self.section

    def cmd_play(self, words, line):
        if len(words) < 2 or not NAME_RE.fullmatch(words[1]):
            raise LomaError("E001", "usage: play NAME [xN] [transpose=S]", line)
        times, transpose = 1, 0
        for w in words[2:]:
            if re.fullmatch(r"x[0-9]+", w):
                times = to_int(w[1:], line)
                if not 1 <= times <= MAX_REPEAT:
                    raise LomaError("E018", "repetitions must be 1-%d, got %d" % (MAX_REPEAT, times), line)
            elif re.fullmatch(r"transpose=[+-]?[0-9]+", w):
                transpose = to_int(w.split("=")[1], line)
            else:
                raise LomaError("E001", "invalid play option '%s' (allowed: xN, transpose=S)" % w, line)
        self.song.plays.append(Play(words[1], times, transpose, line))

    def cmd_at(self, code, line):
        usage = "usage: at TICK TRACK PITCH d=TICKS [v=VEL] | at TICK TRACK ccN=V | at TICK TRACK bend=V | at TICK TRACK \"text\" | at TICK tempo=BPM | at TICK meter=N/D | at TICK key=K"
        m = re.fullmatch(r"at[ \t]+([0-9]+)[ \t]+(.+)", code)
        if not m:
            raise LomaError("E001", usage, line)
        tick = to_int(m.group(1), line)
        if tick > MAX_TICK:
            raise LomaError("E018", "tick %d exceeds the maximum %d" % (tick, MAX_TICK), line)
        rest = m.group(2)
        if rest.startswith("tempo="):
            self.need("1.0", "'at TICK tempo=BPM'", line)
            v = rest[6:]
            if not INT_RE.fullmatch(v):
                raise LomaError("E001", usage, line)
            bpm = to_int(v, line)
            if not 4 <= bpm <= 400:
                raise LomaError("E015", "tempo %d is outside the range 4-400 BPM" % bpm, line)
            self.song.ats.append(AtEvent("tempo", tick, line, value=bpm))
            return
        if rest.startswith("meter="):
            self.need("1.1", "'at TICK meter=N/D'", line)
            self.song.ats.append(AtEvent("meter", tick, line, value=self.meter_value(rest[6:], line, usage)))
            return
        if rest.startswith("key="):
            self.need("1.1", "'at TICK key=K'", line)
            self.song.ats.append(AtEvent("key", tick, line, value=self.key_value(rest[4:], line)))
            return
        tm = re.fullmatch(r"([^ \t]+)(?:[ \t]+(.*))?", rest)
        tail = tm.group(2) or ""
        track = self.track_by_name(tm.group(1), line)
        if not tail:
            raise LomaError("E001", usage, line)
        if tail.startswith('"'):
            self.need("1.0", "lyrics", line)
            lm = re.fullmatch(r'"([^"]+)"', tail)
            if not lm:
                raise LomaError("E001", "lyric must be a non-empty quoted string without inner quotes", line)
            self.song.ats.append(AtEvent("lyric", tick, line, track=track, text=lm.group(1)))
            return
        sc = Scanner(self, tail, line)
        ctl = self.control(sc)
        if ctl is not None:
            kind, num, a, b = ctl
            self.need("1.0", "'at' with %s" % kind, line)
            if b is not None or not sc.eof():
                raise LomaError("E001", usage, line)
            self.song.ats.append(AtEvent(kind, tick, line, track=track, num=num, value=a))
            return
        words = split_words(tail)
        value = self.pitch(words[0], track, line)
        opts = self.options(words[1:], ("d", "v"), line, "'at'")
        for k in opts:
            if not INT_RE.fullmatch(opts[k]):
                raise LomaError("E001", "'at' option %s needs a non-negative integer, got '%s'" % (k, opts[k]), line)
            opts[k] = to_int(opts[k], line)
        if opts.get("d", 0) < 1:
            raise LomaError("E001", "at: d=TICKS (at least 1) is required", line)
        v = opts.get("v", DEFAULT_VEL)
        if not 1 <= v <= 127:
            raise LomaError("E001", "velocity must be 1-127, got %d" % v, line)
        self.song.ats.append(AtEvent("note", tick, line, track=track, pitch=value, d=opts["d"], v=v))

    # ------------------------------------------------------------------ inside a section
    def close_bar(self):
        if self.bar is not None:
            for tl in self.bar.track_lines:
                if not tl.failed and all(p.use is None and not p.items for p in tl.parts):
                    tl.failed = True
                    self.errors.append(LomaError("E001", "empty track line", tl.line))
        self.bar = self.tl = None
        self.after_tl = False

    def close_section(self):
        self.close_bar()
        self.section = None
        self.stack = []
        self.repeats = []
        self.skip_bar = False

    def cmd_bar(self, words, line):
        self.close_bar()
        self.skip_bar = True            # stays True if this line fails
        self.bar_count += 1
        chords = []
        try:
            len_ticks, tempo, meter, key = self.bar_options(words, line, chords)
        except LomaError:
            if any(w.startswith("meter=") for w in words[1:]):
                self.meter_lost = True  # the bars that follow have an unknown length
            raise
        if not chords:
            raise LomaError("E001", "'bar' needs at least one chord, e.g. 'bar Cm'", line)
        if meter is not None:
            self.cur_meter = meter
        if key is not None:
            self.cur_key = key
        self.bar = Bar(chords, len_ticks, tempo, [], line, self.bar_count, self.cur_meter, self.cur_key, self.meter_lost)
        self.stack[-1].append(self.bar)
        self.skip_bar = False

    def bar_options(self, words, line, chords):
        len_ticks, tempo, meter, key = None, None, None, None
        for w in words[1:]:
            if "=" in w:
                k, v = w.split("=", 1)
                if k == "len":
                    len_ticks = self.dur_option(v, line, "len")
                elif k == "tempo":
                    m = re.fullmatch(r"([0-9]+)(?:>([0-9]+))?", v)
                    if not m:
                        raise LomaError("E001", "tempo option must be tempo=N or tempo=N>M", line)
                    lo = to_int(m.group(1), line)
                    hi = to_int(m.group(2), line) if m.group(2) else None
                    for x in (lo, hi):
                        if x is not None and not 4 <= x <= 400:
                            raise LomaError("E015", "tempo %d is outside the range 4-400 BPM" % x, line)
                    tempo = (lo, hi)
                elif k == "meter":
                    self.need("1.1", "bar option 'meter='", line)
                    meter = self.meter_value(v, line, "meter option must be meter=N/D, e.g. meter=3/4")
                elif k == "key":
                    self.need("1.1", "bar option 'key='", line)
                    key = self.key_value(v, line)
                else:
                    raise LomaError("E001", "unknown bar option '%s' (allowed: len=/D tempo=N tempo=N>M meter=N/D key=K)" % k, line)
            else:
                chords.append(self.chord(w, line))
        return len_ticks, tempo, meter, key

    def cmd_repeat(self, words, line):
        self.close_bar()
        times = 1
        ok = len(words) == 2 and INT_RE.fullmatch(words[1])
        if ok:
            times = to_int(words[1], line)
        node = Repeat(times, [], line)
        self.stack[-1].append(node)
        self.stack.append(node.body)
        self.repeats.append(line)
        self.need("0.2", "'repeat' block", line)
        if len(self.repeats) > MAX_DEPTH:
            raise LomaError("E018", "'repeat' blocks nested deeper than %d" % MAX_DEPTH, line)
        if not ok:
            raise LomaError("E001", "usage: repeat N", line)
        if not 1 <= times <= MAX_REPEAT:
            node.times = 1
            raise LomaError("E018", "repetitions must be 1-%d, got %d" % (MAX_REPEAT, times), line)

    def add_content(self, tl, text, line):
        try:
            self.add_chunks(tl, text, line)
        except (LomaError, _Skip):
            tl.failed = True
            raise

    def add_chunks(self, tl, text, line):
        chunks = split_segments(text)
        if len(chunks) > 1:
            self.need("0.2", "segments separated by '|'", line)
        for n, chunk in enumerate(chunks):
            if n > 0:
                tl.parts.append(Part())
            part = tl.parts[-1]
            words = split_words(chunk)
            if not words:
                continue
            if words[0] == "use":
                if part.use is not None or part.items or len(words) != 2:
                    raise LomaError("E016", "'use PATTERN' cannot be mixed with explicit notes in the same segment", line)
                if tl.track.kind == "drums":
                    raise LomaError("E001", "patterns cannot be used on drum tracks", line)
                names = words[1].split(",")
                if len(names) > 1:
                    self.need("0.2", "pattern list 'use A,B'", line)
                for nm in names:
                    if not NAME_RE.fullmatch(nm):
                        raise LomaError("E001", "invalid pattern name '%s'" % nm, line)
                part.use = names
            else:
                if part.use is not None:
                    raise LomaError("E016", "'use PATTERN' cannot be mixed with explicit notes in the same segment", line)
                part.items.extend(self.parse_content(chunk, tl.track, line))

    def track_line(self, m, line):
        self.tl = None
        self.after_tl = True
        if self.bar is None:
            if self.skip_bar:
                return
            raise LomaError("E001", "track line before any 'bar'", line)
        name, attr_text, content = m.group(1), m.group(2), m.group(3)
        track = self.track_by_name(name, line)
        voice = sum(1 for tl in self.bar.track_lines if tl.track is track)
        if voice and self.version < VERSIONS["1.1"]:
            raise LomaError("E001", "track %s already has a line in this bar (several voices on one track need 'loma 1.1')" % name, line)
        attrs = self.parse_attrs(attr_text[1:-1], line, True) if attr_text else {}
        tl = TrackLine(track, attrs, [Part()], line, False, voice)
        self.bar.track_lines.append(tl)
        self.tl = tl
        self.add_content(tl, content, line)

    def continuation(self, code, line):
        if self.tl is None:
            if self.skip_bar or self.after_tl:
                return                  # the line it would continue already failed
            raise self.unknown_command(split_words(code)[0], line)
        try:
            self.need("0.2", "track content on more than one line", line)
        except LomaError:
            self.tl.failed = True
            raise
        self.add_content(self.tl, code, line)

    def section_line(self, code, words, line):
        first = words[0]
        if first == "end" and len(words) == 1:
            self.close_bar()
            if len(self.stack) > 1:
                self.stack.pop()
                self.repeats.pop()
            else:
                self.close_section()
        elif first == "bar":
            self.cmd_bar(words, line)
        elif first == "repeat":
            self.cmd_repeat(words, line)
        else:
            m = TRACK_LINE.fullmatch(code)
            if m:
                self.track_line(m, line)
            else:
                self.continuation(code, line)

    def top_line(self, code, words, line):
        first = words[0]
        if first == "title":
            self.cmd_title(code, line)
        elif first == "tempo":
            self.cmd_tempo(words, line)
        elif first == "meter":
            self.cmd_meter(words, line)
        elif first == "key":
            self.cmd_key(words, line)
        elif first == "track":
            self.cmd_track(words, line)
        elif first == "pattern":
            self.cmd_pattern(code, line)
        elif first == "swing":
            self.cmd_swing(code, line)
        elif first == "voicing":
            self.cmd_voicing(code, line)
        elif first == "section":
            self.cmd_section(words, line)
        elif first == "play":
            self.cmd_play(words, line)
        elif first == "at":
            self.cmd_at(code, line)
        elif first == "end":
            raise LomaError("E001", "'end' without a matching 'section' or 'repeat'", line)
        elif first in ("bar", "repeat") or TRACK_LINE.fullmatch(code):
            raise LomaError("E001", "'%s' outside a section" % first, line)
        else:
            raise self.unknown_command(first, line)

    def unknown_command(self, word, line):
        name = word.split("{")[0]
        if any(t.name == name for t in self.song.tracks):
            return LomaError("E002", "unknown command '%s' (a track line needs ':' after the track name and its attributes)" % word, line)
        text, extra = hint(word, COMMANDS)
        return LomaError("E002", "unknown command '%s'.%s" % (word, text), line, **extra)

    def top(self, code, words, line):
        """A top-level statement; a failed definition is remembered, so that its uses are not reported too."""
        try:
            self.top_line(code, words, line)
        except (LomaError, _Skip):
            first = words[0]
            m = NAME_RE.match(words[1]) if len(words) > 1 else None
            if first in ("pattern", "swing", "voicing", "section") and m:
                self.song.failed[first].add(m.group(0))
            if first == "section" and self.section is not None:
                self.song.orphans.append(self.section)
            if first == "meter":
                self.meter_failed = True
            raise

    # ------------------------------------------------------------------ driver
    def run(self, text):
        for ln, raw in enumerate(text.split("\n"), 1):
            code = strip_comment(raw.rstrip("\r")).strip(WS)
            if not code:
                continue
            words = split_words(code)
            try:
                if self.version is None:
                    self.header(words, ln)
                elif self.section is not None and words[0] in TOP_KEYWORDS:
                    # a top-level statement inside a section: the section lost its 'end'
                    name = self.section.name
                    self.close_section()
                    try:
                        self.top(code, words, ln)
                    except (LomaError, _Skip):
                        pass
                    raise LomaError("E001", "'%s' is not allowed inside section '%s' (missing 'end'?)" % (words[0], name), ln)
                elif self.section is not None:
                    self.section_line(code, words, ln)
                else:
                    self.top(code, words, ln)
            except _Skip:
                pass
            except LomaError as e:
                if e.line is None:
                    e.line = ln
                self.errors.append(e)
                if self.version is None:
                    break
        if self.version is None and not self.errors:
            self.errors.append(LomaError("E001", "empty file: it must start with 'loma VERSION'", 1))
        if self.section is not None:
            if self.repeats:
                self.errors.append(LomaError("E001", "'repeat' is missing its 'end'", self.repeats[-1]))
            else:
                self.errors.append(LomaError("E001", "section '%s' is missing its 'end'" % self.section.name, self.section.line))
            self.close_section()
        return self.song


def parse_partial(text):
    """Text -> (song, syntax errors, checkable).

    With syntax errors the song holds what could be read; 'checkable' says whether its bars can
    still be validated (SPEC 13.1)."""
    if text.startswith("\ufeff"):
        text = text[1:]
    p = Parser()
    song = p.run(text)
    return song, p.errors, p.version is not None and not p.meter_failed


def parse(text):
    """Text -> Song. Raises LomaErrors with the syntax errors."""
    song, errors, _ = parse_partial(text)
    if errors:
        raise LomaErrors(errors)
    return song
