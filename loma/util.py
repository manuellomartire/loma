"""Integer helpers. Everything in LOMA is integer arithmetic."""
import re

from .errors import LomaError
from .model import WHOLE, VALID_DENOMINATORS, MAX_DIGITS


def floor_div(a, b):
    """Division rounded toward minus infinity.

    Python's // already does this; the function gives the rule a name so that ports to
    languages that truncate toward zero (C, Java, Rust, JavaScript) know what to implement."""
    if b == 0:
        raise ZeroDivisionError("floor_div by zero")
    return a // b


def to_int(text, line=None):
    """Decimal integer literal with an optional sign; more than MAX_DIGITS digits is E018."""
    digits = text.lstrip("+-")
    if len(digits) > MAX_DIGITS:
        raise LomaError("E018", "number '%s' is too large (at most %d digits)" % (text, MAX_DIGITS), line)
    return int(text)


def vlq(n):
    if n < 0 or n > 0x0FFFFFFF:
        raise ValueError("VLQ out of range")
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def bpm_to_us(bpm):
    return 60000000 // bpm


_DUR = re.compile(r"#([0-9]+)|([0-9]+)(\.\.|\.|t|q|x([0-9]+)/([0-9]+))?")
_FIXED = {None: (1, 1), ".": (3, 2), "..": (7, 4), "t": (2, 3), "q": (4, 5)}


def duration_ticks(spec, line=None):
    """spec is the text after '/': '4', '8.', '8t', '16q', '8x5/4', '#210'."""
    m = _DUR.fullmatch(spec)
    if not m:
        raise LomaError("E001", "invalid duration '/%s'" % spec, line)
    if m.group(1) is not None:
        n = to_int(m.group(1), line)
        if n < 1:
            raise LomaError("E007", "invalid duration '/%s': must be at least 1 tick" % spec, line)
        return n
    n = to_int(m.group(2), line)
    if n not in VALID_DENOMINATORS:
        raise LomaError("E007", "invalid duration '/%s': %d is not one of 1, 2, 4, 8, 16, 32, 64" % (spec, n), line)
    base = WHOLE // n
    mod = m.group(3)
    if mod in _FIXED:
        num, den = _FIXED[mod]
    else:
        count, space = to_int(m.group(4), line), to_int(m.group(5), line)
        if count < 1 or space < 1:
            raise LomaError("E007", "invalid duration '/%s': tuplet numbers must be at least 1" % spec, line)
        num, den = space, count
    if (base * num) % den:
        raise LomaError("E007", "invalid duration '/%s': the result is not a whole number of ticks" % spec, line)
    return base * num // den


_NAMED = []
for _n in VALID_DENOMINATORS:
    for _s in ("", ".", "t"):
        try:
            _NAMED.append((duration_ticks("%d%s" % (_n, _s)), "/%d%s" % (_n, _s)))
        except LomaError:
            pass


def duration_name(ticks):
    """'/8' style name if ticks is exactly one plain, dotted or triplet duration, else None."""
    for value, name in _NAMED:
        if value == ticks:
            return name
    return None
