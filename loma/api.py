"""Public API of the reference compiler."""
import hashlib

from .decompiler import decompile
from .events import canonical_json
from .expander import compile_song
from .midi_writer import write_midi
from .parser import parse

__all__ = ["compile_text", "expand_json", "sha256", "decompile"]


def compile_text(text):
    """LOMA source -> (compiled, midi_bytes). Raises LomaErrors."""
    compiled = compile_song(parse(text))
    return compiled, write_midi(compiled)


def expand_json(text):
    """LOMA source -> canonical JSON of the expanded events. Raises LomaErrors."""
    compiled = compile_song(parse(text))
    return canonical_json(compiled.events, compiled.track_names)


def sha256(data):
    return hashlib.sha256(data).hexdigest()
