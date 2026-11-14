"""MIDI -> LOMA.

The output is a lossless container: every event becomes an 'at' statement at its exact tick.
A file produced by a LOMA compiler decompiles to a source that compiles back to the same bytes.
For other MIDI files, anything LOMA cannot express is dropped and reported as a warning.
"""
from .midi_reader import read_midi
from .model import DRUMS, NOTE_NAMES, PPQ, MAX_TICK, VALID_DENOMINATORS, KEY_MAJOR, KEY_MINOR, RESERVED
from .parser import NAME_RE

_DRUM_NAMES = {v: k for k, v in DRUMS.items()}
_KEY_NAMES = {(sf, 0): name for name, sf in KEY_MAJOR.items()}
_KEY_NAMES.update({(sf, 1): name + "m" for name, sf in KEY_MINOR.items()})


class DecompileError(Exception):
    pass


class _Channel:
    def __init__(self, ch, track):
        self.ch = ch
        self.track = track        # MIDI track where the channel first appears
        self.program = None
        self.notes = []           # (start, midi track, seq, pitch, duration, velocity)
        self.others = []          # (tick, midi track, seq, text)


def _pitch_name(pitch, drums):
    if drums:
        return _DRUM_NAMES.get(pitch, "m%d" % pitch)
    return "%s%d" % (NOTE_NAMES[pitch % 12], pitch // 12 - 1)


def _bpm(us):
    """Integer BPM whose canonical conversion gives exactly 'us', or the nearest one in range."""
    guess = max(4, min(400, 60000000 // max(us, 1)))
    for bpm in (guess, guess + 1, guess - 1):
        if 4 <= bpm <= 400 and 60000000 // bpm == us:
            return bpm, True
    return guess, False


def _text(raw):
    return raw.decode("utf-8", "replace").replace('"', "'").replace("\n", " ").replace("\r", " ")


def decompile(data):
    """MIDI bytes -> (LOMA source, [warnings])."""
    fmt, division, tracks = read_midi(data)
    warnings, dropped = [], set()

    def scale(tick):
        if (tick * PPQ) % division:
            raise DecompileError("tick %d cannot be converted exactly from %d to %d ticks per quarter" % (tick, division, PPQ))
        t = tick * PPQ // division
        if t > MAX_TICK:
            raise DecompileError("the file is longer than the LOMA maximum of %d ticks" % MAX_TICK)
        return t

    title = meter = key = None
    tempos, channels, names, lyrics = {}, {}, {}, {}
    silent, open_notes = [], {}
    end = 0

    for ti, events in enumerate(tracks):
        has_channel_event = False
        for seq, (tick, kind, a, b) in enumerate(events):
            t = scale(tick)
            end = max(end, t)
            if kind == "sysex":
                dropped.add("system exclusive messages")
            elif kind == "meta":
                if a == 0x03:
                    if ti == 0 and fmt == 1:
                        title = _text(b)
                    else:
                        names[ti] = _text(b)
                elif a == 0x58 and len(b) >= 2:
                    if meter is None:
                        meter = (b[0], 1 << b[1])
                    elif meter != (b[0], 1 << b[1]):
                        dropped.add("time signature changes")
                elif a == 0x59 and len(b) >= 2:
                    if key is None:
                        key = (b[0] - 256 if b[0] > 127 else b[0], b[1])
                elif a == 0x51 and len(b) == 3:
                    tempos[t] = int.from_bytes(b, "big")
                elif a == 0x05:
                    if _text(b):
                        lyrics.setdefault(ti, []).append((t, seq, _text(b)))
                elif a != 0x2F:
                    dropped.add("meta event 0x%02X" % a)
            else:
                has_channel_event = True
                ch, hi = (a & 0x0F) + 1, a & 0xF0
                info = channels.setdefault(ch, _Channel(ch, ti))
                if hi == 0x90 and b[1] > 0:
                    open_notes.setdefault((ch, b[0]), []).append((t, b[1], seq, ti))
                elif hi in (0x80, 0x90):
                    pending = open_notes.get((ch, b[0]))
                    if pending:
                        start, vel, sq, tj = pending.pop(0)
                        if t == start:
                            warnings.append("zero-length note at tick %d lengthened to 1 tick" % start)
                        info.notes.append((start, tj, sq, b[0], max(1, t - start), vel))
                elif hi == 0xB0:
                    info.others.append((t, ti, seq, "cc%d=%d" % (b[0], b[1])))
                elif hi == 0xE0:
                    info.others.append((t, ti, seq, "bend=%d" % ((b[1] << 7 | b[0]) - 8192)))
                elif hi == 0xC0:
                    if info.program is None:
                        info.program = b[0]
                    elif info.program != b[0]:
                        dropped.add("program changes after the first one")
                else:
                    dropped.add("aftertouch messages")
        if not has_channel_event and (ti > 0 or fmt == 0):
            silent.append(ti)
    for (ch, pitch), pending in sorted(open_notes.items()):
        for start, vel, sq, tj in pending:
            warnings.append("note %d on channel %d at tick %d has no note-off: ended at the end of the file" % (pitch, ch, start))
            channels[ch].notes.append((start, tj, sq, pitch, max(1, end - start), vel))

    # ---- which MIDI track owns which channels; an empty named track is taken as the drums track
    owners = {}
    for info in channels.values():
        owners.setdefault(info.track, []).append(info.ch)
    decl = [((info.track, info.ch), names.get(info.track) if len(owners[info.track]) == 1 else None, info.ch)
            for info in channels.values()]
    empty_drums = False
    for ti in silent:
        if ti in names and 10 not in channels and not empty_drums:
            decl.append(((ti, 0), names[ti], None))
            empty_drums = True
        elif ti in names:
            dropped.add("empty tracks")
    decl.sort(key=lambda d: d[0])
    for ti in lyrics:
        if len(owners.get(ti, ())) != 1:
            dropped.add("lyrics in tracks that do not own exactly one channel")

    # ---- header
    out = ["loma 1.0"]
    if title is not None:
        out.append('title "%s"' % title)
    first_us = tempos.pop(0, None)
    if first_us is None:
        warnings.append("no tempo at tick 0: 120 BPM assumed")
        out.append("tempo 120")
    else:
        bpm, exact = _bpm(first_us)
        if not exact:
            warnings.append("tempo %d us per quarter is not an integer BPM: %d BPM used" % (first_us, bpm))
        out.append("tempo %d" % bpm)
    if meter is None:
        meter = (4, 4)
    elif not (1 <= meter[0] <= 64 and meter[1] in VALID_DENOMINATORS):
        warnings.append("time signature %d/%d is not supported: 4/4 used" % meter)
        meter = (4, 4)
    out.append("meter %d/%d" % meter)
    if key is not None:
        if key in _KEY_NAMES:
            out.append("key %s" % _KEY_NAMES[key])
        else:
            dropped.add("invalid key signature")
    out.append("")

    used, track_names = set(), {}

    def unique(wanted, fallback):
        name = wanted if wanted and NAME_RE.fullmatch(wanted) and wanted not in RESERVED else fallback
        base, n = name, 2
        while name in used:
            name = "%s_%d" % (base, n)
            n += 1
        used.add(name)
        return name

    for order, wanted, ch in decl:
        if ch is None or ch == 10:
            track_names[10] = unique(wanted, "drumkit")
            out.append("track %s drums" % track_names[10])
        else:
            track_names[ch] = unique(wanted, "ch%d" % ch)
            out.append("track %s ch=%d program=%d" % (track_names[ch], ch, channels[ch].program or 0))

    out.extend(["", "section main"])
    if end > 0:
        out.append("  bar C len=/#%d" % end)
    out.extend(["end", "play main", ""])

    # ---- events
    for t in sorted(tempos):
        bpm, exact = _bpm(tempos[t])
        if not exact:
            warnings.append("tempo %d us per quarter at tick %d is not an integer BPM: %d BPM used" % (tempos[t], t, bpm))
        out.append("at %d tempo=%d" % (t, bpm))
    for order, wanted, ch in decl:
        if ch is None:
            continue
        info, name = channels[ch], track_names[ch]
        lines, starts = [], set()
        for start, ti, seq, pitch, dur, vel in info.notes:
            if (pitch, start) in starts:
                warnings.append("duplicate note %d at tick %d on channel %d dropped" % (pitch, start, ch))
                continue
            starts.add((pitch, start))
            lines.append((start, ti, seq, "at %d %s %s d=%d v=%d" % (start, name, _pitch_name(pitch, ch == 10), dur, vel)))
        for t, ti, seq, text in info.others:
            lines.append((t, ti, seq, "at %d %s %s" % (t, name, text)))
        if len(owners[info.track]) == 1:
            for t, seq, text in lyrics.get(info.track, ()):
                lines.append((t, info.track, seq, 'at %d %s "%s"' % (t, name, text)))
        lines.sort(key=lambda x: x[:3])
        out.extend(x[3] for x in lines)
    for what in sorted(dropped):
        warnings.append("not representable in LOMA, dropped: %s" % what)
    return "\n".join(out) + "\n", warnings
