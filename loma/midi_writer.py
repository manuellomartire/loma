"""Canonical Standard MIDI File writer. No timestamps, no running status."""
from .model import PPQ
from .util import vlq, bpm_to_us


def _chunk(tag, data):
    return tag + len(data).to_bytes(4, "big") + data


def _meta(kind, payload):
    return bytes([0xFF, kind]) + vlq(len(payload)) + payload


def _track_bytes(events, end_tick):
    """events: list of (tick, bytes) already in canonical order."""
    out = bytearray()
    prev = 0
    for tick, data in events:
        out += vlq(tick - prev) + data
        prev = tick
    out += vlq(end_tick - prev) + _meta(0x2F, b"")
    return _chunk(b"MTrk", bytes(out))


def _time_signature(num, den):
    return _meta(0x58, bytes([num, den.bit_length() - 1, 24, 8]))


def _key_signature(sf, mi):
    return _meta(0x59, bytes([sf & 0xFF, mi]))


def _encode(e, status):
    if e.kind == "note_on":
        return bytes([0x90 | status, e.pitch, e.data["vel"]])
    if e.kind == "note_off":
        return bytes([0x80 | status, e.pitch, 0x40])
    if e.kind == "cc":
        return bytes([0xB0 | status, e.data["controller"], e.data["value"]])
    if e.kind == "bend":
        value = e.data["value"] + 8192
        return bytes([0xE0 | status, value & 0x7F, value >> 7])
    return _meta(0x05, e.data["text"].encode("utf-8"))


def write_midi(compiled):
    song = compiled.song
    end = compiled.end_tick

    conductor = []
    if song.title is not None:
        conductor.append((0, _meta(0x03, song.title.encode("utf-8"))))
    conductor.append((0, _time_signature(*compiled.meter)))
    if compiled.key is not None:
        conductor.append((0, _key_signature(*compiled.key)))
    for e in compiled.events:
        if e.kind == "tempo":
            conductor.append((e.tick, _meta(0x51, bpm_to_us(e.data["bpm"]).to_bytes(3, "big"))))
        elif e.kind == "meter":
            conductor.append((e.tick, _time_signature(e.data["num"], e.data["den"])))
        elif e.kind == "key":
            conductor.append((e.tick, _key_signature(e.data["sf"], e.data["mi"])))

    per_track = [[] for _ in song.tracks]
    for e in compiled.events:
        if e.track >= 0:
            per_track[e.track].append(e)

    tracks = [_track_bytes(conductor, end)]
    for t in song.tracks:
        evs = [(0, _meta(0x03, t.name.encode("utf-8")))]
        if t.kind != "drums":
            evs.append((0, bytes([0xC0 | (t.ch - 1), t.program])))
        evs.extend((e.tick, _encode(e, t.ch - 1)) for e in per_track[t.index])
        tracks.append(_track_bytes(evs, end))

    header = b"MThd" + (6).to_bytes(4, "big") + (1).to_bytes(2, "big") + \
        len(tracks).to_bytes(2, "big") + PPQ.to_bytes(2, "big")
    return header + b"".join(tracks)
