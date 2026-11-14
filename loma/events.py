"""Event model, canonical ordering and canonical JSON."""
import json

ORDER = {"tempo": 0, "note_off": 1, "cc": 2, "bend": 2, "lyric": 2, "note_on": 3}


class Event:
    __slots__ = ("tick", "kind", "track", "ch", "pitch", "seq", "data")

    def __init__(self, tick, kind, track, ch, pitch, seq, data=None):
        self.tick = tick
        self.kind = kind
        self.track = track      # track index, -1 for global events
        self.ch = ch
        self.pitch = pitch
        self.seq = seq
        self.data = data or {}

    def key(self):
        return (self.tick, ORDER[self.kind], self.track, self.ch, self.pitch, self.seq)

    def to_dict(self, track_names):
        d = {"tick": self.tick, "type": self.kind}
        if self.kind == "tempo":
            d["bpm"] = self.data["bpm"]
            return d
        d["track"] = track_names[self.track]
        if self.kind == "lyric":
            d["text"] = self.data["text"]
            return d
        d["ch"] = self.ch
        if self.kind == "note_on":
            d["pitch"] = self.pitch
            d["vel"] = self.data["vel"]
        elif self.kind == "note_off":
            d["pitch"] = self.pitch
        elif self.kind == "cc":
            d["controller"] = self.data["controller"]
            d["value"] = self.data["value"]
        else:
            d["value"] = self.data["value"]
        return d


def sort_events(events):
    return sorted(events, key=Event.key)


def canonical_json(events, track_names):
    items = [json.dumps(e.to_dict(track_names), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
             for e in events]
    return "[" + ",".join(items) + "]\n"
