"""Standard MIDI File reader (formats 0 and 1, running status, sysex), used by the decompiler."""


class MidiError(Exception):
    pass


def _vlq(data, i):
    n = 0
    for _ in range(4):
        if i >= len(data):
            raise MidiError("truncated variable-length quantity")
        c = data[i]
        i += 1
        n = (n << 7) | (c & 0x7F)
        if not c & 0x80:
            return n, i
    raise MidiError("variable-length quantity longer than 4 bytes")


def _track(body):
    events, i, tick, status = [], 0, 0, None
    while i < len(body):
        delta, i = _vlq(body, i)
        tick += delta
        if i >= len(body):
            raise MidiError("truncated track")
        first = body[i]
        if first == 0xFF:
            if i + 1 >= len(body):
                raise MidiError("truncated meta event")
            kind = body[i + 1]
            length, j = _vlq(body, i + 2)
            if j + length > len(body):
                raise MidiError("truncated meta event")
            events.append((tick, "meta", kind, bytes(body[j:j + length])))
            i = j + length
            status = None
        elif first in (0xF0, 0xF7):
            length, j = _vlq(body, i + 1)
            if j + length > len(body):
                raise MidiError("truncated sysex event")
            events.append((tick, "sysex", first, bytes(body[j:j + length])))
            i = j + length
            status = None
        else:
            if first & 0x80:
                status = first
                i += 1
            elif status is None:
                raise MidiError("data byte without a running status")
            hi = status & 0xF0
            if hi == 0xF0:
                raise MidiError("unsupported system message 0x%02X" % status)
            size = 1 if hi in (0xC0, 0xD0) else 2
            if i + size > len(body):
                raise MidiError("truncated channel event")
            data = tuple(body[i:i + size])
            if any(b & 0x80 for b in data):
                raise MidiError("invalid data byte in channel event")
            events.append((tick, "midi", status, data))
            i += size
    return events


def read_midi(data):
    """bytes -> (format, division, [track events]); each event is (tick, type, status/kind, payload)."""
    if len(data) < 14 or data[:4] != b"MThd" or int.from_bytes(data[4:8], "big") < 6:
        raise MidiError("not a Standard MIDI File")
    hlen = int.from_bytes(data[4:8], "big")
    fmt = int.from_bytes(data[8:10], "big")
    ntracks = int.from_bytes(data[10:12], "big")
    division = int.from_bytes(data[12:14], "big")
    if fmt not in (0, 1):
        raise MidiError("unsupported MIDI format %d (only 0 and 1)" % fmt)
    if division & 0x8000 or division == 0:
        raise MidiError("SMPTE time division is not supported")
    i = 8 + hlen
    tracks = []
    while i + 8 <= len(data) and len(tracks) < ntracks:
        tag = data[i:i + 4]
        length = int.from_bytes(data[i + 4:i + 8], "big")
        body = data[i + 8:i + 8 + length]
        if len(body) != length:
            raise MidiError("truncated chunk")
        i += 8 + length
        if tag == b"MTrk":
            tracks.append(_track(body))
    if len(tracks) != ntracks:
        raise MidiError("expected %d tracks, found %d" % (ntracks, len(tracks)))
    return fmt, division, tracks
