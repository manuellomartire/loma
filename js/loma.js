#!/usr/bin/env node
// LOMA 1.0 - second implementation (JavaScript, no dependencies).
// It exists to check conformance: for every input it must produce the same events and the
// same MIDI bytes as the Python reference compiler. All arithmetic is on integers.
// The compiler and the decompiler use only standard JavaScript, so the same file runs in
// Node.js (command line, below) and in a browser (docs/index.html embeds it).
"use strict";

const PPQ = 480;
const WHOLE = 1920;
const RAMP_STEP = 60;
const MAX_TICK = 268435455;
const MAX_NOTES = 1000000;
const MAX_CONTROLS = 1000000;
const MAX_BARS = 100000;
const MAX_ELEMENTS = 4000000;
const MAX_DEPTH = 16;
const MAX_REPEAT = 1000;
const MAX_DIGITS = 9;
const DEFAULT_VEL = 80;
const VALID_DENOMINATORS = [1, 2, 4, 8, 16, 32, 64];
const GATE_PCT = new Map([["leg", 100], ["norm", 90], ["stac", 50]]);
const VERSIONS = new Map([["0.1", 1], ["0.2", 2], ["0.3", 3], ["1.0", 10], ["1.1", 11]]);
const RESERVED = new Set(["loma", "title", "tempo", "meter", "key", "track", "pattern", "swing",
  "voicing", "section", "play", "at", "bar", "end", "repeat", "use", "from", "r", "pedal", "bend", "drums"]);
const PITCH_CLASS = new Map([["C", 0], ["D", 2], ["E", 4], ["F", 5], ["G", 7], ["A", 9], ["B", 11]]);
const DRUMS = new Map([["kick", 36], ["snare", 38], ["hat", 42], ["ohat", 46], ["crash", 49],
  ["ride", 51], ["tom1", 50], ["tom2", 47]]);
const CHORDS_01 = new Map([["", [0, 4, 7]], ["m", [0, 3, 7]], ["7", [0, 4, 7, 10]], ["maj7", [0, 4, 7, 11]],
  ["m7", [0, 3, 7, 10]], ["dim", [0, 3, 6]], ["aug", [0, 4, 8]], ["sus2", [0, 2, 7]], ["sus4", [0, 5, 7]]]);
const CHORDS_03 = new Map([["5", [0, 7]], ["6", [0, 4, 7, 9]], ["m6", [0, 3, 7, 9]], ["dim7", [0, 3, 6, 9]],
  ["m7b5", [0, 3, 6, 10]], ["mmaj7", [0, 3, 7, 11]], ["7sus4", [0, 5, 7, 10]], ["7b9", [0, 4, 7, 10, 13]],
  ["7#9", [0, 4, 7, 10, 15]], ["add9", [0, 4, 7, 14]], ["madd9", [0, 3, 7, 14]], ["9", [0, 4, 7, 10, 14]],
  ["maj9", [0, 4, 7, 11, 14]], ["m9", [0, 3, 7, 10, 14]], ["11", [0, 4, 7, 10, 14, 17]],
  ["m11", [0, 3, 7, 10, 14, 17]], ["13", [0, 4, 7, 10, 14, 21]]]);
const TONES_01 = new Set([1, 3, 5, 7, 8, 10, 12, 14]);
const BASS_TONE = -1;
const KEY_MAJOR = new Map([["C", 0], ["G", 1], ["D", 2], ["A", 3], ["E", 4], ["B", 5], ["F#", 6], ["C#", 7],
  ["F", -1], ["Bb", -2], ["Eb", -3], ["Ab", -4], ["Db", -5], ["Gb", -6], ["Cb", -7]]);
const KEY_MINOR = new Map([["A", 0], ["E", 1], ["B", 2], ["F#", 3], ["C#", 4], ["G#", 5], ["D#", 6], ["A#", 7],
  ["D", -1], ["G", -2], ["C", -3], ["F", -4], ["Bb", -5], ["Eb", -6], ["Ab", -7]]);
const TOP_KEYWORDS = new Set(["title", "tempo", "meter", "key", "track", "pattern", "swing", "voicing",
  "section", "play", "at"]);
const ORDER = new Map([["meter", -2], ["key", -1], ["tempo", 0], ["note_off", 1], ["cc", 2], ["bend", 2], ["lyric", 2], ["note_on", 3]]);

// ---------------------------------------------------------------------------- errors

class LomaError extends Error {
  constructor(code, message, line, ctx) {
    super(message);
    this.code = code;
    this.line = line === undefined ? null : line;
    this.ctx = ctx || {};
  }

  toJSON() {
    const d = { code: this.code };
    if (this.line !== null) d.line = this.line;
    for (const k of ["section", "bar", "chord", "track"]) if (k in this.ctx) d[k] = this.ctx[k];
    d.message = this.message;
    for (const k of Object.keys(this.ctx).sort()) if (!(k in d)) d[k] = this.ctx[k];
    return d;
  }
}

class LomaErrors extends Error {
  constructor(errors) {
    const seen = new Set();
    const uniq = [];
    for (const e of errors) {
      const key = e.code + "|" + e.line + "|" + (e.ctx.track === undefined ? "" : e.ctx.track);
      if (!seen.has(key)) {
        seen.add(key);
        uniq.push(e);
      }
    }
    uniq.sort((a, b) => ((a.line || 0) - (b.line || 0)) || (a.code < b.code ? -1 : a.code > b.code ? 1 : 0));
    super(uniq.length + " error(s)");
    this.errors = uniq;
  }
}

class Skip extends Error {}
class Quiet extends Error {}

// ---------------------------------------------------------------------------- suggestions

function asciiLower(text) {
  return text.replace(/[A-Z]/g, (c) => String.fromCharCode(c.charCodeAt(0) + 32));
}

function asciiUpper(text) {
  return text.replace(/[a-z]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 32));
}

// Levenshtein distance between two arrays of code points.
function editDistance(a, b) {
  let prev = [];
  for (let j = 0; j <= b.length; j++) prev.push(j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      cur.push(Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] !== b[j - 1] ? 1 : 0)));
    }
    prev = cur;
  }
  return prev[b.length];
}

// The candidate nearest to a mistyped name, or null. Case is ignored (ASCII only). A candidate
// is accepted within 2 edits, and only if the edits are fewer than the length of both names;
// ties go to the first candidate in code point order.
function closest(name, candidates) {
  const low = Array.from(asciiLower(name));
  if (low.length === 0 || low.length > 64) return null;
  let best = null, bestD = 3;
  for (const cand of Array.from(candidates).sort()) {
    const c = Array.from(asciiLower(cand));
    const d = editDistance(low, c);
    if (d < bestD && d < c.length && d < low.length) {
      best = cand;
      bestD = d;
    }
  }
  return best;
}

// [text to append to the message, extra fields of the error] for a mistyped name.
function hint(name, candidates) {
  const cand = closest(name, candidates);
  if (cand === null || cand === name) return ["", {}];
  return [" Did you mean '" + cand + "'?", { did_you_mean: cand }];
}

// ---------------------------------------------------------------------------- integer helpers

function floorDiv(a, b) {
  let q = Math.trunc(a / b);
  if (a % b !== 0 && (a < 0) !== (b < 0)) q -= 1;
  return q;
}

function toInt(text, line) {
  if (text.replace(/^[+-]+/, "").length > MAX_DIGITS) {
    throw new LomaError("E018", "number '" + text + "' is too large (at most " + MAX_DIGITS + " digits)", line);
  }
  return parseInt(text, 10);
}

function vlq(n) {
  const out = [n & 0x7F];
  n = Math.floor(n / 128);
  while (n > 0) {
    out.push((n & 0x7F) | 0x80);
    n = Math.floor(n / 128);
  }
  return out.reverse();
}

const DUR_FULL = /^(?:#([0-9]+)|([0-9]+)(\.\.|\.|t|q|x([0-9]+)\/([0-9]+))?)$/;
const FIXED = new Map([[undefined, [1, 1]], [".", [3, 2]], ["..", [7, 4]], ["t", [2, 3]], ["q", [4, 5]]]);

function durationTicks(spec, line) {
  const m = DUR_FULL.exec(spec);
  if (!m) throw new LomaError("E001", "invalid duration '/" + spec + "'", line);
  if (m[1] !== undefined) {
    const n = toInt(m[1], line);
    if (n < 1) throw new LomaError("E007", "invalid duration '/" + spec + "': must be at least 1 tick", line);
    return n;
  }
  const n = toInt(m[2], line);
  if (!VALID_DENOMINATORS.includes(n)) {
    throw new LomaError("E007", "invalid duration '/" + spec + "': " + n + " is not one of 1, 2, 4, 8, 16, 32, 64", line);
  }
  const base = WHOLE / n;
  let num, den;
  if (FIXED.has(m[3])) {
    [num, den] = FIXED.get(m[3]);
  } else {
    const count = toInt(m[4], line), space = toInt(m[5], line);
    if (count < 1 || space < 1) {
      throw new LomaError("E007", "invalid duration '/" + spec + "': tuplet numbers must be at least 1", line);
    }
    num = space;
    den = count;
  }
  if ((base * num) % den !== 0) {
    throw new LomaError("E007", "invalid duration '/" + spec + "': the result is not a whole number of ticks", line);
  }
  return (base * num) / den;
}

const NAMED = [];
for (const n of VALID_DENOMINATORS) {
  for (const s of ["", ".", "t"]) {
    try {
      NAMED.push([durationTicks(n + s), "/" + n + s]);
    } catch (e) {
      if (!(e instanceof LomaError)) throw e;
    }
  }
}

function durationName(ticks) {
  for (const [value, name] of NAMED) if (value === ticks) return name;
  return null;
}

function toneSpec(n) {
  if (n === 0) return [BASS_TONE, 0];
  if (n % 2 === 1 && n >= 1 && n <= 11) return [(n - 1) / 2, 0];
  if (n % 2 === 0 && n >= 8 && n <= 18) return [(n - 8) / 2, 12];
  return null;
}

// ---------------------------------------------------------------------------- text helpers

const WS = " \t";
const NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
const NAME_FULL = /^[A-Za-z][A-Za-z0-9_]*$/;
const INT_FULL = /^[0-9]+$/;
const SINT_FULL = /^[+-]?[0-9]+$/;
const NAME_Y = /[A-Za-z][A-Za-z0-9_]*/y;
const PITCH_TOKEN_Y = /[A-Za-z][A-Za-z0-9#\-]*/y;
const INT_Y = /[0-9]+/y;
const DUR_TOKEN_Y = /#[0-9]+|[0-9]+(?:\.\.|\.|t|q|x[0-9]+\/[0-9]+)?/y;
const CC_Y = /cc([0-9]+)=([0-9]+)(?:>([0-9]+))?/y;
const BEND_Y = /bend=(-?[0-9]+)(?:>(-?[0-9]+))?/y;
const PITCH_FULL = /^([A-G])([#b]?)(-?[0-9]+)$/;
const MIDI_PITCH_FULL = /^m([0-9]+)$/;
const TRACK_LINE = /^([A-Za-z][A-Za-z0-9_]*)(\{[^}]*\})?[ \t]*:([^]*)$/;
const CHORD_FULL = /^([A-G])([#b]?)([^\/^]*)(?:\^([0-9]+))?(?:\/([A-G])([#b]?))?$/;
const CHORD_LOOSE = /^([A-Ga-g])([#b]?)([^\/^]*)((?:\^[0-9]+)?)((?:\/[A-Ga-g][#b]?)?)$/;
const NAME_PREFIX = /^[A-Za-z][A-Za-z0-9_]*/;
const COMMANDS = ["title", "tempo", "meter", "key", "track", "pattern", "swing", "voicing", "section", "play", "at",
  "bar", "end", "repeat"];
// spellings that other notations use for the qualities of LOMA
const CHORD_ALIASES = new Map([["maj", ""], ["major", ""], ["M", ""], ["min", "m"], ["minor", "m"], ["mi", "m"], ["-", "m"],
  ["M7", "maj7"], ["Maj7", "maj7"], ["ma7", "maj7"], ["major7", "maj7"], ["min7", "m7"], ["mi7", "m7"],
  ["-7", "m7"], ["minor7", "m7"], ["dom7", "7"], ["+", "aug"], ["o", "dim"], ["o7", "dim7"],
  ["m7-5", "m7b5"], ["min7b5", "m7b5"], ["sus", "sus4"], ["7sus", "7sus4"], ["M9", "maj9"],
  ["Maj9", "maj9"], ["min9", "m9"], ["min6", "m6"], ["min11", "m11"], ["mM7", "mmaj7"],
  ["mMaj7", "mmaj7"], ["minmaj7", "mmaj7"], ["add2", "add9"]]);

// The valid chord symbol that a wrong one most likely stands for, or null.
function chordHint(text) {
  const m = CHORD_LOOSE.exec(text);
  if (!m) return null;
  let quality = m[3];
  if (!(CHORDS_01.has(quality) || CHORDS_03.has(quality))) {
    quality = CHORD_ALIASES.has(quality) ? CHORD_ALIASES.get(quality)
      : closest(quality, [...CHORDS_01.keys(), ...CHORDS_03.keys()]);
  }
  if (quality === null) return null;
  const fixed = asciiUpper(m[1]) + m[2] + quality + m[4] + asciiUpper(m[5].slice(0, 2)) + m[5].slice(2);
  return fixed !== text && CHORD_FULL.test(fixed) ? fixed : null;
}

function trim(s) {
  return s.replace(/^[ \t]+/, "").replace(/[ \t]+$/, "");
}

function splitWords(text) {
  return text.split(/[ \t]+/).filter((w) => w !== "");
}

function stripComment(line) {
  let inQuote = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') inQuote = !inQuote;
    else if (ch === "#" && !inQuote && (i === 0 || WS.includes(line[i - 1]))) return line.slice(0, i);
  }
  return line;
}

function splitSegments(text) {
  const parts = [];
  let cur = "", inQuote = false;
  for (const ch of text) {
    if (ch === '"') inQuote = !inQuote;
    if (ch === "|" && !inQuote) {
      parts.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  parts.push(cur);
  return parts;
}

function partition(text, sep) {
  const i = text.indexOf(sep);
  return i < 0 ? [text, false, ""] : [text.slice(0, i), true, text.slice(i + sep.length)];
}

function accidental(acc) {
  return acc === "#" ? 1 : acc === "b" ? -1 : 0;
}

// ---------------------------------------------------------------------------- scanner

class Scanner {
  constructor(parser, text, line) {
    this.p = parser;
    this.t = text;
    this.i = 0;
    this.line = line;
  }

  ws() {
    while (this.i < this.t.length && WS.includes(this.t[this.i])) this.i++;
  }

  eof() {
    this.ws();
    return this.i >= this.t.length;
  }

  peek() {
    return this.i < this.t.length ? this.t[this.i] : "";
  }

  match(rx) {
    rx.lastIndex = this.i;
    const m = rx.exec(this.t);
    if (!m) return null;
    this.i = rx.lastIndex;
    return m;
  }

  take(rx) {
    const m = this.match(rx);
    return m ? m[0] : null;
  }

  near() {
    return trim(this.t.slice(this.i, this.i + 12));
  }

  attrs() {
    if (this.peek() !== "{") return {};
    const j = this.t.indexOf("}", this.i);
    if (j < 0) throw new LomaError("E001", "unclosed '{' in attributes", this.line);
    const body = this.t.slice(this.i + 1, j);
    this.i = j + 1;
    return this.p.parseAttrs(body, this.line, false);
  }

  duration() {
    if (this.peek() !== "/") {
      throw new LomaError("E001", "missing duration (expected '/' followed by e.g. 4, 8, 8., 8t, #210) near '" + this.near() + "'", this.line);
    }
    this.i++;
    const spec = this.take(DUR_TOKEN_Y);
    if (spec === null) throw new LomaError("E001", "invalid duration after '/'", this.line);
    if (spec.includes("q") || spec.includes("x")) this.p.need("0.2", "tuplet duration '/" + spec + "'", this.line);
    return durationTicks(spec, this.line);
  }

  tie() {
    if (this.peek() === "~") {
      this.i++;
      return true;
    }
    return false;
  }

  boundary(extra) {
    const c = this.peek();
    if (c === "" || WS.includes(c) || (extra && extra.includes(c))) return;
    if (c === "~") throw new LomaError("E001", "tie '~' must come right after the duration, before any '{...}'", this.line);
    throw new LomaError("E001", "unexpected '" + this.near() + "' (tokens must be separated by spaces)", this.line);
  }
}

// ---------------------------------------------------------------------------- parser

function isExplicit(item) {
  return Object.keys(item.attrs || {}).length > 0 || (item.notes || []).some((n) => Object.keys(n[1]).length > 0);
}

class Parser {
  constructor() {
    this.song = { version: null, title: null, tempo: 120, meter: [4, 4], key: null, tracks: [],
      patterns: new Map(), swings: new Map(), voicings: new Map(), sections: new Map(), plays: [], ats: [],
      // filled only when the file has syntax errors (see SPEC 13.1)
      failed: { pattern: new Set(), swing: new Set(), voicing: new Set(), section: new Set() }, orphans: [] };
    this.errors = [];
    this.seen = new Set();
    this.version = null;
    this.section = null;
    this.stack = [];
    this.repeats = [];
    this.bar = null;
    this.tl = null;
    this.afterTl = false;
    this.skipBar = false;
    this.barCount = 0;
    this.badTracks = new Set();
    this.meterFailed = false;
    this.curMeter = null;
    this.curKey = null;
    this.meterLost = false;
  }

  need(ver, feature, line) {
    if (this.version < VERSIONS.get(ver)) {
      throw new LomaError("E020", feature + " requires 'loma " + ver + "' or later (this file declares 'loma " +
        this.song.version + "')", line, { feature: feature, requires: ver });
    }
  }

  newName(name, kind, exists, line) {
    if (!name || !NAME_FULL.test(name)) {
      throw new LomaError("E019", "invalid " + kind + " name '" + (name || "") + "' (letters, digits, _; must start with a letter)", line);
    }
    if (RESERVED.has(name)) throw new LomaError("E019", "'" + name + "' is a reserved word and cannot be a " + kind + " name", line);
    if (exists(name)) throw new LomaError("E019", "duplicate " + kind + " name '" + name + "'", line);
    return name;
  }

  trackByName(name, line) {
    for (const t of this.song.tracks) if (t.name === name) return t;
    if (this.badTracks.has(name)) throw new Skip();
    const [text, extra] = hint(name, this.song.tracks.map((t) => t.name));
    throw new LomaError("E008", "track '" + name + "' is not declared (declare it with 'track' before using it)." + text, line, extra);
  }

  once(key, line) {
    if (this.seen.has(key)) throw new LomaError("E001", "'" + key + "' is declared more than once", line);
    this.seen.add(key);
  }

  parseAttrs(body, line, lineLevel) {
    const attrs = {};
    for (const tok of splitWords(body)) {
      if (!tok.includes("=")) throw new LomaError("E001", "invalid attribute '" + tok + "' (expected key=value)", line);
      const [k, , v] = partition(tok, "=");
      if (k === "a") {
        if (!GATE_PCT.has(v)) throw new LomaError("E001", "invalid articulation '" + v + "' (allowed: leg, norm, stac)", line);
        attrs.a = v;
      } else if (k === "swing" && lineLevel) {
        this.need("0.2", "swing", line);
        if (!NAME_FULL.test(v)) throw new LomaError("E001", "invalid swing name '" + v + "'", line);
        attrs.swing = v;
      } else if (k === "v" && lineLevel && v.includes(">")) {
        this.need("0.2", "velocity ramp 'v=N>M'", line);
        const m = /^([0-9]+)>([0-9]+)$/.exec(v);
        if (!m) throw new LomaError("E001", "velocity ramp must be v=N>M, got '" + v + "'", line);
        const lo = toInt(m[1], line), hi = toInt(m[2], line);
        for (const x of [lo, hi]) {
          if (x < 1 || x > 127) throw new LomaError("E001", "velocity must be 1-127, got " + x, line);
        }
        attrs.v = [lo, hi];
      } else if (k === "v" || k === "o" || k === "d") {
        if (!SINT_FULL.test(v)) throw new LomaError("E001", "attribute " + k + " needs an integer, got '" + v + "'", line);
        const n = toInt(v, line);
        if (k === "v" && (n < 1 || n > 127)) throw new LomaError("E001", "velocity must be 1-127, got " + n, line);
        if (k === "d" && n < 1) throw new LomaError("E001", "d must be at least 1 tick, got " + n, line);
        attrs[k] = n;
      } else {
        throw new LomaError("E001", "unknown attribute '" + k + "' (allowed: " + (lineLevel ? "v, o, d, a, swing" : "v, o, d, a") + ")", line);
      }
    }
    return attrs;
  }

  pitch(name, track, line) {
    let m = MIDI_PITCH_FULL.exec(name);
    if (m) {
      this.need("1.0", "numeric pitch '" + name + "'", line);
      const value = toInt(m[1], line);
      if (value > 127) throw new LomaError("E006", "pitch " + name + " is outside the MIDI range 0-127", line);
      return value;
    }
    if (track.kind === "drums") {
      if (!DRUMS.has(name)) {
        const [text, extra] = hint(name, DRUMS.keys());
        throw new LomaError("E001", "unknown drum name '" + name + "' (known: " + Array.from(DRUMS.keys()).sort().join(", ") + ")." + text, line, extra);
      }
      return DRUMS.get(name);
    }
    if (DRUMS.has(name)) throw new LomaError("E001", "'" + name + "' is a drum name but track " + track.name + " is not a drums track", line);
    m = PITCH_FULL.exec(name);
    if (!m) throw new LomaError("E001", "invalid pitch name '" + name + "'", line);
    const value = 12 * (toInt(m[3], line) + 1) + PITCH_CLASS.get(m[1]) + accidental(m[2]);
    if (value < 0 || value > 127) throw new LomaError("E006", "pitch " + name + " is outside the MIDI range 0-127 (value " + value + ")", line);
    return value;
  }

  chord(text, line) {
    const m = CHORD_FULL.exec(text);
    if (!m || !(CHORDS_01.has(m[3]) || CHORDS_03.has(m[3]))) {
      const fixed = chordHint(text);
      if (fixed === null) throw new LomaError("E005", "unknown chord '" + text + "'", line);
      throw new LomaError("E005", "unknown chord '" + text + "'. Did you mean '" + fixed + "'?", line, { did_you_mean: fixed });
    }
    const quality = m[3], inv = m[4], bassLetter = m[5];
    if (!CHORDS_01.has(quality)) this.need("0.3", "chord quality '" + quality + "'", line);
    const rootPc = PITCH_CLASS.get(m[1]) + accidental(m[2]);
    const intervals = (CHORDS_01.get(quality) || CHORDS_03.get(quality)).slice();
    if (inv !== undefined) {
      this.need("0.3", "chord inversion '^" + inv + "'", line);
      const k = toInt(inv, line);
      if (k >= intervals.length) {
        throw new LomaError("E005", "chord '" + text + "': inversion " + k + " is not possible on a " + intervals.length + "-note chord", line);
      }
      for (let i = 0; i < k; i++) intervals[i] += 12;
      intervals.sort((a, b) => a - b);
    }
    let bassPc;
    if (bassLetter !== undefined) {
      this.need("0.3", "slash chord", line);
      bassPc = PITCH_CLASS.get(bassLetter) + accidental(m[6]);
    } else {
      bassPc = rootPc + intervals[0];
    }
    return { name: text, rootPc: rootPc, intervals: intervals, bassPc: bassPc };
  }

  // ---- content
  controlValue(text, lo, hi, what, line) {
    const n = toInt(text, line);
    if (n < lo || n > hi) throw new LomaError("E001", what + " must be " + lo + ".." + hi + ", got " + n, line);
    return n;
  }

  control(sc) {
    let m = sc.match(CC_Y);
    if (m) {
      const num = this.controlValue(m[1], 0, 127, "controller number", sc.line);
      const a = this.controlValue(m[2], 0, 127, "controller value", sc.line);
      const b = m[3] === undefined ? null : this.controlValue(m[3], 0, 127, "controller value", sc.line);
      return ["cc", num, a, b];
    }
    m = sc.match(BEND_Y);
    if (m) {
      const a = this.controlValue(m[1], -8192, 8191, "pitch bend", sc.line);
      const b = m[2] === undefined ? null : this.controlValue(m[2], -8192, 8191, "pitch bend", sc.line);
      return ["bend", 0, a, b];
    }
    return null;
  }

  lyric(sc) {
    const j = sc.t.indexOf('"', sc.i + 1);
    if (j < 0) throw new LomaError("E001", "unclosed '\"' in lyric", sc.line);
    const text = sc.t.slice(sc.i + 1, j);
    sc.i = j + 1;
    if (text === "") throw new LomaError("E001", "empty lyric", sc.line);
    return text;
  }

  parseContent(text, track, line) {
    const sc = new Scanner(this, text, line);
    const items = [];
    while (!sc.eof()) {
      const c = sc.peek();
      if (c === '"') {
        this.need("1.0", "lyrics", line);
        items.push({ kind: "lyric", line: line, text: this.lyric(sc) });
      } else if (sc.t.startsWith("pedal+", sc.i) || sc.t.startsWith("pedal-", sc.i)) {
        if (track.kind === "drums") throw new LomaError("E001", "pedal is not available on drum tracks", line);
        items.push({ kind: "cc", line: line, num: 64, a: sc.t[sc.i + 5] === "+" ? 127 : 0, b: null, dur: 0 });
        sc.i += 6;
      } else if (c === "[") {
        sc.i++;
        const notes = [];
        for (;;) {
          sc.ws();
          if (sc.peek() === "]") {
            sc.i++;
            break;
          }
          if (sc.i >= sc.t.length) throw new LomaError("E001", "unclosed '[' in chord", line);
          const name = sc.take(PITCH_TOKEN_Y);
          if (!name) throw new LomaError("E001", "invalid character '" + sc.peek() + "' inside chord", line);
          const value = this.pitch(name, track, line);
          const attrs = sc.attrs();
          sc.boundary("]");
          notes.push([value, attrs]);
        }
        if (notes.length === 0) throw new LomaError("E001", "empty chord '[]'", line);
        const dur = sc.duration();
        const tie = sc.tie();
        items.push({ kind: "chord", line: line, dur: dur, notes: notes, tie: tie, attrs: sc.attrs() });
      } else if (c === "*") {
        this.need("0.3", "voicing '*NAME'", line);
        if (track.kind === "drums") throw new LomaError("E001", "voicings cannot be used on drum tracks", line);
        sc.i++;
        const name = sc.take(NAME_Y);
        if (!name) throw new LomaError("E001", "'*' must be followed by a voicing name", line);
        const dur = sc.duration();
        const tie = sc.tie();
        items.push({ kind: "voiced", line: line, dur: dur, name: name, tie: tie, attrs: sc.attrs() });
      } else {
        const ctl = this.control(sc);
        if (ctl !== null) {
          const [kind, num, a, b] = ctl;
          this.need("0.2", kind === "cc" ? "control change" : "pitch bend", line);
          items.push({ kind: kind, line: line, num: num, a: a, b: b, dur: b === null ? 0 : sc.duration() });
        } else {
          const name = sc.take(PITCH_TOKEN_Y);
          if (!name) throw new LomaError("E001", "unexpected character '" + c + "'", line);
          if (name === "use") {
            throw new LomaError("E016", "'use PATTERN' cannot be mixed with explicit notes in the same segment", line);
          }
          if (name === "r") {
            const dur = sc.duration();
            if (sc.tie()) throw new LomaError("E012", "a rest cannot be tied", line);
            if (Object.keys(sc.attrs()).length > 0) throw new LomaError("E001", "a rest cannot have attributes", line);
            items.push({ kind: "rest", line: line, dur: dur });
          } else {
            const value = this.pitch(name, track, line);
            const dur = sc.duration();
            const tie = sc.tie();
            items.push({ kind: "note", line: line, dur: dur, notes: [[value, {}]], tie: tie, attrs: sc.attrs() });
          }
        }
      }
      sc.boundary();
    }
    return items;
  }

  // ---- patterns, swings, voicings
  tone(sc) {
    const tok = sc.take(INT_Y);
    if (tok === null) return null;
    const n = toInt(tok, sc.line);
    const spec = toneSpec(n);
    if (spec === null) {
      throw new LomaError("E010", "tone " + n + " does not exist (valid tones: 0, 1 3 5 7 9 11, 8 10 12 14 16 18)", sc.line);
    }
    if (!TONES_01.has(n)) this.need("0.3", "tone " + n, sc.line);
    let shift = 0;
    while (sc.peek() === "+" || sc.peek() === "-") {
      this.need("0.3", "octave marks on tones", sc.line);
      shift += sc.peek() === "+" ? 12 : -12;
      sc.i++;
    }
    return [spec[0], spec[1] + shift];
  }

  step(sc, defaultDur) {
    let tones, kind;
    if (sc.peek() === "(") {
      sc.i++;
      tones = [];
      for (;;) {
        sc.ws();
        if (sc.peek() === ")") {
          sc.i++;
          break;
        }
        const t = this.tone(sc);
        if (t === null) throw new LomaError("E001", "invalid group in pattern (expected tone numbers and ')')", sc.line);
        tones.push(t);
      }
      if (tones.length === 0) throw new LomaError("E001", "empty group '()' in pattern", sc.line);
      kind = "tones";
    } else if (sc.peek() === "r") {
      sc.i++;
      tones = [];
      kind = "rest";
    } else {
      const t = this.tone(sc);
      if (t === null) throw new LomaError("E001", "invalid pattern step near '" + sc.near() + "'", sc.line);
      tones = [t];
      kind = "tones";
    }
    const dur = sc.peek() === "/" ? sc.duration() : defaultDur;
    const attrs = sc.attrs();
    if (kind === "rest" && Object.keys(attrs).length > 0) throw new LomaError("E001", "a rest cannot have attributes", sc.line);
    sc.boundary();
    return { kind: kind, tones: tones, dur: dur, attrs: attrs };
  }

  options(words, allowed, line, what) {
    const opts = new Map();
    for (const w of words) {
      const [k, found, v] = partition(w, "=");
      if (!found || !allowed.includes(k)) {
        throw new LomaError("E001", "invalid " + what + " option '" + w + "' (allowed: " + allowed.join(" ") + ")", line);
      }
      opts.set(k, v);
    }
    return opts;
  }

  baseOption(v, line) {
    if (!/^-?[0-9]+$/.test(v)) throw new LomaError("E001", "base needs an octave number, got '" + v + "'", line);
    const base = toInt(v, line);
    if (base < -1 || base > 9) throw new LomaError("E006", "base octave " + base + " is outside -1..9", line);
    return base;
  }

  durOption(v, line, what) {
    if (!v.startsWith("/")) throw new LomaError("E001", what + " needs a duration like /4, got '" + v + "'", line);
    const spec = v.slice(1);
    if (spec.includes("q") || spec.includes("x")) this.need("0.2", "tuplet duration '/" + spec + "'", line);
    return durationTicks(spec, line);
  }

  cmdPattern(code, line) {
    const [head, found, body] = partition(code, ":");
    if (!found) throw new LomaError("E001", "usage: pattern NAME base=O dur=/D : steps", line);
    const words = splitWords(head);
    const name = this.newName(words.length > 1 ? words[1] : "", "pattern", (n) => this.song.patterns.has(n), line);
    const sc = new Scanner(this, body, line);
    let base, steps;
    if (words.length > 2 && words[2] === "from") {
      this.need("0.2", "'pattern ... from'", line);
      if (words.length < 4) throw new LomaError("E001", "usage: pattern NAME from OTHER [base=O] : INDEX=STEP ...", line);
      const src = this.song.patterns.get(words[3]);
      if (src === undefined) {
        if (this.song.failed.pattern.has(words[3])) throw new Skip();
        const [text, extra] = hint(words[3], this.song.patterns.keys());
        throw new LomaError("E004", "pattern '" + words[3] + "' is not defined (it must be defined before this line)." + text, line, extra);
      }
      const opts = this.options(words.slice(4), ["base"], line, "pattern");
      base = opts.has("base") ? this.baseOption(opts.get("base"), line) : src.base;
      steps = src.steps.slice();
      while (!sc.eof()) {
        const tok = sc.take(INT_Y);
        if (tok === null || sc.peek() !== "=") throw new LomaError("E001", "expected INDEX=STEP near '" + sc.near() + "'", line);
        const idx = toInt(tok, line);
        if (idx < 1 || idx > steps.length) throw new LomaError("E001", "step index " + idx + " is outside 1.." + steps.length, line);
        sc.i++;
        const st = this.step(sc, null);
        if (st.dur === null) st.dur = steps[idx - 1].dur;
        steps[idx - 1] = st;
      }
    } else {
      const opts = this.options(words.slice(2), ["base", "dur"], line, "pattern");
      if (!opts.has("base") || !opts.has("dur")) throw new LomaError("E001", "pattern needs both base=OCTAVE and dur=/DURATION", line);
      base = this.baseOption(opts.get("base"), line);
      const dur = this.durOption(opts.get("dur"), line, "dur");
      steps = [];
      while (!sc.eof()) steps.push(this.step(sc, dur));
      if (steps.length === 0) throw new LomaError("E001", "pattern has no steps", line);
    }
    this.song.patterns.set(name, { name: name, base: base, steps: steps, length: steps.reduce((s, x) => s + x.dur, 0), line: line });
  }

  cmdSwing(code, line) {
    this.need("0.2", "swing", line);
    const [head, found, body] = partition(code, ":");
    if (!found) throw new LomaError("E001", "usage: swing NAME grid=/D : OFFSET OFFSET ...", line);
    const words = splitWords(head);
    const name = this.newName(words.length > 1 ? words[1] : "", "swing", (n) => this.song.swings.has(n), line);
    const opts = this.options(words.slice(2), ["grid"], line, "swing");
    if (!opts.has("grid")) throw new LomaError("E001", "swing needs grid=/DURATION", line);
    const grid = this.durOption(opts.get("grid"), line, "grid");
    const table = [];
    for (const w of splitWords(body)) {
      if (!SINT_FULL.test(w)) throw new LomaError("E001", "swing offsets must be integers, got '" + w + "'", line);
      table.push(toInt(w, line));
    }
    if (table.length === 0) throw new LomaError("E001", "swing has no offsets", line);
    this.song.swings.set(name, { name: name, grid: grid, table: table, line: line });
  }

  cmdVoicing(code, line) {
    this.need("0.3", "voicing", line);
    const [head, found, body] = partition(code, ":");
    if (!found) throw new LomaError("E001", "usage: voicing NAME base=O : TONE TONE ...", line);
    const words = splitWords(head);
    const name = this.newName(words.length > 1 ? words[1] : "", "voicing", (n) => this.song.voicings.has(n), line);
    const opts = this.options(words.slice(2), ["base"], line, "voicing");
    if (!opts.has("base")) throw new LomaError("E001", "voicing needs base=OCTAVE", line);
    const base = this.baseOption(opts.get("base"), line);
    const sc = new Scanner(this, body, line);
    const tones = [];
    while (!sc.eof()) {
      const t = this.tone(sc);
      if (t === null) throw new LomaError("E001", "invalid voicing tone near '" + sc.near() + "'", line);
      sc.boundary();
      tones.push(t);
    }
    if (tones.length === 0) throw new LomaError("E001", "voicing has no tones", line);
    this.song.voicings.set(name, { name: name, base: base, tones: tones, line: line });
  }

  // ---- top-level statements
  header(words, line) {
    if (words.length !== 2 || words[0] !== "loma") {
      throw new LomaError("E001", "the file must start with 'loma VERSION' (e.g. 'loma 1.0')", line);
    }
    if (!VERSIONS.has(words[1])) throw new LomaError("E001", "unsupported version '" + words[1] + "' (supported: " + Array.from(VERSIONS.keys()).join(", ") + ")", line);
    this.song.version = words[1];
    this.version = VERSIONS.get(words[1]);
  }

  cmdTitle(code, line) {
    this.once("title", line);
    const m = /^title[ \t]+"([^"]*)"$/.exec(code);
    if (!m) throw new LomaError("E001", "title needs a quoted string without inner quotes: title \"Name\"", line);
    this.song.title = m[1];
  }

  cmdTempo(words, line) {
    this.once("tempo", line);
    if (words.length !== 2 || !INT_FULL.test(words[1])) throw new LomaError("E001", "usage: tempo BPM (integer)", line);
    const bpm = toInt(words[1], line);
    if (bpm < 4 || bpm > 400) throw new LomaError("E015", "tempo " + bpm + " is outside the range 4-400 BPM", line);
    this.song.tempo = bpm;
  }

  meterValue(text, line, usage) {
    const m = /^([0-9]+)\/([0-9]+)$/.exec(text);
    if (!m) throw new LomaError("E001", usage, line);
    const num = toInt(m[1], line), den = toInt(m[2], line);
    if (num < 1 || num > 64 || !VALID_DENOMINATORS.includes(den)) {
      throw new LomaError("E018", "meter " + num + "/" + den + " is outside the limits (numerator 1-64, denominator 1, 2, 4, 8, 16, 32, 64)", line);
    }
    return [num, den];
  }

  keyValue(text, line) {
    const m = /^([A-G][#b]?)(m?)$/.exec(text);
    if (m) {
      const table = m[2] ? KEY_MINOR : KEY_MAJOR;
      if (table.has(m[1])) return [table.get(m[1]), m[2] ? 1 : 0];
    }
    throw new LomaError("E013", "invalid key '" + text + "' (examples: C, Cm, F#m, Bb)", line);
  }

  cmdMeter(words, line) {
    this.once("meter", line);
    this.song.meter = this.meterValue(words.length === 2 ? words[1] : "", line, "usage: meter N/D, e.g. meter 4/4");
  }

  cmdKey(words, line) {
    this.once("key", line);
    if (words.length !== 2) {
      throw new LomaError("E013", "invalid key '" + (words.length > 1 ? words[1] : "") + "' (examples: C, Cm, F#m, Bb)", line);
    }
    this.song.key = this.keyValue(words[1], line);
  }

  cmdTrack(words, line) {
    try {
      this.declareTrack(words, line);
    } catch (e) {
      if (e instanceof LomaError) {
        const name = words.length > 1 ? words[1] : "";
        if (this.song.tracks.every((t) => t.name !== name)) this.badTracks.add(name);
      }
      throw e;
    }
  }

  declareTrack(words, line) {
    const name = this.newName(words.length > 1 ? words[1] : "", "track", (n) => this.song.tracks.some((t) => t.name === n), line);
    const rest = words.slice(2);
    const drums = rest.includes("drums");
    const raw = this.options(rest.filter((w) => w !== "drums"), ["ch", "program"], line, "track");
    const opts = new Map();
    for (const [k, v] of raw) {
      if (!INT_FULL.test(v)) throw new LomaError("E001", "track option " + k + " needs an integer, got '" + v + "'", line);
      opts.set(k, toInt(v, line));
    }
    let ch, program, kind;
    if (drums) {
      if (opts.size > 0) throw new LomaError("E001", "a drums track takes no ch/program options", line);
      if (this.song.tracks.some((t) => t.kind === "drums")) {
        throw new LomaError("E011", "only one drums track is allowed (channel 10 is exclusive)", line);
      }
      ch = 10;
      program = 0;
      kind = "drums";
    } else {
      if (!opts.has("ch")) throw new LomaError("E001", "melodic track needs ch=N (1-16)", line);
      ch = opts.get("ch");
      program = opts.has("program") ? opts.get("program") : 0;
      kind = "melodic";
      if (ch < 1 || ch > 16) throw new LomaError("E001", "ch must be 1-16, got " + ch, line);
      if (program < 0 || program > 127) throw new LomaError("E001", "program must be 0-127, got " + program, line);
      if (ch === 10) throw new LomaError("E011", "channel 10 is reserved for drums", line);
      for (const t of this.song.tracks) {
        if (t.kind === "melodic" && t.ch === ch) {
          throw new LomaError("E011", "channel " + ch + " is already used by track " + t.name, line);
        }
      }
    }
    this.song.tracks.push({ name: name, kind: kind, ch: ch, program: program, index: this.song.tracks.length, line: line });
  }

  cmdSection(words, line) {
    this.section = { name: words.length > 1 ? words[1] : "", body: [], line: line };
    this.stack = [this.section.body];
    this.repeats = [];
    this.bar = null;
    this.tl = null;
    this.skipBar = false;
    this.barCount = 0;
    this.curMeter = null;               // every section starts in the meter and key of the header
    this.curKey = null;
    this.meterLost = false;
    if (words.length !== 2) throw new LomaError("E001", "usage: section NAME", line);
    const name = this.newName(words[1], "section", (n) => this.song.sections.has(n), line);
    this.song.sections.set(name, this.section);
  }

  cmdPlay(words, line) {
    if (words.length < 2 || !NAME_FULL.test(words[1])) throw new LomaError("E001", "usage: play NAME [xN] [transpose=S]", line);
    let times = 1, transpose = 0;
    for (const w of words.slice(2)) {
      if (/^x[0-9]+$/.test(w)) {
        times = toInt(w.slice(1), line);
        if (times < 1 || times > MAX_REPEAT) {
          throw new LomaError("E018", "repetitions must be 1-" + MAX_REPEAT + ", got " + times, line);
        }
      } else if (/^transpose=[+-]?[0-9]+$/.test(w)) {
        transpose = toInt(w.split("=")[1], line);
      } else {
        throw new LomaError("E001", "invalid play option '" + w + "' (allowed: xN, transpose=S)", line);
      }
    }
    this.song.plays.push({ name: words[1], times: times, transpose: transpose, line: line });
  }

  cmdAt(code, line) {
    const usage = "usage: at TICK TRACK PITCH d=TICKS [v=VEL] | at TICK TRACK ccN=V | at TICK TRACK bend=V | at TICK TRACK \"text\" | at TICK tempo=BPM | at TICK meter=N/D | at TICK key=K";
    const m = /^at[ \t]+([0-9]+)[ \t]+([^]+)$/.exec(code);
    if (!m) throw new LomaError("E001", usage, line);
    const tick = toInt(m[1], line);
    if (tick > MAX_TICK) throw new LomaError("E018", "tick " + tick + " exceeds the maximum " + MAX_TICK, line);
    const rest = m[2];
    if (rest.startsWith("tempo=")) {
      this.need("1.0", "'at TICK tempo=BPM'", line);
      const v = rest.slice(6);
      if (!INT_FULL.test(v)) throw new LomaError("E001", usage, line);
      const bpm = toInt(v, line);
      if (bpm < 4 || bpm > 400) throw new LomaError("E015", "tempo " + bpm + " is outside the range 4-400 BPM", line);
      this.song.ats.push({ kind: "tempo", tick: tick, line: line, value: bpm });
      return;
    }
    if (rest.startsWith("meter=")) {
      this.need("1.1", "'at TICK meter=N/D'", line);
      this.song.ats.push({ kind: "meter", tick: tick, line: line, value: this.meterValue(rest.slice(6), line, usage) });
      return;
    }
    if (rest.startsWith("key=")) {
      this.need("1.1", "'at TICK key=K'", line);
      this.song.ats.push({ kind: "key", tick: tick, line: line, value: this.keyValue(rest.slice(4), line) });
      return;
    }
    const tm = /^([^ \t]+)(?:[ \t]+([^]*))?$/.exec(rest);
    const tail = tm[2] || "";
    const track = this.trackByName(tm[1], line);
    if (tail === "") throw new LomaError("E001", usage, line);
    if (tail.startsWith('"')) {
      this.need("1.0", "lyrics", line);
      const lm = /^"([^"]+)"$/.exec(tail);
      if (!lm) throw new LomaError("E001", "lyric must be a non-empty quoted string without inner quotes", line);
      this.song.ats.push({ kind: "lyric", tick: tick, line: line, track: track, text: lm[1] });
      return;
    }
    const sc = new Scanner(this, tail, line);
    const ctl = this.control(sc);
    if (ctl !== null) {
      const [kind, num, a, b] = ctl;
      this.need("1.0", "'at' with " + kind, line);
      if (b !== null || !sc.eof()) throw new LomaError("E001", usage, line);
      this.song.ats.push({ kind: kind, tick: tick, line: line, track: track, num: num, value: a });
      return;
    }
    const words = splitWords(tail);
    const value = this.pitch(words[0], track, line);
    const raw = this.options(words.slice(1), ["d", "v"], line, "'at'");
    const opts = new Map();
    for (const [k, v] of raw) {
      if (!INT_FULL.test(v)) throw new LomaError("E001", "'at' option " + k + " needs a non-negative integer, got '" + v + "'", line);
      opts.set(k, toInt(v, line));
    }
    if ((opts.has("d") ? opts.get("d") : 0) < 1) throw new LomaError("E001", "at: d=TICKS (at least 1) is required", line);
    const v = opts.has("v") ? opts.get("v") : DEFAULT_VEL;
    if (v < 1 || v > 127) throw new LomaError("E001", "velocity must be 1-127, got " + v, line);
    this.song.ats.push({ kind: "note", tick: tick, line: line, track: track, pitch: value, d: opts.get("d"), v: v });
  }

  // ---- inside a section
  closeBar() {
    if (this.bar !== null) {
      for (const tl of this.bar.trackLines) {
        if (!tl.failed && tl.parts.every((p) => p.use === null && p.items.length === 0)) {
          tl.failed = true;
          this.errors.push(new LomaError("E001", "empty track line", tl.line));
        }
      }
    }
    this.bar = null;
    this.tl = null;
    this.afterTl = false;
  }

  closeSection() {
    this.closeBar();
    this.section = null;
    this.stack = [];
    this.repeats = [];
    this.skipBar = false;
  }

  cmdBar(words, line) {
    this.closeBar();
    this.skipBar = true;
    this.barCount++;
    const chords = [];
    let options;
    try {
      options = this.barOptions(words, line, chords);
    } catch (e) {
      // the bars that follow have an unknown length
      if (e instanceof LomaError && words.slice(1).some((w) => w.startsWith("meter="))) this.meterLost = true;
      throw e;
    }
    if (chords.length === 0) throw new LomaError("E001", "'bar' needs at least one chord, e.g. 'bar Cm'", line);
    if (options.meter !== null) this.curMeter = options.meter;
    if (options.key !== null) this.curKey = options.key;
    this.bar = { isBar: true, chords: chords, lenTicks: options.lenTicks, tempo: options.tempo, trackLines: [], line: line,
      number: this.barCount, meter: this.curMeter, key: this.curKey, uncertain: this.meterLost };
    this.stack[this.stack.length - 1].push(this.bar);
    this.skipBar = false;
  }

  barOptions(words, line, chords) {
    let lenTicks = null, tempo = null, meter = null, key = null;
    for (const w of words.slice(1)) {
      if (w.includes("=")) {
        const [k, , v] = partition(w, "=");
        if (k === "len") {
          lenTicks = this.durOption(v, line, "len");
        } else if (k === "tempo") {
          const m = /^([0-9]+)(?:>([0-9]+))?$/.exec(v);
          if (!m) throw new LomaError("E001", "tempo option must be tempo=N or tempo=N>M", line);
          const lo = toInt(m[1], line);
          const hi = m[2] ? toInt(m[2], line) : null;
          for (const x of [lo, hi]) {
            if (x !== null && (x < 4 || x > 400)) throw new LomaError("E015", "tempo " + x + " is outside the range 4-400 BPM", line);
          }
          tempo = [lo, hi];
        } else if (k === "meter") {
          this.need("1.1", "bar option 'meter='", line);
          meter = this.meterValue(v, line, "meter option must be meter=N/D, e.g. meter=3/4");
        } else if (k === "key") {
          this.need("1.1", "bar option 'key='", line);
          key = this.keyValue(v, line);
        } else {
          throw new LomaError("E001", "unknown bar option '" + k + "' (allowed: len=/D tempo=N tempo=N>M meter=N/D key=K)", line);
        }
      } else {
        chords.push(this.chord(w, line));
      }
    }
    return { lenTicks: lenTicks, tempo: tempo, meter: meter, key: key };
  }

  cmdRepeat(words, line) {
    this.closeBar();
    let times = 1;
    const ok = words.length === 2 && INT_FULL.test(words[1]);
    if (ok) times = toInt(words[1], line);
    const node = { isBar: false, times: times, body: [], line: line };
    this.stack[this.stack.length - 1].push(node);
    this.stack.push(node.body);
    this.repeats.push(line);
    this.need("0.2", "'repeat' block", line);
    if (this.repeats.length > MAX_DEPTH) throw new LomaError("E018", "'repeat' blocks nested deeper than " + MAX_DEPTH, line);
    if (!ok) throw new LomaError("E001", "usage: repeat N", line);
    if (times < 1 || times > MAX_REPEAT) {
      node.times = 1;
      throw new LomaError("E018", "repetitions must be 1-" + MAX_REPEAT + ", got " + times, line);
    }
  }

  addContent(tl, text, line) {
    try {
      this.addChunks(tl, text, line);
    } catch (e) {
      if (e instanceof LomaError || e instanceof Skip) tl.failed = true;
      throw e;
    }
  }

  addChunks(tl, text, line) {
    const chunks = splitSegments(text);
    if (chunks.length > 1) this.need("0.2", "segments separated by '|'", line);
    chunks.forEach((chunk, n) => {
      if (n > 0) tl.parts.push({ use: null, items: [] });
      const part = tl.parts[tl.parts.length - 1];
      const words = splitWords(chunk);
      if (words.length === 0) return;
      if (words[0] === "use") {
        if (part.use !== null || part.items.length > 0 || words.length !== 2) {
          throw new LomaError("E016", "'use PATTERN' cannot be mixed with explicit notes in the same segment", line);
        }
        if (tl.track.kind === "drums") throw new LomaError("E001", "patterns cannot be used on drum tracks", line);
        const names = words[1].split(",");
        if (names.length > 1) this.need("0.2", "pattern list 'use A,B'", line);
        for (const nm of names) {
          if (!NAME_FULL.test(nm)) throw new LomaError("E001", "invalid pattern name '" + nm + "'", line);
        }
        part.use = names;
      } else {
        if (part.use !== null) {
          throw new LomaError("E016", "'use PATTERN' cannot be mixed with explicit notes in the same segment", line);
        }
        for (const it of this.parseContent(chunk, tl.track, line)) part.items.push(it);
      }
    });
  }

  trackLine(m, line) {
    this.tl = null;
    this.afterTl = true;
    if (this.bar === null) {
      if (this.skipBar) return;
      throw new LomaError("E001", "track line before any 'bar'", line);
    }
    const track = this.trackByName(m[1], line);
    const voice = this.bar.trackLines.filter((tl) => tl.track === track).length;
    if (voice > 0 && this.version < VERSIONS.get("1.1")) {
      throw new LomaError("E001", "track " + m[1] + " already has a line in this bar (several voices on one track need 'loma 1.1')", line);
    }
    const attrs = m[2] ? this.parseAttrs(m[2].slice(1, -1), line, true) : {};
    const tl = { track: track, attrs: attrs, parts: [{ use: null, items: [] }], line: line, failed: false, voice: voice };
    this.bar.trackLines.push(tl);
    this.tl = tl;
    this.addContent(tl, m[3], line);
  }

  continuation(code, line) {
    if (this.tl === null) {
      if (this.skipBar || this.afterTl) return;
      throw this.unknownCommand(splitWords(code)[0], line);
    }
    try {
      this.need("0.2", "track content on more than one line", line);
    } catch (e) {
      this.tl.failed = true;
      throw e;
    }
    this.addContent(this.tl, code, line);
  }

  sectionLine(code, words, line) {
    const first = words[0];
    if (first === "end" && words.length === 1) {
      this.closeBar();
      if (this.stack.length > 1) {
        this.stack.pop();
        this.repeats.pop();
      } else {
        this.closeSection();
      }
    } else if (first === "bar") {
      this.cmdBar(words, line);
    } else if (first === "repeat") {
      this.cmdRepeat(words, line);
    } else {
      const m = TRACK_LINE.exec(code);
      if (m) this.trackLine(m, line);
      else this.continuation(code, line);
    }
  }

  topLine(code, words, line) {
    const first = words[0];
    if (first === "title") this.cmdTitle(code, line);
    else if (first === "tempo") this.cmdTempo(words, line);
    else if (first === "meter") this.cmdMeter(words, line);
    else if (first === "key") this.cmdKey(words, line);
    else if (first === "track") this.cmdTrack(words, line);
    else if (first === "pattern") this.cmdPattern(code, line);
    else if (first === "swing") this.cmdSwing(code, line);
    else if (first === "voicing") this.cmdVoicing(code, line);
    else if (first === "section") this.cmdSection(words, line);
    else if (first === "play") this.cmdPlay(words, line);
    else if (first === "at") this.cmdAt(code, line);
    else if (first === "end") throw new LomaError("E001", "'end' without a matching 'section' or 'repeat'", line);
    else if (first === "bar" || first === "repeat" || TRACK_LINE.test(code)) {
      throw new LomaError("E001", "'" + first + "' outside a section", line);
    } else throw this.unknownCommand(first, line);
  }

  unknownCommand(word, line) {
    const name = word.split("{")[0];
    if (this.song.tracks.some((t) => t.name === name)) {
      return new LomaError("E002", "unknown command '" + word + "' (a track line needs ':' after the track name and its attributes)", line);
    }
    const [text, extra] = hint(word, COMMANDS);
    return new LomaError("E002", "unknown command '" + word + "'." + text, line, extra);
  }

  // A top-level statement; a failed definition is remembered, so that its uses are not reported too.
  top(code, words, line) {
    try {
      this.topLine(code, words, line);
    } catch (e) {
      if (e instanceof LomaError || e instanceof Skip) {
        const first = words[0];
        const m = words.length > 1 ? NAME_PREFIX.exec(words[1]) : null;
        if (["pattern", "swing", "voicing", "section"].includes(first) && m) this.song.failed[first].add(m[0]);
        if (first === "section" && this.section !== null) this.song.orphans.push(this.section);
        if (first === "meter") this.meterFailed = true;
      }
      throw e;
    }
  }

  run(text) {
    const lines = text.split("\n");
    for (let n = 0; n < lines.length; n++) {
      const ln = n + 1;
      const code = trim(stripComment(lines[n].replace(/\r+$/, "")));
      if (code === "") continue;
      const words = splitWords(code);
      try {
        if (this.version === null) {
          this.header(words, ln);
        } else if (this.section !== null && TOP_KEYWORDS.has(words[0])) {
          const name = this.section.name;
          this.closeSection();
          try {
            this.top(code, words, ln);
          } catch (e) {
            if (!(e instanceof LomaError || e instanceof Skip)) throw e;
          }
          throw new LomaError("E001", "'" + words[0] + "' is not allowed inside section '" + name + "' (missing 'end'?)", ln);
        } else if (this.section !== null) {
          this.sectionLine(code, words, ln);
        } else {
          this.top(code, words, ln);
        }
      } catch (e) {
        if (e instanceof Skip) continue;
        if (!(e instanceof LomaError)) throw e;
        if (e.line === null) e.line = ln;
        this.errors.push(e);
        if (this.version === null) break;
      }
    }
    if (this.version === null && this.errors.length === 0) {
      this.errors.push(new LomaError("E001", "empty file: it must start with 'loma VERSION'", 1));
    }
    if (this.section !== null) {
      if (this.repeats.length > 0) {
        this.errors.push(new LomaError("E001", "'repeat' is missing its 'end'", this.repeats[this.repeats.length - 1]));
      } else {
        this.errors.push(new LomaError("E001", "section '" + this.section.name + "' is missing its 'end'", this.section.line));
      }
      this.closeSection();
    }
    return this.song;
  }
}

// Text -> { song, errors, checkable }. With syntax errors the song holds what could be read;
// 'checkable' says whether its bars can still be validated (SPEC 13.1).
function parsePartial(text) {
  if (text.startsWith("\ufeff")) text = text.slice(1);
  const p = new Parser();
  const song = p.run(text);
  return { song: song, errors: p.errors, checkable: p.version !== null && !p.meterFailed };
}

function parse(text) {
  const r = parsePartial(text);
  if (r.errors.length > 0) throw new LomaErrors(r.errors);
  return r.song;
}

// ---------------------------------------------------------------------------- expansion

class Budget {
  constructor() {
    this.notes = 0;
    this.controls = 0;
    this.elements = 0;
  }

  element(line) {
    this.elements++;
    if (this.elements > MAX_ELEMENTS) {
      throw new LomaErrors([new LomaError("E018", "more than " + MAX_ELEMENTS + " expanded elements", line)]);
    }
  }

  add(notes, controls, line) {
    this.notes += notes;
    this.controls += controls;
    if (this.notes > MAX_NOTES) throw new LomaErrors([new LomaError("E018", "more than " + MAX_NOTES + " notes", line)]);
    if (this.controls > MAX_CONTROLS) {
      throw new LomaErrors([new LomaError("E018", "more than " + MAX_CONTROLS + " control events", line)]);
    }
  }
}

function checkPitch(pitch, line, ctx) {
  if (pitch < 0 || pitch > 127) throw new LomaError("E006", "pitch " + pitch + " is outside the MIDI range 0-127", line, ctx);
  return pitch;
}

function transposed(pitch, transpose, drums, line, ctx) {
  if (drums || transpose === 0) return pitch;
  const p = pitch + transpose;
  if (p < 0 || p > 127) {
    throw new LomaError("E006", "transposition by " + (transpose < 0 ? "" : "+") + transpose + " moves pitch " + pitch + " outside the MIDI range 0-127 (result " + p + ")", line, ctx);
  }
  return p;
}

function tonePitch(tone, chord, base, line, ctx) {
  const [idx, shift] = tone;
  if (idx === BASS_TONE) return checkPitch(12 * base + chord.bassPc + shift, line, ctx);
  if (idx >= chord.intervals.length) {
    throw new LomaError("E010", "tone " + (2 * idx + 1) + " does not exist in chord " + chord.name + " (it has " + chord.intervals.length + " notes)", line, ctx);
  }
  return checkPitch(12 * (base + 1) + chord.rootPc + chord.intervals[idx] + shift, line, ctx);
}

function ramp(a, b, start, length) {
  const out = [];
  for (let k = 0; k * RAMP_STEP < length; k++) {
    out.push([start + k * RAMP_STEP, a + floorDiv((b - a) * (k * RAMP_STEP), length)]);
  }
  out.push([start + length, b]);
  return out;
}

function undefinedName(song, kind, names, name, line, ctx) {
  if (song.failed[kind].has(name)) return new Quiet();
  const [text, extra] = hint(name, names);
  return new LomaError("E004", kind + " '" + name + "' is not defined." + text, line, Object.assign({}, ctx, extra));
}

class BarExpander {
  constructor(song, budget) {
    this.song = song;
    this.budget = budget;
  }

  lineDefaults(tl, p, barLen, tctx) {
    const m = { v: DEFAULT_VEL, o: 0, a: "norm" };
    for (const k of ["o", "d", "a"]) if (k in tl.attrs) m[k] = tl.attrs[k];
    const v = tl.attrs.v;
    if (Array.isArray(v)) m.v = v[0] + floorDiv((v[1] - v[0]) * p, barLen);
    else if (v !== undefined) m.v = v;
    let swing = 0;
    if (tl.attrs.swing !== undefined) {
      const sw = this.song.swings.get(tl.attrs.swing);
      if (sw === undefined) throw undefinedName(this.song, "swing", this.song.swings.keys(), tl.attrs.swing, tl.line, tctx);
      if (p % sw.grid === 0) swing = sw.table[(p / sw.grid) % sw.table.length];
    }
    return [m, swing];
  }

  notes(tl, p, barLen, tctx, pitches, itemAttrs, noteAttrs) {
    const [base, swing] = this.lineDefaults(tl, p, barLen, tctx);
    return pitches.map((pitch, i) => {
      const m = Object.assign({}, base, itemAttrs, noteAttrs[i]);
      m.o += swing;
      return [pitch, m];
    });
  }

  controls(it, tick) {
    if (it.kind === "lyric") {
      this.budget.add(0, 1, it.line);
      return [[tick, "lyric", { text: it.text }]];
    }
    this.budget.add(0, it.b === null ? 1 : floorDiv(it.dur + RAMP_STEP - 1, RAMP_STEP) + 1, it.line);
    const pairs = it.b === null ? [[tick, it.a]] : ramp(it.a, it.b, tick, it.dur);
    if (it.kind === "cc") return pairs.map(([t, v]) => [t, "cc", { controller: it.num, value: v }]);
    return pairs.map(([t, v]) => [t, "bend", { value: v }]);
  }

  fillPattern(tl, part, chord, start, origin, length, barLen, playIdx, transpose, tctx, out, single) {
    const pats = [];
    for (const name of part.use) {
      const pat = this.song.patterns.get(name);
      if (pat === undefined) throw undefinedName(this.song, "pattern", this.song.patterns.keys(), name, tl.line, tctx);
      pats.push(pat);
    }
    const total = pats.reduce((s, x) => s + x.length, 0);
    let pos = 0, i = 0;
    while (pos < length) {
      const pat = pats[i % pats.length];
      i++;
      if (pos + pat.length > length) {
        throw new LomaError("E009", "pattern " + part.use.join(",") + " (" + total + " ticks) does not fill the " + length + "-tick " +
          (single ? "bar" : "chord segment") + " exactly", tl.line, Object.assign({}, tctx, { expected: length, got: total }));
      }
      for (const step of pat.steps) {
        this.budget.element(tl.line);
        if (step.kind === "tones") {
          this.budget.add(step.tones.length, 0, tl.line);
          const pitches = step.tones.map((t) => transposed(tonePitch(t, chord, pat.base, tl.line, tctx), transpose, false, tl.line, tctx));
          const p = origin + pos;
          const notes = this.notes(tl, p, barLen, tctx, pitches, step.attrs, pitches.map(() => ({})));
          out.push({ kind: "note", pos: start + p, line: tl.line, ctx: tctx, playIdx: playIdx, dur: step.dur, notes: notes, tie: false, explicit: false });
        }
        pos += step.dur;
      }
    }
  }

  fillExplicit(tl, part, bar, seg, start, origin, length, barLen, playIdx, transpose, tctx, out, single) {
    const drums = tl.track.kind === "drums";
    let cursor = 0;
    for (const it of part.items) {
      this.budget.element(it.line);
      const p = origin + cursor;
      if (it.kind === "cc" || it.kind === "bend" || it.kind === "lyric") {
        const ctl = this.controls(it, start + p);
        out.push({ kind: "ctl", pos: start + p, line: it.line, ctx: tctx, playIdx: playIdx, controls: ctl });
        continue;
      }
      if (it.kind === "rest") {
        cursor += it.dur;
        continue;
      }
      let pitches, noteAttrs;
      if (it.kind === "voiced") {
        const voicing = this.song.voicings.get(it.name);
        if (voicing === undefined) throw undefinedName(this.song, "voicing", this.song.voicings.keys(), it.name, it.line, tctx);
        const chord = bar.chords[Math.min(Math.floor(p / seg), bar.chords.length - 1)];
        pitches = voicing.tones.map((t) => tonePitch(t, chord, voicing.base, it.line, tctx));
        noteAttrs = pitches.map(() => ({}));
      } else {
        pitches = it.notes.map((n) => n[0]);
        noteAttrs = it.notes.map((n) => n[1]);
      }
      this.budget.add(pitches.length, 0, it.line);
      pitches = pitches.map((x) => transposed(x, transpose, drums, it.line, tctx));
      const notes = this.notes(tl, p, barLen, tctx, pitches, it.attrs || {}, noteAttrs);
      out.push({ kind: "note", pos: start + p, line: it.line, ctx: tctx, playIdx: playIdx, dur: it.dur, notes: notes, tie: it.tie, explicit: isExplicit(it) });
      cursor += it.dur;
    }
    if (cursor !== length) {
      const where = single ? "bar" : "segment";
      const extra = { expected: length, got: cursor };
      let msg;
      if (cursor < length) {
        const miss = length - cursor;
        const name = durationName(miss);
        msg = where + " length mismatch. Expected " + length + " ticks, got " + cursor + ". Missing " + miss + " ticks" + (name ? " (= " + name + ")" : "") + ".";
        extra.missing = miss;
        if (name) {
          extra.suggestion = "add_rest";
          extra.duration = name;
        }
      } else {
        msg = where + " length mismatch. Expected " + length + " ticks, got " + cursor + ". Exceeds by " + (cursor - length) + " ticks.";
        extra.excess = cursor - length;
      }
      const line = part.items.length > 0 ? part.items[part.items.length - 1].line : tl.line;
      throw new LomaError("E003", msg, line, Object.assign({}, tctx, extra));
    }
  }

  expand(sec, bar, start, playIdx, transpose, barLen) {
    const ctx = { section: sec.name, bar: bar.number, chord: bar.chords.map((c) => c.name).join(" ") };
    const n = bar.chords.length;
    if (barLen % n !== 0) {
      throw new LomaError("E014", "bar of " + barLen + " ticks cannot be split into " + n + " equal parts", bar.line, ctx);
    }
    const seg = barLen / n;
    const result = [];
    for (const tl of bar.trackLines) {
      if (tl.failed) continue;              // only in a file with syntax errors
      const tctx = Object.assign({}, ctx, { track: tl.track.name });
      const single = tl.parts.length === 1;
      if (!single && tl.parts.length !== n) {
        throw new LomaError("E021", "track line has " + tl.parts.length + " segments but the bar has " + n + " chord(s)", tl.line,
          Object.assign({}, tctx, { expected: n, got: tl.parts.length }));
      }
      const out = [];
      try {
        tl.parts.forEach((part, k) => {
          if (part.use !== null) {
            const segments = single ? bar.chords.map((_, kk) => kk) : [k];
            for (const kk of segments) {
              this.fillPattern(tl, part, bar.chords[kk], start, kk * seg, seg, barLen, playIdx, transpose, tctx, out, n === 1);
            }
          } else if (single) {
            this.fillExplicit(tl, part, bar, seg, start, 0, barLen, barLen, playIdx, transpose, tctx, out, true);
          } else {
            this.fillExplicit(tl, part, bar, seg, start, k * seg, seg, barLen, playIdx, transpose, tctx, out, false);
          }
        });
      } catch (e) {
        if (e instanceof Quiet) continue;
        throw e;
      }
      result.push([tl.track.index, tl.voice, out]);
    }
    return result;
  }
}

function countBars(body) {
  let total = 0;
  for (const node of body) {
    total += node.isBar ? 1 : node.times * countBars(node.body);
    if (total > MAX_BARS) return total;
  }
  return total;
}

function flatten(body, out) {
  for (const node of body) {
    if (node.isBar) out.push(node);
    else for (let i = 0; i < node.times; i++) flatten(node.body, out);
  }
}

function allBars(body, out) {
  for (const node of body) {
    if (node.isBar) out.push(node);
    else allBars(node.body, out);
  }
}

function buildTempoMap(song, timeline) {
  const tmap = new Map([[0, song.tempo]]);
  for (const [, bar, start, , , length] of timeline) {
    if (bar.tempo === null) continue;
    const [n, m] = bar.tempo;
    if (m === null) {
      tmap.set(start, n);
    } else {
      for (let k = 0; k * PPQ < length; k++) tmap.set(start + k * PPQ, n + floorDiv((m - n) * (k * PPQ), length));
      tmap.set(start + length, m);
    }
  }
  for (const at of song.ats) if (at.kind === "tempo") tmap.set(at.tick, at.value);
  return tmap;
}

// Ticks of a bar: its 'len=', or else the meter in effect (its own or the one of the header).
function barLength(song, bar) {
  if (bar.lenTicks) return bar.lenTicks;
  const [num, den] = bar.meter || song.meter;
  return num * (WHOLE / den);
}

// [Map tick -> [num, den], Map tick -> [sf, mi]]: one time signature and one key signature per tick,
// the last one wins. A bar writes a signature when the one in effect differs from that of the bar
// played before it.
function buildSignatureMaps(song, timeline) {
  const meters = new Map([[0, song.meter]]), keys = new Map([[0, song.key]]);
  let meter = song.meter, key = song.key;
  for (const [, bar, start] of timeline) {
    const m = bar.meter || song.meter, k = bar.key || song.key;
    if (m[0] !== meter[0] || m[1] !== meter[1]) {
      meters.set(start, m);
      meter = m;
    }
    if (k !== null && (key === null || k[0] !== key[0] || k[1] !== key[1])) {
      keys.set(start, k);
      key = k;
    }
  }
  for (const at of song.ats) {
    if (at.kind === "meter") meters.set(at.tick, at.value);
    else if (at.kind === "key") keys.set(at.tick, at.value);
  }
  return [meters, keys];
}

function samePitches(a, b) {
  const x = a.map((n) => n[0]).sort((p, q) => p - q);
  const y = b.map((n) => n[0]).sort((p, q) => p - q);
  return x.length === y.length && x.every((v, i) => v === y[i]);
}

function resolveTies(track, items, errors) {
  const n = items.length;
  const cont = new Array(n).fill(null);
  const total = items.map((it) => it.dur || 0);
  for (let i = 0; i < n; i++) {
    const it = items[i];
    if (it.kind !== "note" || !it.tie) continue;
    let j = i + 1;
    while (j < n && items[j].kind !== "note") j++;
    let err = null;
    if (track.kind === "drums") {
      err = "ties are not allowed on drum tracks";
    } else if (j >= n) {
      err = "tie has no following note";
    } else {
      const nx = items[j];
      if (nx.pos !== it.pos + it.dur) err = "the tied note must start exactly where this one ends";
      else if (nx.playIdx !== it.playIdx) err = "a tie cannot cross into a different 'play' command";
      else if (!samePitches(nx.notes, it.notes)) err = "tied notes must have the same pitch (same pitches for chords)";
      else if (nx.explicit) err = "the tied note must not have its own attributes (v, o, d, a)";
    }
    if (err !== null) {
      errors.push(new LomaError("E012", "invalid tie: " + err, it.line, it.ctx));
      continue;
    }
    const head = cont[i] !== null ? cont[i] : i;
    cont[j] = head;
    total[head] += items[j].dur;
  }
  return [cont, total];
}

function eventKey(e) {
  return [e.tick, ORDER.get(e.kind), e.track, e.ch, e.pitch, e.seq];
}

function compareKeys(a, b) {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i];
  return 0;
}

// Bar checks of the semantic phase on a file that has syntax errors (SPEC 13.1). Every bar that
// could be read is validated once for each 'play' that uses it; the position in the song does
// not matter for these errors. Returns the list of errors.
function checkBars(song) {
  const errors = [];
  const expander = new BarExpander(song, new Budget());
  const todo = [];
  const played = new Set();
  song.plays.forEach((play, pi) => {
    const sec = song.sections.get(play.name);
    if (sec === undefined) {
      if (!song.failed.section.has(play.name)) {
        const [text, extra] = hint(play.name, song.sections.keys());
        errors.push(new LomaError("E004", "section '" + play.name + "' is not defined." + text, play.line, extra));
      }
      return;
    }
    played.add(play.name);
    todo.push([sec, pi, play.transpose]);
  });
  for (const sec of song.sections.values()) if (!played.has(sec.name)) todo.push([sec, -1, 0]);
  for (const sec of song.orphans) todo.push([sec, -1, 0]);
  try {
    for (const [sec, pi, transpose] of todo) {
      const flat = [];
      allBars(sec.body, flat);
      for (const bar of flat) {
        if (bar.uncertain) continue;        // its meter was set by a 'bar' line that is wrong
        try {
          expander.expand(sec, bar, 0, pi, transpose, barLength(song, bar));
        } catch (e) {
          if (!(e instanceof LomaError)) throw e;
          errors.push(e);
        }
      }
    }
  } catch (e) {
    if (e instanceof LomaErrors) return [];  // a limit was exceeded: only the syntax errors are reported
    throw e;
  }
  return errors;
}

function compileSong(song) {
  const errors = [];
  const budget = new Budget();
  const expander = new BarExpander(song, budget);

  const timeline = [];
  const played = new Set();
  let cursor = 0, bars = 0;
  song.plays.forEach((play, pi) => {
    const sec = song.sections.get(play.name);
    if (sec === undefined) {
      const [text, extra] = hint(play.name, song.sections.keys());
      errors.push(new LomaError("E004", "section '" + play.name + "' is not defined." + text, play.line, extra));
      return;
    }
    played.add(play.name);
    bars += play.times * countBars(sec.body);
    if (bars > MAX_BARS) throw new LomaErrors([new LomaError("E018", "the song expands to more than " + MAX_BARS + " bars", play.line)]);
    const flat = [];
    flatten(sec.body, flat);
    for (let r = 0; r < play.times; r++) {
      for (const bar of flat) {
        const length = barLength(song, bar);
        timeline.push([sec, bar, cursor, pi, play.transpose, length]);
        cursor += length;
        if (cursor > MAX_TICK) {
          throw new LomaErrors([new LomaError("E018", "the song is longer than the maximum of " + MAX_TICK + " ticks", play.line)]);
        }
      }
    }
  });
  const totalLen = cursor;

  const trackItems = song.tracks.map(() => new Map());    // for each track: voice number -> items
  for (const [sec, bar, start, pi, tr, length] of timeline) {
    try {
      for (const [ti, voice, items] of expander.expand(sec, bar, start, pi, tr, length)) {
        if (!trackItems[ti].has(voice)) trackItems[ti].set(voice, []);
        const list = trackItems[ti].get(voice);
        for (const it of items) list.push(it);
      }
    } catch (e) {
      if (!(e instanceof LomaError)) throw e;
      errors.push(e);
    }
  }
  for (const sec of song.sections.values()) {
    if (played.has(sec.name)) continue;
    const flat = [];
    allBars(sec.body, flat);
    for (const bar of flat) {
      try {
        expander.expand(sec, bar, 0, -1, 0, barLength(song, bar));
      } catch (e) {
        if (!(e instanceof LomaError)) throw e;
        errors.push(e);
      }
    }
  }

  const events = [];
  const tempoMap = buildTempoMap(song, timeline);
  for (const tick of Array.from(tempoMap.keys()).sort((a, b) => a - b)) {
    events.push({ tick: tick, kind: "tempo", track: -1, ch: 0, pitch: 0, seq: 0, data: { bpm: tempoMap.get(tick) } });
  }
  const [meterMap, keyMap] = buildSignatureMaps(song, timeline);
  for (const tick of Array.from(meterMap.keys()).sort((a, b) => a - b)) {
    if (tick > 0) events.push({ tick: tick, kind: "meter", track: -1, ch: 0, pitch: 0, seq: 0, data: { num: meterMap.get(tick)[0], den: meterMap.get(tick)[1] } });
  }
  for (const tick of Array.from(keyMap.keys()).sort((a, b) => a - b)) {
    if (tick > 0) events.push({ tick: tick, kind: "key", track: -1, ch: 0, pitch: 0, seq: 0, data: { sf: keyMap.get(tick)[0], mi: keyMap.get(tick)[1] } });
  }

  const resolved = [];
  const counters = song.tracks.map(() => 0);
  for (const track of song.tracks) {
    let c = 0;
    // voice by voice: ties stay inside a voice
    for (const voice of Array.from(trackItems[track.index].keys()).sort((a, b) => a - b)) {
      const items = trackItems[track.index].get(voice);
      const [cont, total] = resolveTies(track, items, errors);
      items.forEach((it, i) => {
        if (it.kind === "ctl") {
          for (const [tick, kind, data] of it.controls) {
            if (tick > MAX_TICK) {
              errors.push(new LomaError("E018", "event at tick " + tick + " exceeds the maximum " + MAX_TICK, it.line, it.ctx));
              break;
            }
            events.push({ tick: tick, kind: kind, track: track.index, ch: track.ch, pitch: 0, seq: c, data: data });
            c++;
          }
        } else if (cont[i] === null) {
          for (const [pitch, m] of it.notes) {
            const sounding = "d" in m ? m.d : Math.max(1, floorDiv(total[i] * GATE_PCT.get(m.a), 100));
            const start = Math.max(0, it.pos + m.o);
            resolved.push({ track: track, pitch: pitch, vel: m.v, start: start, end: start + sounding, on: c, off: c + 1, line: it.line, ctx: it.ctx });
            c += 2;
          }
        }
      });
    }
    counters[track.index] = c;
  }
  for (const at of song.ats) {
    if (at.kind === "tempo" || at.kind === "meter" || at.kind === "key") continue;
    const c = counters[at.track.index];
    const ctx = { track: at.track.name };
    if (at.kind === "note") {
      budget.add(1, 0, at.line);
      resolved.push({ track: at.track, pitch: at.pitch, vel: at.v, start: at.tick, end: at.tick + at.d, on: c, off: c + 1, line: at.line, ctx: ctx });
      counters[at.track.index] = c + 2;
      continue;
    }
    budget.add(0, 1, at.line);
    const data = at.kind === "cc" ? { controller: at.num, value: at.value } : at.kind === "bend" ? { value: at.value } : { text: at.text };
    events.push({ tick: at.tick, kind: at.kind, track: at.track.index, ch: at.track.ch, pitch: 0, seq: c, data: data });
    counters[at.track.index] = c + 1;
  }

  const groups = new Map();
  for (const n of resolved) {
    const key = n.track.ch * 128 + n.pitch;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(n);
  }
  for (const key of Array.from(groups.keys()).sort((a, b) => a - b)) {
    const lst = groups.get(key).slice().sort((a, b) => (a.start - b.start) || (a.on - b.on));
    for (let i = 0; i + 1 < lst.length; i++) {
      const a = lst[i], b = lst[i + 1];
      if (a.start === b.start) {
        errors.push(new LomaError("E017", "duplicate note: pitch " + b.pitch + " starts twice at tick " + b.start + " on channel " + b.track.ch, b.line, b.ctx));
      } else if (a.end > b.start) {
        a.end = b.start;
      }
    }
  }
  for (const n of resolved) {
    if (n.end > MAX_TICK) errors.push(new LomaError("E018", "event at tick " + n.end + " exceeds the maximum " + MAX_TICK, n.line, n.ctx));
  }
  if (errors.length > 0) throw new LomaErrors(errors);

  for (const n of resolved) {
    events.push({ tick: n.start, kind: "note_on", track: n.track.index, ch: n.track.ch, pitch: n.pitch, seq: n.on, data: { vel: n.vel } });
    events.push({ tick: n.end, kind: "note_off", track: n.track.index, ch: n.track.ch, pitch: n.pitch, seq: n.off, data: {} });
  }
  const keyed = events.map((e) => [eventKey(e), e]);
  keyed.sort((a, b) => compareKeys(a[0], b[0]));
  const sorted = keyed.map((x) => x[1]);
  let endTick = totalLen;
  for (const e of sorted) if (e.tick > endTick) endTick = e.tick;
  return { song: song, events: sorted, endTick: endTick, bars: timeline.map((x) => x[2]), meter: meterMap.get(0), key: keyMap.get(0) };
}

// ---------------------------------------------------------------------------- output

function eventObject(e, trackNames) {
  if (e.kind === "tempo") return { bpm: e.data.bpm, tick: e.tick, type: e.kind };
  if (e.kind === "meter") return { den: e.data.den, num: e.data.num, tick: e.tick, type: e.kind };
  if (e.kind === "key") return { mi: e.data.mi, sf: e.data.sf, tick: e.tick, type: e.kind };
  const track = trackNames[e.track];
  if (e.kind === "lyric") return { text: e.data.text, tick: e.tick, track: track, type: e.kind };
  if (e.kind === "note_on") return { ch: e.ch, pitch: e.pitch, tick: e.tick, track: track, type: e.kind, vel: e.data.vel };
  if (e.kind === "note_off") return { ch: e.ch, pitch: e.pitch, tick: e.tick, track: track, type: e.kind };
  if (e.kind === "cc") return { ch: e.ch, controller: e.data.controller, tick: e.tick, track: track, type: e.kind, value: e.data.value };
  return { ch: e.ch, tick: e.tick, track: track, type: e.kind, value: e.data.value };
}

function canonicalJson(compiled) {
  const names = compiled.song.tracks.map((t) => t.name);
  return "[" + compiled.events.map((e) => JSON.stringify(eventObject(e, names))).join(",") + "]\n";
}

function utf8(text) {
  return Array.from(new TextEncoder().encode(text));
}

function meta(kind, payload) {
  return [0xFF, kind].concat(vlq(payload.length), payload);
}

function u32(n) {
  return [(n >>> 24) & 0xFF, (n >>> 16) & 0xFF, (n >>> 8) & 0xFF, n & 0xFF];
}

function trackBytes(events, endTick) {
  const out = [];
  let prev = 0;
  for (const [tick, data] of events) {
    for (const b of vlq(tick - prev)) out.push(b);
    for (const b of data) out.push(b);
    prev = tick;
  }
  for (const b of vlq(endTick - prev)) out.push(b);
  out.push(0xFF, 0x2F, 0x00);
  return [0x4D, 0x54, 0x72, 0x6B].concat(u32(out.length), out);
}

function encode(e, status) {
  if (e.kind === "note_on") return [0x90 | status, e.pitch, e.data.vel];
  if (e.kind === "note_off") return [0x80 | status, e.pitch, 0x40];
  if (e.kind === "cc") return [0xB0 | status, e.data.controller, e.data.value];
  if (e.kind === "bend") {
    const value = e.data.value + 8192;
    return [0xE0 | status, value & 0x7F, value >> 7];
  }
  return meta(0x05, utf8(e.data.text));
}

function writeMidi(compiled) {
  const song = compiled.song;
  const end = compiled.endTick;
  const conductor = [];
  if (song.title !== null) conductor.push([0, meta(0x03, utf8(song.title))]);
  const timeSignature = (num, den) => meta(0x58, [num, VALID_DENOMINATORS.indexOf(den), 24, 8]);
  const keySignature = (sf, mi) => meta(0x59, [sf & 0xFF, mi]);
  conductor.push([0, timeSignature(compiled.meter[0], compiled.meter[1])]);
  if (compiled.key !== null) conductor.push([0, keySignature(compiled.key[0], compiled.key[1])]);
  for (const e of compiled.events) {
    if (e.kind === "tempo") {
      const us = floorDiv(60000000, e.data.bpm);
      conductor.push([e.tick, meta(0x51, [(us >> 16) & 0xFF, (us >> 8) & 0xFF, us & 0xFF])]);
    } else if (e.kind === "meter") {
      conductor.push([e.tick, timeSignature(e.data.num, e.data.den)]);
    } else if (e.kind === "key") {
      conductor.push([e.tick, keySignature(e.data.sf, e.data.mi)]);
    }
  }
  const perTrack = song.tracks.map(() => []);
  for (const e of compiled.events) if (e.track >= 0) perTrack[e.track].push(e);

  const chunks = [trackBytes(conductor, end)];
  for (const t of song.tracks) {
    const evs = [[0, meta(0x03, utf8(t.name))]];
    if (t.kind !== "drums") evs.push([0, [0xC0 | (t.ch - 1), t.program]]);
    for (const e of perTrack[t.index]) evs.push([e.tick, encode(e, t.ch - 1)]);
    chunks.push(trackBytes(evs, end));
  }
  const header = [0x4D, 0x54, 0x68, 0x64, 0, 0, 0, 6, 0, 1, (chunks.length >> 8) & 0xFF, chunks.length & 0xFF, (PPQ >> 8) & 0xFF, PPQ & 0xFF];
  const out = new Uint8Array(header.length + chunks.reduce((n, c) => n + c.length, 0));
  out.set(header, 0);
  let offset = header.length;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

function compileText(text) {
  const r = parsePartial(text);
  if (r.errors.length > 0) throw new LomaErrors(r.errors.concat(r.checkable ? checkBars(r.song) : []));
  const compiled = compileSong(r.song);
  return { compiled: compiled, midi: writeMidi(compiled) };
}


// ---------------------------------------------------------------------------- MIDI -> LOMA

class MidiError extends Error {}

function readVlq(data, i) {
  let n = 0;
  for (let k = 0; k < 4; k++) {
    if (i >= data.length) throw new MidiError("truncated variable-length quantity");
    const c = data[i++];
    n = n * 128 + (c & 0x7F);
    if (!(c & 0x80)) return [n, i];
  }
  throw new MidiError("variable-length quantity longer than 4 bytes");
}

function readTrack(body) {
  const events = [];
  let i = 0, tick = 0, status = null;
  while (i < body.length) {
    let delta;
    [delta, i] = readVlq(body, i);
    tick += delta;
    if (i >= body.length) throw new MidiError("truncated track");
    const first = body[i];
    if (first === 0xFF) {
      if (i + 1 >= body.length) throw new MidiError("truncated meta event");
      const kind = body[i + 1];
      const [length, j] = readVlq(body, i + 2);
      if (j + length > body.length) throw new MidiError("truncated meta event");
      events.push([tick, "meta", kind, body.slice(j, j + length)]);
      i = j + length;
      status = null;
    } else if (first === 0xF0 || first === 0xF7) {
      const [length, j] = readVlq(body, i + 1);
      if (j + length > body.length) throw new MidiError("truncated sysex event");
      events.push([tick, "sysex", first, body.slice(j, j + length)]);
      i = j + length;
      status = null;
    } else {
      if (first & 0x80) {
        status = first;
        i++;
      } else if (status === null) {
        throw new MidiError("data byte without a running status");
      }
      const hi = status & 0xF0;
      if (hi === 0xF0) throw new MidiError("unsupported system message 0x" + status.toString(16).toUpperCase().padStart(2, "0"));
      const size = hi === 0xC0 || hi === 0xD0 ? 1 : 2;
      if (i + size > body.length) throw new MidiError("truncated channel event");
      const data = Array.from(body.slice(i, i + size));
      if (data.some((b) => b & 0x80)) throw new MidiError("invalid data byte in channel event");
      events.push([tick, "midi", status, data]);
      i += size;
    }
  }
  return events;
}

function be(data, i, n) {
  let v = 0;
  for (let k = 0; k < n; k++) v = v * 256 + data[i + k];
  return v;
}

function readMidi(data) {
  const tag = (i) => String.fromCharCode(data[i], data[i + 1], data[i + 2], data[i + 3]);
  if (data.length < 14 || tag(0) !== "MThd" || be(data, 4, 4) < 6) throw new MidiError("not a Standard MIDI File");
  const hlen = be(data, 4, 4), fmt = be(data, 8, 2), ntracks = be(data, 10, 2), division = be(data, 12, 2);
  if (fmt !== 0 && fmt !== 1) throw new MidiError("unsupported MIDI format " + fmt + " (only 0 and 1)");
  if (division & 0x8000 || division === 0) throw new MidiError("SMPTE time division is not supported");
  let i = 8 + hlen;
  const tracks = [];
  while (i + 8 <= data.length && tracks.length < ntracks) {
    const name = tag(i), length = be(data, i + 4, 4);
    const body = data.slice(i + 8, i + 8 + length);
    if (body.length !== length) throw new MidiError("truncated chunk");
    i += 8 + length;
    if (name === "MTrk") tracks.push(readTrack(body));
  }
  if (tracks.length !== ntracks) throw new MidiError("expected " + ntracks + " tracks, found " + tracks.length);
  return { format: fmt, division: division, tracks: tracks };
}

function pitchName(pitch, drums) {
  if (drums) {
    for (const [name, value] of DRUMS) if (value === pitch) return name;
    return "m" + pitch;
  }
  return NOTE_NAMES[pitch % 12] + (Math.floor(pitch / 12) - 1);
}

function exactBpm(us) {
  const guess = Math.max(4, Math.min(400, floorDiv(60000000, Math.max(us, 1))));
  for (const bpm of [guess, guess + 1, guess - 1]) {
    if (bpm >= 4 && bpm <= 400 && floorDiv(60000000, bpm) === us) return [bpm, true];
  }
  return [guess, false];
}

function metaText(raw) {
  return new TextDecoder("utf-8").decode(Uint8Array.from(raw)).replace(/"/g, "'").replace(/[\n\r]/g, " ");
}

// MIDI bytes -> { source, warnings }. Every event becomes an 'at' statement at its exact tick,
// so a file produced by a LOMA compiler compiles back to the same bytes.
function decompile(data) {
  const midi = readMidi(data);
  const fmt = midi.format, division = midi.division;
  const warnings = [];
  const dropped = new Set();

  const scale = (tick) => {
    if ((tick * PPQ) % division !== 0) {
      throw new MidiError("tick " + tick + " cannot be converted exactly from " + division + " to " + PPQ + " ticks per quarter");
    }
    const t = (tick * PPQ) / division;
    if (t > MAX_TICK) throw new MidiError("the file is longer than the LOMA maximum of " + MAX_TICK + " ticks");
    return t;
  };

  let title = null, end = 0;
  const meters = new Map(), keys = new Map();     // tick -> last signature written at that tick
  const tempos = new Map(), channels = new Map(), names = new Map(), lyrics = new Map(), openNotes = new Map();
  const silent = [];

  midi.tracks.forEach((events, ti) => {
    let hasChannelEvent = false;
    events.forEach(([tick, kind, a, b], seq) => {
      const t = scale(tick);
      end = Math.max(end, t);
      if (kind === "sysex") {
        dropped.add("system exclusive messages");
      } else if (kind === "meta") {
        if (a === 0x03) {
          if (ti === 0 && fmt === 1) title = metaText(b);
          else names.set(ti, metaText(b));
        } else if (a === 0x58 && b.length >= 2) {
          meters.set(t, [b[0], Math.pow(2, b[1])]);
        } else if (a === 0x59 && b.length >= 2) {
          keys.set(t, [b[0] > 127 ? b[0] - 256 : b[0], b[1]]);
        } else if (a === 0x51 && b.length === 3) {
          tempos.set(t, be(b, 0, 3));
        } else if (a === 0x05) {
          const text = metaText(b);
          if (text !== "") {
            if (!lyrics.has(ti)) lyrics.set(ti, []);
            lyrics.get(ti).push([t, seq, text]);
          }
        } else if (a !== 0x2F) {
          dropped.add("meta event 0x" + a.toString(16).toUpperCase().padStart(2, "0"));
        }
      } else {
        hasChannelEvent = true;
        const ch = (a & 0x0F) + 1, hi = a & 0xF0;
        if (!channels.has(ch)) channels.set(ch, { ch: ch, track: ti, program: null, notes: [], others: [] });
        const info = channels.get(ch);
        const noteKey = ch * 128 + b[0];
        if (hi === 0x90 && b[1] > 0) {
          if (!openNotes.has(noteKey)) openNotes.set(noteKey, []);
          openNotes.get(noteKey).push([t, b[1], seq, ti]);
        } else if (hi === 0x80 || hi === 0x90) {
          const pending = openNotes.get(noteKey);
          if (pending && pending.length > 0) {
            const [start, vel, sq, tj] = pending.shift();
            if (t === start) warnings.push("zero-length note at tick " + start + " lengthened to 1 tick");
            info.notes.push([start, tj, sq, b[0], Math.max(1, t - start), vel]);
          }
        } else if (hi === 0xB0) {
          info.others.push([t, ti, seq, "cc" + b[0] + "=" + b[1]]);
        } else if (hi === 0xE0) {
          info.others.push([t, ti, seq, "bend=" + ((b[1] * 128 + b[0]) - 8192)]);
        } else if (hi === 0xC0) {
          if (info.program === null) info.program = b[0];
          else if (info.program !== b[0]) dropped.add("program changes after the first one");
        } else {
          dropped.add("aftertouch messages");
        }
      }
    });
    if (!hasChannelEvent && (ti > 0 || fmt === 0)) silent.push(ti);
  });
  for (const noteKey of Array.from(openNotes.keys()).sort((x, y) => x - y)) {
    const ch = Math.floor(noteKey / 128), pitch = noteKey % 128;
    for (const [start, vel, sq, tj] of openNotes.get(noteKey)) {
      warnings.push("note " + pitch + " on channel " + ch + " at tick " + start + " has no note-off: ended at the end of the file");
      channels.get(ch).notes.push([start, tj, sq, pitch, Math.max(1, end - start), vel]);
    }
  }

  const owners = new Map();
  for (const info of channels.values()) {
    if (!owners.has(info.track)) owners.set(info.track, []);
    owners.get(info.track).push(info.ch);
  }
  const decl = [];
  for (const info of channels.values()) {
    const wanted = owners.get(info.track).length === 1 && names.has(info.track) ? names.get(info.track) : null;
    decl.push([[info.track, info.ch], wanted, info.ch]);
  }
  let emptyDrums = null;              // MIDI track taken as a drums track without notes
  for (const ti of silent) {
    if (names.has(ti) && !channels.has(10) && emptyDrums === null) {
      decl.push([[ti, 0], names.get(ti), null]);
      emptyDrums = ti;
    } else if (names.has(ti)) {
      dropped.add("empty tracks");
    }
  }
  decl.sort((x, y) => (x[0][0] - y[0][0]) || (x[0][1] - y[0][1]));
  for (const ti of lyrics.keys()) {
    if ((owners.get(ti) || []).length !== 1 && ti !== emptyDrums) dropped.add("lyrics in tracks that do not own exactly one channel");
  }

  const validMeter = (m) => m[0] >= 1 && m[0] <= 64 && VALID_DENOMINATORS.includes(m[1]);
  const keyNameOf = (k) => {
    let found = null;
    for (const [name, sf] of k[1] === 0 ? KEY_MAJOR : k[1] === 1 ? KEY_MINOR : []) {
      if (sf === k[0]) found = name + (k[1] === 1 ? "m" : "");
    }
    return found;
  };
  let meter = meters.has(0) ? meters.get(0) : null;
  const key = keys.has(0) ? keys.get(0) : null;
  meters.delete(0);
  keys.delete(0);
  const byTick = (map) => Array.from(map.keys()).sort((x, y) => x - y);
  const meterAts = byTick(meters).filter((t) => validMeter(meters.get(t))).map((t) => [t, meters.get(t)]);
  const keyAts = byTick(keys).filter((t) => keyNameOf(keys.get(t)) !== null).map((t) => [t, keyNameOf(keys.get(t))]);
  if (meterAts.length < meters.size) dropped.add("unsupported time signatures");
  if (keyAts.length < keys.size) dropped.add("invalid key signature");
  const out = [meterAts.length > 0 || keyAts.length > 0 ? "loma 1.1" : "loma 1.0"];
  if (title !== null) out.push('title "' + title + '"');
  if (!tempos.has(0)) {
    warnings.push("no tempo at tick 0: 120 BPM assumed");
    out.push("tempo 120");
  } else {
    const firstUs = tempos.get(0);
    tempos.delete(0);
    const [bpm, exact] = exactBpm(firstUs);
    if (!exact) warnings.push("tempo " + firstUs + " us per quarter is not an integer BPM: " + bpm + " BPM used");
    out.push("tempo " + bpm);
  }
  if (meter === null) {
    meter = [4, 4];
  } else if (!validMeter(meter)) {
    warnings.push("time signature " + meter[0] + "/" + meter[1] + " is not supported: 4/4 used");
    meter = [4, 4];
  }
  out.push("meter " + meter[0] + "/" + meter[1]);
  if (key !== null) {
    const keyName = keyNameOf(key);
    if (keyName !== null) out.push("key " + keyName);
    else dropped.add("invalid key signature");
  }
  out.push("");

  const used = new Set(), trackNames = new Map();
  const unique = (wanted, fallback) => {
    let name = wanted && NAME_FULL.test(wanted) && !RESERVED.has(wanted) ? wanted : fallback;
    const base = name;
    for (let n = 2; used.has(name); n++) name = base + "_" + n;
    used.add(name);
    return name;
  };
  for (const [, wanted, ch] of decl) {
    if (ch === null || ch === 10) {
      trackNames.set(10, unique(wanted, "drumkit"));
      out.push("track " + trackNames.get(10) + " drums");
    } else {
      trackNames.set(ch, unique(wanted, "ch" + ch));
      out.push("track " + trackNames.get(ch) + " ch=" + ch + " program=" + (channels.get(ch).program || 0));
    }
  }
  out.push("", "section main");
  if (end > 0) out.push("  bar C len=/#" + end);
  out.push("end", "play main", "");

  for (const t of Array.from(tempos.keys()).sort((x, y) => x - y)) {
    const [bpm, exact] = exactBpm(tempos.get(t));
    if (!exact) warnings.push("tempo " + tempos.get(t) + " us per quarter at tick " + t + " is not an integer BPM: " + bpm + " BPM used");
    out.push("at " + t + " tempo=" + bpm);
  }
  for (const [t, m] of meterAts) out.push("at " + t + " meter=" + m[0] + "/" + m[1]);
  for (const [t, name] of keyAts) out.push("at " + t + " key=" + name);
  for (const [order, , ch] of decl) {
    if (ch === null) {                // the drums track without notes: it can still carry lyrics
      const words = (lyrics.get(order[0]) || []).slice().sort((x, y) => (x[0] - y[0]) || (x[1] - y[1]));
      for (const [t, , text] of words) out.push("at " + t + " " + trackNames.get(10) + ' "' + text + '"');
      continue;
    }
    const info = channels.get(ch), name = trackNames.get(ch);
    const lines = [], starts = new Set();
    for (const [start, ti, seq, pitch, dur, vel] of info.notes) {
      const startKey = pitch + ":" + start;
      if (starts.has(startKey)) {
        warnings.push("duplicate note " + pitch + " at tick " + start + " on channel " + ch + " dropped");
        continue;
      }
      starts.add(startKey);
      lines.push([start, ti, seq, "at " + start + " " + name + " " + pitchName(pitch, ch === 10) + " d=" + dur + " v=" + vel]);
    }
    for (const [t, ti, seq, text] of info.others) lines.push([t, ti, seq, "at " + t + " " + name + " " + text]);
    if (owners.get(info.track).length === 1) {
      for (const [t, seq, text] of lyrics.get(info.track) || []) lines.push([t, info.track, seq, "at " + t + " " + name + ' "' + text + '"']);
    }
    lines.sort((x, y) => (x[0] - y[0]) || (x[1] - y[1]) || (x[2] - y[2]));
    for (const line of lines) out.push(line[3]);
  }
  for (const what of Array.from(dropped).sort()) warnings.push("not representable in LOMA, dropped: " + what);
  return { source: out.join("\n") + "\n", warnings: warnings };
}

const api = { compileText, canonicalJson, parse, compileSong, writeMidi, readMidi, decompile, floorDiv,
  durationTicks, LomaError, LomaErrors, MidiError, PPQ };
if (typeof module === "object" && module && module.exports) module.exports = api;

// ---------------------------------------------------------------------------- command line (Node.js)

function main(argv) {
  const fs = require("fs");
  const crypto = require("crypto");
  const cmd = argv[0];
  const file = argv[1];
  const asJson = argv.includes("--json");
  const outIndex = argv.indexOf("-o");
  if (!["compile", "check", "expand", "hash", "decompile"].includes(cmd) || file === undefined || (cmd === "compile" && outIndex < 0)) {
    process.stderr.write("usage: loma.js compile FILE -o OUT [--json] | check FILE [--json] | expand FILE --json | hash FILE | decompile FILE.mid [-o OUT]\n");
    return 2;
  }
  try {
    const data = fs.readFileSync(file === "-" ? 0 : file);
    if (cmd === "decompile") {
      const result = decompile(new Uint8Array(data));
      for (const w of result.warnings) process.stderr.write("warning: " + w + "\n");
      if (outIndex >= 0) fs.writeFileSync(argv[outIndex + 1], result.source);
      else process.stdout.write(result.source);
      return 0;
    }
    let text;
    try {
      text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(data);
    } catch (e) {
      throw new LomaErrors([new LomaError("E001", "the file is not valid UTF-8", 1)]);
    }
    const { compiled, midi } = compileText(text);
    if (cmd === "check") process.stdout.write(asJson ? "[]\n" : "OK\n");
    else if (cmd === "compile") fs.writeFileSync(argv[outIndex + 1], midi);
    else if (cmd === "expand") process.stdout.write(canonicalJson(compiled));
    else process.stdout.write(crypto.createHash("sha256").update(midi).digest("hex") + "\n");
    return 0;
  } catch (e) {
    if (e instanceof LomaErrors) {
      if (asJson) {
        process.stdout.write(JSON.stringify(e.errors) + "\n");
      } else {
        for (const x of e.errors) process.stderr.write(x.code + " line " + x.line + ": " + x.message + "\n");
        process.stderr.write(e.errors.length + " error(s)\n");
      }
      return 1;
    }
    if (e instanceof MidiError || (e && typeof e.code === "string" && e.syscall)) {
      process.stderr.write("loma: " + e.message + "\n");
      return 2;
    }
    throw e;
  }
}

if (typeof require === "function" && typeof module === "object" && require.main === module) {
  process.exitCode = main(process.argv.slice(2));
}
