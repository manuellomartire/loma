"""Structured errors: code, position, cause, expected value."""

_HEAD_KEYS = ("section", "bar", "chord", "track")


class LomaError(Exception):
    def __init__(self, code, message, line=None, **ctx):
        super().__init__(message)
        self.code = code
        self.message = message
        self.line = line
        self.ctx = ctx

    def to_dict(self):
        d = {"code": self.code}
        if self.line is not None:
            d["line"] = self.line
        for k in _HEAD_KEYS:
            if k in self.ctx:
                d[k] = self.ctx[k]
        d["message"] = self.message
        for k in sorted(self.ctx):
            if k not in d:
                d[k] = self.ctx[k]
        return d

    def format(self):
        s = self.code
        if self.line is not None:
            s += " line %d" % self.line
        if "bar" in self.ctx:
            s += " bar %s" % self.ctx["bar"]
            if "chord" in self.ctx:
                s += " (%s)" % self.ctx["chord"]
        if "track" in self.ctx:
            s += " track %s" % self.ctx["track"]
        return s + ": " + self.message


class LomaErrors(Exception):
    """Raised when a file has one or more errors. Errors are unique and sorted by (line, code)."""

    def __init__(self, errors):
        seen, uniq = set(), []
        for e in errors:
            key = (e.code, e.line, e.ctx.get("track"))
            if key not in seen:
                seen.add(key)
                uniq.append(e)
        uniq.sort(key=lambda e: (e.line if e.line is not None else 0, e.code))
        super().__init__("%d error(s)" % len(uniq))
        self.errors = uniq
