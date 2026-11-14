"""Constants, tables and data classes shared by all compiler stages."""
from dataclasses import dataclass, field

PPQ = 480
WHOLE = 1920                      # ticks in a whole note
RAMP_STEP = 60                    # ticks between two events of a cc/bend ramp
MAX_TICK = 268435455              # largest value of a 4-byte VLQ
MAX_NOTES = 1000000
MAX_CONTROLS = 1000000
MAX_BARS = 100000
MAX_ELEMENTS = 4000000            # expanded notes, rests, controls and pattern steps
MAX_DEPTH = 16                    # nested 'repeat' blocks
MAX_REPEAT = 1000
MAX_DIGITS = 9
DEFAULT_VEL = 80
DEFAULT_TEMPO = 120
DEFAULT_METER = (4, 4)
VALID_DENOMINATORS = (1, 2, 4, 8, 16, 32, 64)
GATE_PCT = {"leg": 100, "norm": 90, "stac": 50}

VERSIONS = {"0.1": (0, 1), "0.2": (0, 2), "0.3": (0, 3), "1.0": (1, 0)}

RESERVED = frozenset((
    "loma", "title", "tempo", "meter", "key", "track", "pattern", "swing", "voicing",
    "section", "play", "at", "bar", "end", "repeat", "use", "from", "r", "pedal", "bend",
    "drums"))

PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NOTE_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")

DRUMS = {"kick": 36, "snare": 38, "hat": 42, "ohat": 46,
         "crash": 49, "ride": 51, "tom1": 50, "tom2": 47}

CHORDS_01 = {
    "": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10), "dim": (0, 3, 6), "aug": (0, 4, 8),
    "sus2": (0, 2, 7), "sus4": (0, 5, 7),
}
CHORDS_03 = {
    "5": (0, 7), "6": (0, 4, 7, 9), "m6": (0, 3, 7, 9),
    "dim7": (0, 3, 6, 9), "m7b5": (0, 3, 6, 10), "mmaj7": (0, 3, 7, 11),
    "7sus4": (0, 5, 7, 10), "7b9": (0, 4, 7, 10, 13), "7#9": (0, 4, 7, 10, 15),
    "add9": (0, 4, 7, 14), "madd9": (0, 3, 7, 14),
    "9": (0, 4, 7, 10, 14), "maj9": (0, 4, 7, 11, 14), "m9": (0, 3, 7, 10, 14),
    "11": (0, 4, 7, 10, 14, 17), "m11": (0, 3, 7, 10, 14, 17),
    "13": (0, 4, 7, 10, 14, 21),
}
CHORD_INTERVALS = dict(CHORDS_01, **CHORDS_03)

TONES_01 = frozenset((1, 3, 5, 7, 8, 10, 12, 14))
BASS_TONE = -1


def tone_spec(n):
    """Tone number -> (index in the chord or BASS_TONE, semitone shift); None if invalid."""
    if n == 0:
        return (BASS_TONE, 0)
    if n % 2 == 1 and 1 <= n <= 11:
        return ((n - 1) // 2, 0)
    if n % 2 == 0 and 8 <= n <= 18:
        return ((n - 8) // 2, 12)
    return None


KEY_MAJOR = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
             "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7}
KEY_MINOR = {"A": 0, "E": 1, "B": 2, "F#": 3, "C#": 4, "G#": 5, "D#": 6, "A#": 7,
             "D": -1, "G": -2, "C": -3, "F": -4, "Bb": -5, "Eb": -6, "Ab": -7}


@dataclass
class Track:
    name: str
    kind: str            # "melodic" or "drums"
    ch: int              # 1..16
    program: int
    index: int
    line: int


@dataclass
class PStep:
    kind: str            # "rest" or "tones"
    tones: tuple         # ((index, shift), ...)
    dur: int             # None = inherit (only inside 'pattern ... from')
    attrs: dict


@dataclass
class Pattern:
    name: str
    base: int
    steps: list
    length: int
    line: int


@dataclass
class Swing:
    name: str
    grid: int
    table: tuple
    line: int


@dataclass
class Voicing:
    name: str
    base: int
    tones: tuple
    line: int


@dataclass
class Chord:
    name: str
    root_pc: int
    intervals: tuple     # ascending, after inversion
    bass_pc: int


@dataclass
class Item:
    kind: str            # "note", "chord", "voiced", "rest", "cc", "bend", "lyric"
    line: int
    dur: int = 0
    notes: list = None   # [(pitch, attrs)] for note/chord
    tie: bool = False
    attrs: dict = None
    name: str = None     # voicing name
    num: int = 0         # controller number
    a: int = 0           # value (or ramp start)
    b: int = None        # ramp end, None = single event
    text: str = None

    @property
    def explicit(self):
        return bool(self.attrs) or any(bool(a) for _, a in (self.notes or ()))


@dataclass
class Part:
    use: list = None     # pattern names, or None for explicit content
    items: list = field(default_factory=list)


@dataclass
class TrackLine:
    track: Track
    attrs: dict
    parts: list
    line: int
    failed: bool = False


@dataclass
class Bar:
    chords: list
    len_ticks: int       # None = from meter
    tempo: tuple         # None, (N, None) or (N, M)
    track_lines: list
    line: int
    number: int


@dataclass
class Repeat:
    times: int
    body: list
    line: int


@dataclass
class Section:
    name: str
    body: list           # Bar | Repeat
    line: int


@dataclass
class Play:
    name: str
    times: int
    transpose: int
    line: int


@dataclass
class AtEvent:
    kind: str            # "note", "cc", "bend", "lyric", "tempo"
    tick: int
    line: int
    track: Track = None
    pitch: int = 0
    d: int = 0
    v: int = 0
    num: int = 0
    value: int = 0
    text: str = None


@dataclass
class Song:
    version: str = None
    title: str = None
    tempo: int = DEFAULT_TEMPO
    meter: tuple = DEFAULT_METER
    key: tuple = None            # (sf, mi) or None
    tracks: list = field(default_factory=list)
    patterns: dict = field(default_factory=dict)
    swings: dict = field(default_factory=dict)
    voicings: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    plays: list = field(default_factory=list)
    ats: list = field(default_factory=list)
