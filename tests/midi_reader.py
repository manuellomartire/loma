"""Tiny independent SMF reader used only by the tests (does not share code with the writer)."""


def read_vlq(b, i):
    n = 0
    while True:
        c = b[i]
        i += 1
        n = (n << 7) | (c & 0x7F)
        if not c & 0x80:
            return n, i


def read_midi(data):
    assert data[:4] == b"MThd" and int.from_bytes(data[4:8], "big") == 6
    fmt = int.from_bytes(data[8:10], "big")
    ntr = int.from_bytes(data[10:12], "big")
    div = int.from_bytes(data[12:14], "big")
    i = 14
    tracks = []
    for _ in range(ntr):
        assert data[i:i + 4] == b"MTrk"
        ln = int.from_bytes(data[i + 4:i + 8], "big")
        body = data[i + 8:i + 8 + ln]
        assert len(body) == ln
        i += 8 + ln
        j, tick, evs = 0, 0, []
        while j < len(body):
            d, j = read_vlq(body, j)
            tick += d
            st = body[j]
            assert st & 0x80, "running status is not allowed"
            if st == 0xFF:
                kind = body[j + 1]
                ln2, k = read_vlq(body, j + 2)
                evs.append((tick, "meta", kind, bytes(body[k:k + ln2])))
                j = k + ln2
            else:
                hi = st & 0xF0
                n = 2 if hi in (0x80, 0x90, 0xA0, 0xB0, 0xE0) else 1
                evs.append((tick, "midi", st, tuple(body[j + 1:j + 1 + n])))
                j += 1 + n
        tracks.append(evs)
        assert i <= len(data)
    assert i == len(data), "trailing bytes"
    return fmt, div, tracks
