"""Validation, expansion and note resolution.

Per track:  expand -> attributes -> ties -> sounding length -> offset
            -> duplicates/overlaps -> events
"""
from .errors import LomaError, LomaErrors
from .events import Event, sort_events
from .model import (Bar, MAX_TICK, MAX_NOTES, MAX_CONTROLS, MAX_BARS, MAX_ELEMENTS, DEFAULT_VEL,
                    GATE_PCT, BASS_TONE, WHOLE, PPQ, RAMP_STEP)
from .util import floor_div, duration_name


class Compiled:
    def __init__(self, song, events, end_tick):
        self.song = song
        self.events = events
        self.end_tick = end_tick

    @property
    def track_names(self):
        return [t.name for t in self.song.tracks]


class RItem:
    """A note group or a group of control events placed on the song timeline."""
    __slots__ = ("kind", "pos", "dur", "notes", "tie", "explicit", "play_idx", "ctx", "line", "controls")

    def __init__(self, kind, pos, line, ctx, play_idx, dur=0, notes=None, tie=False, explicit=False, controls=None):
        self.kind = kind            # "note" or "ctl"
        self.pos = pos
        self.dur = dur
        self.notes = notes          # [(pitch, attrs)]
        self.tie = tie
        self.explicit = explicit
        self.play_idx = play_idx
        self.ctx = ctx
        self.line = line
        self.controls = controls    # [(tick, kind, data)]


class Budget:
    """Global limits on the amount of expanded material. Exceeding one of them is fatal."""

    def __init__(self):
        self.notes = 0
        self.controls = 0
        self.elements = 0

    def element(self, line):
        self.elements += 1
        if self.elements > MAX_ELEMENTS:
            raise LomaErrors([LomaError("E018", "more than %d expanded elements" % MAX_ELEMENTS, line)])

    def add(self, notes, controls, line):
        self.notes += notes
        self.controls += controls
        if self.notes > MAX_NOTES:
            raise LomaErrors([LomaError("E018", "more than %d notes" % MAX_NOTES, line)])
        if self.controls > MAX_CONTROLS:
            raise LomaErrors([LomaError("E018", "more than %d control events" % MAX_CONTROLS, line)])


def check_pitch(pitch, line, ctx):
    if not 0 <= pitch <= 127:
        raise LomaError("E006", "pitch %d is outside the MIDI range 0-127" % pitch, line, **ctx)
    return pitch


def transposed(pitch, transpose, drums, line, ctx):
    if drums or transpose == 0:
        return pitch
    p = pitch + transpose
    if not 0 <= p <= 127:
        raise LomaError("E006", "transposition by %+d moves pitch %d outside the MIDI range 0-127 (result %d)" % (
            transpose, pitch, p), line, **ctx)
    return p


def tone_pitch(tone, chord, base, line, ctx):
    idx, shift = tone
    if idx == BASS_TONE:
        return check_pitch(12 * base + chord.bass_pc + shift, line, ctx)
    if idx >= len(chord.intervals):
        raise LomaError("E010", "tone %d does not exist in chord %s (it has %d notes)" % (
            2 * idx + 1, chord.name, len(chord.intervals)), line, **ctx)
    return check_pitch(12 * (base + 1) + chord.root_pc + chord.intervals[idx] + shift, line, ctx)


def ramp(a, b, start, length):
    """(tick, value) pairs of a linear ramp: one every RAMP_STEP ticks, then the exact end value."""
    k = 0
    while k * RAMP_STEP < length:
        yield start + k * RAMP_STEP, a + floor_div((b - a) * (k * RAMP_STEP), length)
        k += 1
    yield start + length, b


class BarExpander:
    def __init__(self, song, budget):
        self.song = song
        self.budget = budget

    def line_defaults(self, tl, p, bar_len, tctx):
        """Line-level attributes for a note at position p in the bar, plus its swing offset."""
        m = {"v": DEFAULT_VEL, "o": 0, "a": "norm"}
        for k in ("o", "d", "a"):
            if k in tl.attrs:
                m[k] = tl.attrs[k]
        v = tl.attrs.get("v")
        if isinstance(v, tuple):
            m["v"] = v[0] + floor_div((v[1] - v[0]) * p, bar_len)
        elif v is not None:
            m["v"] = v
        swing = 0
        name = tl.attrs.get("swing")
        if name is not None:
            sw = self.song.swings.get(name)
            if sw is None:
                raise LomaError("E004", "swing '%s' is not defined" % name, tl.line, **tctx)
            if p % sw.grid == 0:
                swing = sw.table[(p // sw.grid) % len(sw.table)]
        return m, swing

    def notes(self, tl, p, bar_len, tctx, pitches, item_attrs, note_attrs):
        base, swing = self.line_defaults(tl, p, bar_len, tctx)
        out = []
        for pitch, na in zip(pitches, note_attrs):
            m = dict(base)
            m.update(item_attrs)
            m.update(na)
            m["o"] += swing
            out.append((pitch, m))
        return out

    def controls(self, it, tick):
        if it.kind == "lyric":
            self.budget.add(0, 1, it.line)
            return [(tick, "lyric", {"text": it.text})]
        count = 1 if it.b is None else (it.dur + RAMP_STEP - 1) // RAMP_STEP + 1
        self.budget.add(0, count, it.line)
        pairs = [(tick, it.a)] if it.b is None else list(ramp(it.a, it.b, tick, it.dur))
        if it.kind == "cc":
            return [(t, "cc", {"controller": it.num, "value": v}) for t, v in pairs]
        return [(t, "bend", {"value": v}) for t, v in pairs]

    def fill_pattern(self, tl, part, chord, start, origin, length, bar_len, play_idx, transpose, tctx, out, single):
        pats = []
        for name in part.use:
            pat = self.song.patterns.get(name)
            if pat is None:
                raise LomaError("E004", "pattern '%s' is not defined" % name, tl.line, **tctx)
            pats.append(pat)
        pos, i = 0, 0
        while pos < length:
            pat = pats[i % len(pats)]
            i += 1
            if pos + pat.length > length:
                raise LomaError("E009", "pattern %s (%d ticks) does not fill the %d-tick %s exactly" % (
                    ",".join(part.use), sum(p.length for p in pats), length, "bar" if single else "chord segment"),
                    tl.line, expected=length, got=sum(p.length for p in pats), **tctx)
            for step in pat.steps:
                self.budget.element(tl.line)
                if step.kind == "tones":
                    self.budget.add(len(step.tones), 0, tl.line)
                    pitches = [transposed(tone_pitch(t, chord, pat.base, tl.line, tctx), transpose, False, tl.line, tctx)
                               for t in step.tones]
                    p = origin + pos
                    notes = self.notes(tl, p, bar_len, tctx, pitches, step.attrs, [{}] * len(pitches))
                    out.append(RItem("note", start + p, tl.line, tctx, play_idx, dur=step.dur, notes=notes))
                pos += step.dur

    def fill_explicit(self, tl, part, bar, seg, start, origin, length, bar_len, play_idx, transpose, tctx, out, single):
        drums = tl.track.kind == "drums"
        cursor = 0
        for it in part.items:
            self.budget.element(it.line)
            p = origin + cursor
            if it.kind in ("cc", "bend", "lyric"):
                ctl = self.controls(it, start + p)
                out.append(RItem("ctl", start + p, it.line, tctx, play_idx, controls=ctl))
                continue
            if it.kind == "rest":
                cursor += it.dur
                continue
            if it.kind == "voiced":
                voicing = self.song.voicings.get(it.name)
                if voicing is None:
                    raise LomaError("E004", "voicing '%s' is not defined" % it.name, it.line, **tctx)
                chord = bar.chords[min(p // seg, len(bar.chords) - 1)]
                pitches = [tone_pitch(t, chord, voicing.base, it.line, tctx) for t in voicing.tones]
                note_attrs = [{}] * len(pitches)
            else:
                pitches = [n[0] for n in it.notes]
                note_attrs = [n[1] for n in it.notes]
            self.budget.add(len(pitches), 0, it.line)
            pitches = [transposed(x, transpose, drums, it.line, tctx) for x in pitches]
            notes = self.notes(tl, p, bar_len, tctx, pitches, it.attrs or {}, note_attrs)
            out.append(RItem("note", start + p, it.line, tctx, play_idx, dur=it.dur, notes=notes,
                             tie=it.tie, explicit=it.explicit))
            cursor += it.dur
        if cursor != length:
            where = "bar" if single else "segment"
            extra = {"expected": length, "got": cursor}
            if cursor < length:
                miss = length - cursor
                name = duration_name(miss)
                msg = "%s length mismatch. Expected %d ticks, got %d. Missing %d ticks%s." % (
                    where, length, cursor, miss, " (= %s)" % name if name else "")
                extra["missing"] = miss
                if name:
                    extra["suggestion"] = "add_rest"
                    extra["duration"] = name
            else:
                msg = "%s length mismatch. Expected %d ticks, got %d. Exceeds by %d ticks." % (
                    where, length, cursor, cursor - length)
                extra["excess"] = cursor - length
            line = part.items[-1].line if part.items else tl.line
            raise LomaError("E003", msg, line, **dict(tctx, **extra))

    def expand(self, sec, bar, start, play_idx, transpose, bar_len):
        """Returns [(track index, [RItem])]. Raises the first error of the bar."""
        ctx = {"section": sec.name, "bar": bar.number, "chord": " ".join(c.name for c in bar.chords)}
        n = len(bar.chords)
        if bar_len % n:
            raise LomaError("E014", "bar of %d ticks cannot be split into %d equal parts" % (bar_len, n), bar.line, **ctx)
        seg = bar_len // n
        result = []
        for tl in bar.track_lines:
            tctx = dict(ctx, track=tl.track.name)
            single = len(tl.parts) == 1
            if not single and len(tl.parts) != n:
                raise LomaError("E021", "track line has %d segments but the bar has %d chord(s)" % (len(tl.parts), n),
                                tl.line, expected=n, got=len(tl.parts), **tctx)
            out = []
            for k, part in enumerate(tl.parts):
                if part.use is not None:
                    for kk in (range(n) if single else (k,)):
                        self.fill_pattern(tl, part, bar.chords[kk], start, kk * seg, seg, bar_len,
                                          play_idx, transpose, tctx, out, n == 1)
                elif single:
                    self.fill_explicit(tl, part, bar, seg, start, 0, bar_len, bar_len, play_idx, transpose, tctx, out, True)
                else:
                    self.fill_explicit(tl, part, bar, seg, start, k * seg, seg, bar_len, play_idx, transpose, tctx, out, False)
            result.append((tl.track.index, out))
        return result


def count_bars(body):
    total = 0
    for node in body:
        total += 1 if isinstance(node, Bar) else node.times * count_bars(node.body)
        if total > MAX_BARS:
            return total
    return total


def flatten(body, out):
    for node in body:
        if isinstance(node, Bar):
            out.append(node)
        else:
            for _ in range(node.times):
                flatten(node.body, out)


def all_bars(body, out):
    for node in body:
        if isinstance(node, Bar):
            out.append(node)
        else:
            all_bars(node.body, out)


def build_tempo_map(song, timeline):
    """One tempo per tick, the last one wins."""
    tmap = {0: song.tempo}
    for (sec, bar, start, pi, tr, length) in timeline:
        if bar.tempo is None:
            continue
        n, m = bar.tempo
        if m is None:
            tmap[start] = n
        else:
            k = 0
            while k * PPQ < length:
                tmap[start + k * PPQ] = n + floor_div((m - n) * (k * PPQ), length)
                k += 1
            tmap[start + length] = m
    for at in song.ats:
        if at.kind == "tempo":
            tmap[at.tick] = at.value
    return tmap


def resolve_ties(track, items, errors):
    n = len(items)
    cont = [None] * n
    total = [it.dur for it in items]
    for i, it in enumerate(items):
        if it.kind != "note" or not it.tie:
            continue
        j = i + 1
        while j < n and items[j].kind != "note":
            j += 1
        err = None
        if track.kind == "drums":
            err = "ties are not allowed on drum tracks"
        elif j >= n:
            err = "tie has no following note"
        else:
            nx = items[j]
            if nx.pos != it.pos + it.dur:
                err = "the tied note must start exactly where this one ends"
            elif nx.play_idx != it.play_idx:
                err = "a tie cannot cross into a different 'play' command"
            elif sorted(p for p, _ in nx.notes) != sorted(p for p, _ in it.notes):
                err = "tied notes must have the same pitch (same pitches for chords)"
            elif nx.explicit:
                err = "the tied note must not have its own attributes (v, o, d, a)"
        if err:
            errors.append(LomaError("E012", "invalid tie: " + err, it.line, **it.ctx))
            continue
        head = cont[i] if cont[i] is not None else i
        cont[j] = head
        total[head] += items[j].dur
    return cont, total


def compile_song(song):
    errors = []
    budget = Budget()
    expander = BarExpander(song, budget)
    meter_len = song.meter[0] * (WHOLE // song.meter[1])

    # ---- timeline
    timeline, cursor, played, bars = [], 0, set(), 0
    for pi, play in enumerate(song.plays):
        sec = song.sections.get(play.name)
        if sec is None:
            errors.append(LomaError("E004", "section '%s' is not defined" % play.name, play.line))
            continue
        played.add(play.name)
        bars += play.times * count_bars(sec.body)
        if bars > MAX_BARS:
            raise LomaErrors([LomaError("E018", "the song expands to more than %d bars" % MAX_BARS, play.line)])
        flat = []
        flatten(sec.body, flat)
        for _ in range(play.times):
            for bar in flat:
                length = bar.len_ticks or meter_len
                timeline.append((sec, bar, cursor, pi, play.transpose, length))
                cursor += length
                if cursor > MAX_TICK:
                    raise LomaErrors([LomaError("E018", "the song is longer than the maximum of %d ticks" % MAX_TICK, play.line)])
    total_len = cursor

    # ---- expand bars (first error of each bar)
    track_items = [[] for _ in song.tracks]
    for (sec, bar, start, pi, tr, length) in timeline:
        try:
            for ti, items in expander.expand(sec, bar, start, pi, tr, length):
                track_items[ti].extend(items)
        except LomaError as e:
            errors.append(e)
    for sec in song.sections.values():          # sections never played are still validated
        if sec.name in played:
            continue
        flat = []
        all_bars(sec.body, flat)
        for bar in flat:
            try:
                expander.expand(sec, bar, 0, -1, 0, bar.len_ticks or meter_len)
            except LomaError as e:
                errors.append(e)

    # ---- tempo
    events = []
    tempo_map = build_tempo_map(song, timeline)
    for tick in sorted(tempo_map):
        events.append(Event(tick, "tempo", -1, 0, 0, 0, {"bpm": tempo_map[tick]}))

    # ---- ties, sounding length, offset, sequence numbers
    resolved = []
    counters = [0] * len(song.tracks)
    for track in song.tracks:
        items = track_items[track.index]
        cont, total = resolve_ties(track, items, errors)
        c = 0
        for i, it in enumerate(items):
            if it.kind == "ctl":
                for tick, kind, data in it.controls:
                    if tick > MAX_TICK:
                        errors.append(LomaError("E018", "event at tick %d exceeds the maximum %d" % (tick, MAX_TICK), it.line, **it.ctx))
                        break
                    events.append(Event(tick, kind, track.index, track.ch, 0, c, data))
                    c += 1
            elif cont[i] is None:
                for pitch, m in it.notes:
                    sounding = m["d"] if "d" in m else max(1, total[i] * GATE_PCT[m["a"]] // 100)
                    start = max(0, it.pos + m["o"])
                    resolved.append({"track": track, "pitch": pitch, "vel": m["v"], "start": start,
                                     "end": start + sounding, "on": c, "off": c + 1, "line": it.line, "ctx": it.ctx})
                    c += 2
        counters[track.index] = c
    for at in song.ats:                         # 'at' events are numbered last, in file order
        if at.kind == "tempo":
            continue
        c = counters[at.track.index]
        ctx = {"track": at.track.name}
        if at.kind == "note":
            budget.add(1, 0, at.line)
            resolved.append({"track": at.track, "pitch": at.pitch, "vel": at.v, "start": at.tick,
                             "end": at.tick + at.d, "on": c, "off": c + 1, "line": at.line, "ctx": ctx})
            counters[at.track.index] = c + 2
            continue
        budget.add(0, 1, at.line)
        if at.kind == "cc":
            data = {"controller": at.num, "value": at.value}
        elif at.kind == "bend":
            data = {"value": at.value}
        else:
            data = {"text": at.text}
        events.append(Event(at.tick, at.kind, at.track.index, at.track.ch, 0, c, data))
        counters[at.track.index] = c + 1

    # ---- duplicates and overlaps (same channel and pitch)
    groups = {}
    for n in resolved:
        groups.setdefault((n["track"].ch, n["pitch"]), []).append(n)
    for key in sorted(groups):
        lst = sorted(groups[key], key=lambda n: (n["start"], n["on"]))
        for a, b in zip(lst, lst[1:]):
            if a["start"] == b["start"]:
                errors.append(LomaError("E017", "duplicate note: pitch %d starts twice at tick %d on channel %d" % (
                    b["pitch"], b["start"], key[0]), b["line"], **b["ctx"]))
            elif a["end"] > b["start"]:
                a["end"] = b["start"]
    for n in resolved:
        if n["end"] > MAX_TICK:
            errors.append(LomaError("E018", "event at tick %d exceeds the maximum %d" % (n["end"], MAX_TICK), n["line"], **n["ctx"]))
    if errors:
        raise LomaErrors(errors)

    for n in resolved:
        tr = n["track"]
        events.append(Event(n["start"], "note_on", tr.index, tr.ch, n["pitch"], n["on"], {"vel": n["vel"]}))
        events.append(Event(n["end"], "note_off", tr.index, tr.ch, n["pitch"], n["off"]))
    events = sort_events(events)
    end_tick = max([total_len] + [e.tick for e in events])
    return Compiled(song, events, end_tick)
