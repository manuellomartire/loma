# LOMA 1.0 — Language specification

Language version: **1.0**. File extension: `.loma`. Italian version: [SPEC.it.md](SPEC.it.md). If the two texts disagree, the conformance suite decides.

LOMA is a text language for describing music, designed to be written by an AI and compiled deterministically to a MIDI file: the same `.loma` file gives the same `.mid`, byte for byte, with any conforming compiler.

## Contents

1. [Principles](#1-principles)
2. [Conformance](#2-conformance)
3. [Arithmetic](#3-arithmetic)
4. [Text structure](#4-text-structure)
5. [Global statements](#5-global-statements)
6. [Pitches and durations](#6-pitches-and-durations)
7. [Content of a line](#7-content-of-a-line)
8. [Chords and tones](#8-chords-and-tones)
9. [Patterns, swing, voicings](#9-patterns-swing-voicings)
10. [Sections and bars](#10-sections-and-bars)
11. [Arrangement: `play` and `at`](#11-arrangement-play-and-at)
12. [Limits](#12-limits)
13. [Errors](#13-errors)
14. [Note resolution](#14-note-resolution)
15. [Events: order and canonical JSON](#15-events-order-and-canonical-json)
16. [Canonical MIDI](#16-canonical-midi)
17. [Command line and conformance suite](#17-command-line-and-conformance-suite)
18. [Language versions](#18-language-versions)
19. [Complete example](#19-complete-example)

The formal grammar is in [spec/grammar.ebnf](spec/grammar.ebnf).

---

## 1. Principles

1. **Deterministic.** No randomness, no floating point, nothing that depends on date, system or compiler version.
2. **Written, not computed.** Expression (early and late notes, dynamics) is written in the file. The compiler invents nothing: it applies integer rules.
3. **Declarative and limited.** Few commands, regular syntax, no `if`, no free loops, no `random`.
4. **Errors an AI can read.** Every error has a code, a line, a cause and the expected value.
5. **Two levels.** The *structural* level (chords, bars, patterns, sections) sits on top of the *expressive* level (velocity, micro-timing, articulation, controls).

LOMA does **not** produce audio (the sound depends on the synthesizer that plays the MIDI), does **not** compose and does **not** guarantee musical quality: it guarantees that a description always gives the same MIDI.

## 2. Conformance

The words **MUST**, **SHOULD** and **MAY** have the meaning of RFC 2119. A plain "must" counts as MUST.

A compiler is **conforming** if:

- for every valid file it produces exactly the events (§15) and the MIDI bytes (§16) defined here (MUST);
- for every invalid file it rejects the file and reports as its **first** error the same code and the same line as the reference compiler (MUST); the complete list of errors SHOULD match;
- it passes the suite in `conformance/` (§17).

The suite is the working definition of conformance: two independent compilers must produce the same bytes from the same files.

## 3. Arithmetic

All computation is on **integers**. Within the limits of §12 every intermediate value fits a signed 64-bit integer (and stays below 2^53).

**`floor_div(a, b)`** is ⌊a / b⌋, division rounded toward −∞, for any signs. Every division written `//` in this specification is `floor_div`.

| Expression | `floor_div` (MUST) | Truncation toward zero (NOT conforming) |
|---|---|---|
| `7 // 3` | 2 | 2 |
| `-7 // 3` | -3 | -2 |
| `7 // -3` | -3 | -2 |
| `-7 // -3` | 2 | 2 |

C, Java, Rust and JavaScript truncate toward zero: implementations in those languages must write `floor_div` by hand. Where the specification needs an exact result (durations, splitting a bar among chords) the compiler reports an error instead of rounding.

Resolution: **480 ticks per quarter note** (PPQ), not configurable. A whole note is 1920 ticks.

## 4. Text structure

- **Encoding**: UTF-8. A leading byte order mark is ignored. A file that is not valid UTF-8 gives `E001` at line 1.
- **Lines** end with LF or CR LF.
- **Blanks**: SPACE and TAB only. Other Unicode space characters separate nothing and cause an error. Indentation is free.
- **Comments**: `#` starts a comment only at the beginning of a line or after a blank, and never inside double quotes. So `F#3` is a pitch and `"a # b"` is a text.
- **Numbers**: ASCII digits `0`–`9` only, at most 9 digits (otherwise `E018`).
- **Names** (tracks, patterns, swings, voicings, sections): an ASCII letter followed by letters, digits or `_`. Each kind has its own namespace; names are unique within a kind (`E019`).
- **Reserved words**, not usable as names (`E019`): `loma title tempo meter key track pattern swing voicing section play at bar end repeat use from r pedal bend drums`.
- Empty lines are ignored. Every statement is one line, except the content of a track line, which may continue (§10.3).

The first non-empty line must be `loma VERSION` with version `0.1`, `0.2`, `0.3` or `1.0`. If it is missing or wrong, the compiler reports only that error. The declared version decides which constructs are allowed (§18): using a newer one gives `E020`.

## 5. Global statements

After the header, global statements may appear in any order, outside sections.

```
loma 1.0
title "Song name"
tempo 100
meter 4/4
key Cm
track RH ch=1 program=0
track Kit drums
```

| Statement | Rules | Default |
|---|---|---|
| `title "TEXT"` | At most one. The text contains no `"`. | no title |
| `tempo N` | At most one. BPM in **quarter notes** per minute, integer 4–400 (`E015`). | 120 |
| `meter N/D` | At most one. N from 1 to 64, D one of 1, 2, 4, 8, 16, 32, 64 (`E018`). | 4/4 |
| `key K` | At most one. It does not change the notes: it is written to the MIDI file as a Key Signature. Valid keys in §16 (`E013`). | none |
| `track NAME ch=N [program=P]` | Channel 1–16 except 10, exclusive to each track (`E011`). Program 0–127. | program 0 |
| `track NAME drums` | Drums on channel 10; at most one (`E011`). No options. | |

Repeating `title`, `tempo`, `meter` or `key` gives `E001`. A track must be declared **before** the line that uses it (`E008`). The order of the track declarations is the order of the tracks in the MIDI file. Patterns, swings, voicings and sections may be used before their definition, except the source of `pattern ... from` (§9.2).

## 6. Pitches and durations

### 6.1 Pitches

`C4` is middle C, MIDI 60. Value: `12 * (octave + 1) + semitone + accidental`, with C=0, D=2, E=4, F=5, G=7, A=9, B=11, `#` = +1, `b` = −1. The octave may be negative (`C-1` = 0). The result must be 0–127 (`E006`).

Since 1.0 a pitch can also be written as a MIDI number: `m60`. It works on every track.

On `drums` tracks, pitches are percussion names (or `mN`):

| Name | MIDI | Name | MIDI |
|---|---|---|---|
| `kick` | 36 | `crash` | 49 |
| `snare` | 38 | `ride` | 51 |
| `hat` | 42 | `tom1` | 50 |
| `ohat` | 46 | `tom2` | 47 |

A percussion name on a melodic track, or a note name on a `drums` track, gives `E001`.

### 6.2 Durations

A duration is `/` followed by a value. It is the **written duration**: how far time advances.

| Written | Ticks | Written | Ticks | Written | Ticks |
|---|---|---|---|---|---|
| `/1` | 1920 | `/2.` | 1440 | `/2t` | 640 |
| `/2` | 960 | `/4.` | 720 | `/4t` | 320 |
| `/4` | 480 | `/8.` | 360 | `/8t` | 160 |
| `/8` | 240 | `/16.` | 180 | `/16t` | 80 |
| `/16` | 120 | `/32.` | 90 | `/32t` | 40 |
| `/32` | 60 | `/64.` | 45 | `/64t` | 20 |
| `/64` | 30 | | | | |

Computation: `base = 1920 // n` with `n` one of 1, 2, 4, 8, 16, 32, 64 (otherwise `E007`); then one optional suffix:

| Suffix | Meaning | Formula |
|---|---|---|
| `.` | dotted | `base * 3 / 2` |
| `..` | double dotted | `base * 7 / 4` |
| `t` | triplet (3 in the time of 2) | `base * 2 / 3` |
| `q` | quintuplet (5 in the time of 4), since 0.2 | `base * 4 / 5` |
| `xA/B` | tuplet: A notes in the time of B, since 0.2 | `base * B / A` |

If the result is not an integer (for example `/64..` or `/8x7/4`: 480 is not divisible by 7) the compiler gives `E007`. `/8q` is 192 ticks, `/16q` 96, `/4x5/4` 384.

Exact duration in ticks: `/#N`, with N ≥ 1 (`/#210` = 210 ticks). It covers everything musical values cannot express.

## 7. Content of a line

The content of a track line is a sequence of elements separated by blanks. A **cursor** starts at 0 at the beginning of the bar (or of the segment, §10.4) and advances by the written duration of notes, rests and chords.

### 7.1 Notes, rests, chords

```
C4/4                 note
r/4                  rest
[C4 Eb4 G4]/2        chord: simultaneous notes, same duration
*open/2              the current chord played with a voicing (§9.4)
```

Elements must be separated by blanks (`C4/4C4/4` is `E001`).

### 7.2 Ties

`~` is written right after the duration, before the braces: `C4/2~ C4/4`, `C4/2~{v=80} C4/4`.

- The next note of the same track must have the **same pitch** and start exactly where this one ends. For chords: the same set of pitches.
- The tied note that follows **must not have attributes of its own** (neither on the element nor on single notes).
- Velocity, offset and articulation are those of the **first** note. The written duration of the merged note is the sum of the durations.
- A tie may cross bars, segments, sections and `repeat` blocks, but not the boundary between two different `play` statements.
- Controls (§7.5) and lyrics may stand between two tied notes; rests may not.
- Rests and notes of a `drums` track cannot be tied.

Every violation gives `E012`, at the line of the note that carries `~`.

### 7.3 Attributes

In braces, right after the element: `Eb5/8{v=78 o=-6}`.

| Attribute | Meaning | Default |
|---|---|---|
| `v=N` | velocity 1–127 | 80 |
| `o=N` | offset in ticks, signed: early or late | 0 |
| `d=N` | **sounding** length in ticks, N ≥ 1 | from `a=` |
| `a=` | articulation: `leg` 100%, `norm` 90%, `stac` 50% of the written duration | `norm` |

Attributes can be written at four levels. The most specific wins:

**note inside a chord > element > line > default**

```
RH{v=50}: [C4 E4{v=70} G4]/2{v=60}      # C4 and G4 at 60, E4 at 70
```

A rest has no attributes. An attribute repeated inside the same braces takes its last value.

**Written and sounding length.** The written duration (`/8`) moves the cursor; the sounding length says how long the note sounds. Without `d=`, the sounding length is `max(1, written * pct // 100)`.

**Offset.** It moves only the MIDI events of the note, not the cursor: `start = max(0, position + o)`, `end = start + sounding_length`. Offsets may create overlaps between different notes; for the same pitch see §14.

### 7.4 Line attributes (since 0.2)

Only in the braces after the track name:

- **`v=N>M`**: velocity ramp along the bar. A note at position `p` (ticks from the start of the bar, before the offset) gets `N + (M - N) * p // bar_length`. It is the line value: `v=` on the element or on the note replaces it. It also applies to pattern notes.
- **`swing=NAME`**: applies a swing table (§9.3). The table offset is **added** to the note's `o=`.

### 7.5 Controls

Controls have no duration of their own: they fire at the cursor position and do not move it.

| Element | Event | Since |
|---|---|---|
| `pedal+` / `pedal-` | controller 64 at 127 / 0. Not allowed on `drums` tracks. | 0.1 |
| `ccN=V` | control change N (0–127) with value V (0–127) | 0.2 |
| `bend=V` | pitch bend, V from −8192 to 8191 (0 = centre) | 0.2 |
| `ccN=A>B/D`, `bend=A>B/D` | linear ramp from A to B over the duration D | 0.2 |

**Ramp.** With `start` = cursor position and `len` = ticks of the duration D, the events are:

- one every 60 ticks: for `k = 0, 1, 2, ...` while `k * 60 < len`, at tick `start + k * 60`, with value `A + (B - A) * (k * 60) // len`;
- a final one at tick `start + len`, with value `B`.

All of them are emitted, even when two consecutive values are equal. The ramp does not move the cursor: it runs "under" the notes that follow and may go past the end of the bar.

Example: `cc1=10>0/4` (len = 480) gives the values 10, 8, 7, 6, 5, 3, 2, 1 at ticks 0, 60, ..., 420 and 0 at tick 480. Truncation toward zero would give 9, 8, 7, 5, 4, 3, 2: not conforming.

### 7.6 Lyrics (since 1.0)

`"text"` attaches a lyric (Lyric meta event) at the cursor position, in the track of the line. The text cannot be empty and cannot contain `"`.

```
Voice: "Fre" C4/4 "re" D4/4 "Ja" E4/4 "cques" C4/4
```

## 8. Chords and tones

Every bar declares one or more chords. A chord is used by patterns and voicings: it does not affect notes written by hand.

### 8.1 Symbols

`ROOT QUALITY [^INVERSION] [/BASS]`, without blanks. Root and bass are a letter `A`–`G` with an optional `#` or `b`.

| Quality | Intervals | Quality | Intervals |
|---|---|---|---|
| (empty) | 0 4 7 | `sus2` | 0 2 7 |
| `m` | 0 3 7 | `sus4` | 0 5 7 |
| `7` | 0 4 7 10 | `dim` | 0 3 6 |
| `maj7` | 0 4 7 11 | `aug` | 0 4 8 |
| `m7` | 0 3 7 10 | | |

Since 0.3:

| Quality | Intervals | Quality | Intervals |
|---|---|---|---|
| `5` | 0 7 | `add9` | 0 4 7 14 |
| `6` | 0 4 7 9 | `madd9` | 0 3 7 14 |
| `m6` | 0 3 7 9 | `9` | 0 4 7 10 14 |
| `dim7` | 0 3 6 9 | `maj9` | 0 4 7 11 14 |
| `m7b5` | 0 3 6 10 | `m9` | 0 3 7 10 14 |
| `mmaj7` | 0 3 7 11 | `11` | 0 4 7 10 14 17 |
| `7sus4` | 0 5 7 10 | `m11` | 0 3 7 10 14 17 |
| `7b9` | 0 4 7 10 13 | `13` | 0 4 7 10 14 21 |
| `7#9` | 0 4 7 10 15 | | |

An unknown symbol gives `E005`.

### 8.2 Inversions and bass (since 0.3)

- **`^K`**: inversion K. The K lowest notes go up an octave (`+12`), then the intervals are sorted in ascending order. `C^1` has intervals 4 7 12; `C^2` 7 12 16. K must be less than the number of notes (`E005`).
- **`/BASS`**: bass note (slash chord). It does not change the intervals: it defines tone `0`.

### 8.3 Tones

Patterns and voicings refer to chord notes by **tone numbers**. They are **ordinal indices** of the chord notes in ascending order (after the inversion), **not scale degrees**: on `Csus4` tone `3` is F.

| Tone | Note |
|---|---|
| `1`, `3`, `5`, `7`, `9`, `11` | first, second, ..., sixth note of the chord |
| `8`, `10`, `12`, `14`, `16`, `18` | the same six notes one octave up |
| `0` | the bass (since 0.3) |

Tones `9`, `11`, `16`, `18` and `0` need 0.3. Since 0.3 a tone may carry **octave marks**: each `+` raises it 12 semitones, each `-` lowers it (`5-`, `1++`).

With `base` = the octave given by the pattern or voicing, `pc(X)` = semitone of note X plus its accidental (so `pc(Cb)` = −1 and `pc(B#)` = 12):

- tone with index `i`: `12 * (base + 1) + pc(root) + intervals[i] + shift`;
- tone `0` with `/BASS`: `12 * base + pc(bass) + shift` (the bass note in octave `base − 1`);
- tone `0` without `/BASS`: `12 * base + pc(root) + intervals[0] + shift` (the lowest chord note, one octave down).

A tone number that does not exist (`2`, `13`, `20`...) gives `E010` at the definition. A tone the chord does not have (for example `7` on a triad) gives `E010` in the bar that uses it. A pitch outside 0–127 gives `E006`.

## 9. Patterns, swing, voicings

### 9.1 Patterns

```
pattern NAME base=OCTAVE dur=/DURATION : STEP STEP ...
```

- `base`: octave of the root, from −1 to 9 (`E006`). `dur`: default duration of the steps. The two options may come in either order.
- A step is a tone (`1`), a rest (`r`) or a group of simultaneous tones (`(1 5 8)`), followed by an optional duration of its own (`1/4`) and optional attributes (`1{v=70}`). A rest has no attributes.
- The length of the pattern is the sum of the durations of its steps.

```
pattern arp8 base=3 dur=/8 : 1 3 5 3 1 3 5 3
```

On `Cm` it plays C3 Eb3 G3 Eb3 C3 Eb3 G3 Eb3.

### 9.2 Variants (since 0.2)

```
pattern NAME from OTHER [base=OCTAVE] : INDEX=STEP ...
```

It copies the pattern `OTHER`, which must be defined **before** this line (`E004`), and replaces the given steps (indices from 1). A replacement step without a duration inherits the duration of the step it replaces. The list after the colon may be empty. `base=` changes the octave.

```
pattern arpB from arp8 : 4=8 8=r
```

### 9.3 Swing (since 0.2)

```
swing NAME grid=/DURATION : OFFSET OFFSET ...
```

A table of signed offsets in ticks. A line with `swing=NAME` gives every note that falls on the grid the offset `table[(p // grid) % table_length]`, where `p` is the position of the note in the bar. Notes that do not fall on the grid (`p % grid != 0`) get nothing.

```
swing shuffle grid=/8 : 0 40        # every off-beat eighth is 40 ticks late
```

### 9.4 Voicings (since 0.3)

```
voicing NAME base=OCTAVE : TONE TONE ...
```

A way of laying out the current chord. In the content of a melodic line, `*NAME/DURATION` plays the chord that is active at the cursor position with those tones; it takes `~` and attributes like a chord written by hand. It is not allowed on `drums` tracks (`E001`); an undefined voicing gives `E004`.

```
voicing open base=3 : 1 5 10
RH: *open/2 *open/2
```

### 9.5 Using a pattern

```
LH: use arp8
LH: use arp8,arpB       # since 0.2
```

- `use` is the whole content of a line or of a segment: it cannot be mixed with notes written by hand (`E016`). It is not allowed on `drums` tracks.
- The pattern is repeated until it fills **each chord segment** (§10.4), starting again at every segment with the chord of that segment.
- With a list, the patterns alternate cyclically: A, B, A, B...
- The fill must be exact: if a pattern would run past the end of the segment, `E009`.
- Pattern notes get the attributes of the line (ramp and swing included) and then those of the step.

## 10. Sections and bars

### 10.1 Sections

```
section NAME
  bar ...
  ...
end
```

A section is a sequence of bars and `repeat` blocks. A section that is never played is validated all the same.

### 10.2 Bars

```
bar CHORD [CHORD ...] [len=/D] [tempo=N | tempo=N>M]
```

- At least one chord. Chords and options may come in any order.
- **Length**: `numerator * (1920 // denominator)` from the `meter` (4/4 = 1920, 3/4 = 1440, 6/8 = 1440), or `len=/D` for irregular bars and pickups.
- **`tempo=N`**: tempo change at the start of the bar.
- **`tempo=N>M`**: linear ritardando or accelerando that reaches `M` at the end of the bar. Events: one every 480 ticks, for `k = 0, 1, ...` while `k * 480 < len`, with `bpm = N + (M - N) * (k * 480) // len`; plus a final one at the end of the bar with value `M`. Example, 4/4, `tempo=100>70`: 100, 92, 85, 77 at ticks 0, 480, 960, 1440 and 70 at tick 1920.
- BPM are integers from 4 to 400 (`E015`). The whole curve is computed in BPM; the conversion to microseconds happens only when the MIDI is written.
- The song has **at most one tempo per tick: the last one declared wins**, in this order: the initial `tempo`, the bars in playing order, then the `at ... tempo=` statements in file order.

### 10.3 Track lines

```
TRACK{line attributes}: content
```

- A track has at most one line per bar (`E001`). A track that is not named is silent.
- Since 0.2 the content may continue on the following lines: every line that is not `bar`, `repeat`, `end` or a new track line continues the previous line.
- A line with no content at all gives `E001`.
- The content must fill the bar **exactly**, otherwise `E003`.

```
RH{v=70}:
  C5/8 D5/8 E5/4
  G5/2
```

### 10.4 Several chords in one bar

`bar Cm Ab Bb` splits the bar into **equal segments**, one per chord. Every split that is whole in ticks is allowed (4/4 with three chords: 640 ticks each); otherwise `E014`. The active chord changes at the start of each segment.

A line can be written in two ways:

- **Without `|`**: it covers the whole bar. With `use`, the pattern starts again at each segment. Notes written by hand may cross the boundary between segments.
- **With `|`** (since 0.2): one part per segment. The number of parts must equal the number of chords (`E021`). Each part is either `use ...` or notes, and must fill its own segment exactly (`E003`, `E009`).

```
bar Cm Ab
  LH: use arp4 | C3/4 Eb3/4
```

### 10.5 `repeat` blocks (since 0.2)

```
repeat N
  bar ...
end
```

It repeats the bars it contains N times (1–1000). Blocks can be nested. The bar number reported in errors is the position of the bar in the text of the section, not in the performance.

## 11. Arrangement: `play` and `at`

### 11.1 `play`

```
play NAME [xN] [transpose=±S]
```

The order of the `play` statements is the order of the song. `xN` repeats the section N times (1–1000). `transpose` shifts by S semitones every note of the melodic tracks, including those of patterns, voicings and `mN`; drums are not transposed. A note that leaves 0–127 gives `E006`.

### 11.2 `at`

Events at absolute ticks, counted from the start of the song after expansion. They are written outside sections.

```
at TICK TRACK PITCH d=TICKS [v=VELOCITY]
at TICK TRACK ccN=V             # since 1.0
at TICK TRACK bend=V            # since 1.0
at TICK TRACK "text"            # since 1.0
at TICK tempo=BPM               # since 1.0
```

- The note is already resolved: `d=` is required and is the sounding length; it has no offset, articulation or ties; `v=` is 80 when omitted.
- `at` notes take part in the check for duplicates and overlaps (§14).
- `at` forms take no ramps and are not transposed.

`loma decompile` uses these forms to rewrite a MIDI file as LOMA source without loss.

## 12. Limits

A conforming compiler MUST reject files that exceed these limits.

| Item | Limit | Error |
|---|---|---|
| Digits of a number | at most 9 | `E018` |
| `meter` numerator / denominator | 1–64 / 1, 2, 4, 8, 16, 32, 64 | `E018` |
| Repetitions (`xN`, `repeat N`) | 1–1000 | `E018` |
| Bars after expansion | at most 100000 | `E018` |
| Tick of any event | ≤ 268435455 | `E018` |
| Notes (after expansion, before ties) | at most 1000000 | `E018` |
| Control events (cc, bend, lyrics) | at most 1000000 | `E018` |
| Expanded elements (notes, rests, controls, pattern steps) | at most 4000000 | `E018` |
| Nested `repeat` blocks | at most 16 levels | `E018` |
| Tempo | 4–400 BPM | `E015` |

The limits on bars, notes, controls, expanded elements and song length are **fatal**: the compiler stops and reports only that error.

## 13. Errors

Every error has a **code**, a **line** and a message; where it makes sense, also section, bar, chords, track and numeric values.

```
E003 line 14 bar 2 (Ab) track RH: bar length mismatch. Expected 1920 ticks, got 1680. Missing 240 ticks (= /8).
```

JSON form (`--json`): an array of objects. `code` and `line` are required; the other fields SHOULD be present. A compiler MAY add `suggestion` (for example `"suggestion": "add_rest", "duration": "/8"`), but it never changes the file.

```json
[{"code": "E003", "line": 14, "section": "verse", "bar": 2, "chord": "Ab", "track": "RH",
  "message": "bar length mismatch. Expected 1920 ticks, got 1680. Missing 240 ticks (= /8).",
  "expected": 1920, "got": 1680, "missing": 240, "suggestion": "add_rest", "duration": "/8"}]
```

| Code | Meaning |
|---|---|
| E001 | Syntax error (also: an attribute or option value outside its allowed range) |
| E002 | Unknown command |
| E003 | The content does not fill the bar or the segment exactly |
| E004 | Undefined name: pattern, section, swing or voicing |
| E005 | Unknown chord symbol or impossible inversion |
| E006 | Pitch outside 0–127, or `base` octave outside −1..9 |
| E007 | Invalid duration (denominator not allowed, or result not a whole number of ticks) |
| E008 | Undeclared track |
| E009 | The pattern does not fill the bar or the segment exactly |
| E010 | Tone that does not exist, or that the chord does not have |
| E011 | Channel already used, channel 10 on a melodic track, or more than one `drums` track |
| E012 | Invalid tie |
| E013 | Invalid key |
| E014 | Bar that cannot be split into whole parts among its chords |
| E015 | Tempo outside 4–400 BPM |
| E016 | `use` mixed with notes in the same segment |
| E017 | Duplicate notes: same pitch, same channel, same starting tick |
| E018 | Limit exceeded (§12) |
| E019 | Invalid, reserved or duplicate name |
| E020 | Construct not available in the declared version (§18) |
| E021 | Number of segments (`|`) different from the number of chords |

### 13.1 Order and phases

Errors are reported **sorted by line**, then by code, without repetitions (same code, same line, same track).

1. **Syntax phase**, line by line: at most **one error per line**. If this phase finds errors, the next one does not run.
2. **Semantic phase**, only on a syntactically clean file: for each bar the **first** error, following the track lines in the order they are written (`E014`, `E021`, `E004`, `E009`, `E010`, `E006`, `E003`); then ties (`E012`), then duplicate notes and events past the limit (`E017`, `E018`). Sections that are never played are validated bar by bar.

Recovery rules of the syntax phase, to avoid cascades of errors (SHOULD):

- a wrong `bar` line makes the compiler ignore its track lines;
- a wrong track line makes it ignore its continuation lines;
- a wrong `track` declaration makes it ignore the lines that use that name;
- a wrong `section` or `repeat` header does not prevent the analysis of its body;
- a global statement inside a section gives `E001` ("missing `end`") and closes the section.

Reported line: the one where the construct is written. For `E003` it is the line of the last element of the line or segment (the first line of the track line, if the segment is empty); for `E004` on a section it is the line of the `play`; for `E009`, `E021` and pattern errors it is the first line of the track line; for `E014` it is the `bar` line; for `E017` it is the line of the second note.

## 14. Note resolution

For every note a compiler MUST apply these steps in this order:

1. **Expansion.** `play`, repetitions, `repeat`, transposition, patterns and voicings produce, for each track, a sequence of notes with a position (cursor) and a written duration.
2. **Attributes.** Defaults, then line (with the velocity ramp and the swing computed at the position of the note), then element, then note.
3. **Ties.** Tied notes merge into one: written duration = sum, attributes of the first.
4. **Sounding length.** `d=` if present, otherwise `max(1, written_duration * pct // 100)`.
5. **Offset.** `start = max(0, position + o + swing)`, `end = start + sounding_length`.
6. **Duplicates and overlaps**, among all notes with the same pitch on the same channel (including `at` notes), sorted by start: two notes with the same start give `E017`; if a note starts while the previous one is still sounding, the end of the previous one is moved to the start of the new one.
7. **Events.** Note-on, note-off, controls and tempo go to the ordering of §15.

## 15. Events: order and canonical JSON

### 15.1 Ordering

All events are sorted by the key:

```
(tick, type, track_index, channel, pitch, sequence_number)
```

Types within the same tick: **0** tempo, **1** note-off, **2** controls (control change, pitch bend, lyrics), **3** note-on. A note-off before the note-on lets the same note be struck again; a control before the note-on acts on the note that starts at that tick.

- Tempo events have `track_index = -1`, channel 0, pitch 0.
- Controls have pitch 0, so within a tick they keep the order in which they were generated.
- `sequence_number` is a **per-track** counter starting at 0. It is assigned after ties, walking through the elements of the track in expansion order (bars in playing order; inside a bar, parts and elements in written order; the steps of a pattern in order): every control event takes one number (a ramp: one per event); every note takes two consecutive ones, note-on and note-off; the notes of a chord in written order, those of a group or a voicing in the order of the tones. A note merged by a tie is numbered in the place of its first note. `at` events are numbered **after** all other events of the track, in file order.

A compiler must never rely on the implicit order of dictionaries, sets or libraries: it builds the list and sorts it with this key.

### 15.2 Canonical JSON

`loma expand FILE --json` prints the events in the order of §15.1. It shows where two compilers diverge: in the interpretation (LOMA → events) or in the writing of the bytes (events → MIDI).

Format: a JSON array on a single line, followed by exactly one newline. Every event is an object with its **keys in alphabetical order**, no blanks, separators `,` and `:`. Strings are UTF-8 with non-ASCII characters left unescaped.

| `type` | Fields |
|---|---|
| `tempo` | `bpm`, `tick`, `type` |
| `note_on` | `ch`, `pitch`, `tick`, `track`, `type`, `vel` |
| `note_off` | `ch`, `pitch`, `tick`, `track`, `type` |
| `cc` | `ch`, `controller`, `tick`, `track`, `type`, `value` |
| `bend` | `ch`, `tick`, `track`, `type`, `value` |
| `lyric` | `text`, `tick`, `track`, `type` |

```
[{"bpm":120,"tick":0,"type":"tempo"},{"ch":1,"pitch":60,"tick":0,"track":"P","type":"note_on","vel":80},{"ch":1,"pitch":60,"tick":1728,"track":"P","type":"note_off"}]
```

## 16. Canonical MIDI

- Standard MIDI File **format 1**, 480 ticks per quarter note.
- `MThd`: length 6, format 1, number of tracks = 1 + number of declared `track`s, division `0x01E0`.
- **Track 0 (conductor)**, at tick 0 in this order:
  1. Track Name `FF 03` with the `title`, if present (UTF-8);
  2. Time Signature `FF 58 04 nn dd 18 08`: `nn` numerator, `dd` log2 of the denominator;
  3. Key Signature `FF 59 02 sf mi`, if `key` is present (table below);
  4. the Set Tempo events `FF 51 03 tttttt`, each at its tick. Value: `60000000 // bpm` microseconds per quarter note, on 3 bytes.
- One MIDI track per `track`, in declaration order. At tick 0: Track Name `FF 03` with the LOMA name, then Program Change `Cn pp` (not for `drums`), then the events of the track in the order of §15.1.
- Encoding, with `n` = channel − 1:

| Event | Bytes |
|---|---|
| note-on | `9n pp vv` |
| note-off | `8n pp 40` (release velocity fixed at 64) |
| control change | `Bn cc vv` |
| pitch bend | `En ll mm`, with `x = value + 8192`, `ll = x & 0x7F`, `mm = x >> 7` |
| lyric | `FF 05 len text` (UTF-8) |

- Delta times as VLQ. **No running status**: every event writes its own status byte.
- **End of Track** `FF 2F 00` in every track, even an empty one, all at the same tick: `end = max(total length of the bars played, tick of the last event)`.
- The length of each `MTrk` chunk is the number of bytes it contains. No other metadata: no timestamp, no software name or version.

**Keys.** `sf` is the number of sharps (positive) or flats (negative), as a signed byte; `mi` is 0 for major, 1 for minor.

| sf | Major | Minor | sf | Major | Minor |
|---|---|---|---|---|---|
| 0 | `C` | `Am` | | | |
| 1 | `G` | `Em` | −1 | `F` | `Dm` |
| 2 | `D` | `Bm` | −2 | `Bb` | `Gm` |
| 3 | `A` | `F#m` | −3 | `Eb` | `Cm` |
| 4 | `E` | `C#m` | −4 | `Ab` | `Fm` |
| 5 | `B` | `G#m` | −5 | `Db` | `Bbm` |
| 6 | `F#` | `D#m` | −6 | `Gb` | `Ebm` |
| 7 | `C#` | `A#m` | −7 | `Cb` | `Abm` |

### 16.1 Example with the expected bytes

These bytes were worked out by hand from the specification, not taken from a compiler.

```loma
loma 0.1
tempo 120
meter 4/4
track P ch=1 program=0
section s
  bar C
    P: C4/1
end
play s
```

The note lasts `1920 * 90 // 100 = 1728` ticks; the song ends at tick 1920. The file is 72 bytes long.

```
4D 54 68 64  00 00 00 06  00 01  00 02  01 E0        MThd, format 1, 2 tracks, 480 PPQ
4D 54 72 6B  00 00 00 14                             MTrk (conductor), 20 bytes
  00 FF 58 04 04 02 18 08                            time signature 4/4
  00 FF 51 03 07 A1 20                               tempo 500000 us (120 BPM)
  8F 00 FF 2F 00                                     end of track, delta 1920
4D 54 72 6B  00 00 00 16                             MTrk (P), 22 bytes
  00 FF 03 01 50                                     track name "P"
  00 C0 00                                           program change 0, channel 1
  00 90 3C 50                                        note-on  C4 (60), velocity 80
  8D 40 80 3C 40                                     note-off C4, delta 1728
  81 40 FF 2F 00                                     end of track, delta 192
```

SHA-256: `ab4d7aaa44d5b98d3df8d7df7937dbee852d20ce3869a8b5d4612758349bb460`.

## 17. Command line and conformance suite

The suite talks to a compiler through three commands. A compiler that wants to be checked MUST offer them:

| Command | Behaviour |
|---|---|
| `CMD compile FILE -o OUT` | Writes the MIDI file. Exit status 0; 1 if the file has errors. |
| `CMD expand FILE --json` | Prints the canonical JSON (§15.2). Status 0. |
| `CMD check FILE --json` | Valid file: prints `[]`, status 0. Invalid file: prints the array of errors (§13), status 1. |

`FILE` may be `-` to read standard input (SHOULD).

The suite is in `conformance/`:

- `valid/NAME.loma` with `NAME.mid`, `NAME.events.json`, `NAME.sha256`: the compiler must produce the same bytes and the same JSON;
- `errors/NAME.loma` with `NAME.errors.json`: the compiler must report the same `code` and `line`, in the same order (with `--first-error-only` only the first one is compared, the minimum required by §2).

```
python3 conformance/run.py --cmd "python3 -m loma"
python3 conformance/run.py --cmd "node js/loma.js"
```

## 18. Language versions

Each version is a superset of the previous one: a file that is valid in one version gives the same bytes if it declares a later version. Using a construct without declaring the version that introduces it gives `E020`.

| Version | Adds |
|---|---|
| **0.1** | Notes, rests, chords, ties, attributes, pedal, drums, patterns, sections, `play`, transposition, `at` for notes, tempo changes |
| **0.2** | `ccN=`, `bend=` and ramps; velocity ramp `v=N>M`; `swing`; content on several lines; segments with `\|`; lists `use A,B`; `pattern ... from`; quintuplets `q` and tuplets `xA/B`; `repeat` blocks |
| **0.3** | Extended chords; inversions `^K`; bass `/X` and tone `0`; tones `9 11 16 18`; octave marks; `voicing` and `*NAME` |
| **1.0** | Lyrics `"..."`; numeric pitches `mN`; `at` with `cc`, `bend`, lyric and `tempo` |

## 19. Complete example

```loma
loma 1.0
title "Example"
tempo 100
meter 4/4
key Cm

track RH ch=1 program=0
track LH ch=2 program=0
track Kit drums

pattern arp8 base=3 dur=/8 : 1 3 5 3 1 3 5 3
pattern arpB from arp8 : 8=8
swing light grid=/8 : 0 12
voicing open base=3 : 1 5 10

section verse
  bar Cm
    RH{v=78}: Eb5/8 D5/8 C5/4 G4/4 r/4
    LH{v=60 swing=light}: use arp8
    Kit{v=64}: kick/4 hat/4 snare/4 hat/4
  bar Ab Bb
    RH{v=70>90}: C5/4 Eb5/4 | D5/4. F5/8{o=-6}
    LH{v=60}: *open/2 | *open/2
    Kit{v=64}: kick/4 hat/4 | snare/4 hat/8 hat/8
  repeat 2
    bar Gm
      RH{v=72}: "la" G4/2~ G4/4 Bb4/4{a=stac}
      LH{v=55}: use arpB
  end
end

section ending
  bar Cm tempo=100>70
    RH{v=70}: pedal+ cc11=100>40/1 [C4 Eb4 G4]/1{a=leg} pedal-
    LH{v=55}: C2/1{a=leg}
    Kit{v=50}: crash/1
end

play verse x2
play ending
```
