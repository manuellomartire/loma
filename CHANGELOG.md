# Changelog

*English · [Italiano](CHANGELOG.it.md)*

The versions of the language are cumulative: a file that is valid in one version produces the same bytes if it declares a later one. The compiler accepts `loma 0.1`, `0.2`, `0.3` and `1.0`.

## Compiler 1.1.0 (language 1.0)

The bytes produced by valid files do not change. What changes is which errors are reported for invalid files.

- **Errors in one round.** Syntax errors and the bar checks on the readable lines are reported together (before, content errors appeared only after all the syntax had been fixed). The rules are in SPEC §13.1; ties, duplicate notes and limits are still checked only on a syntactically clean file.
- **Suggestions.** A mistyped name proposes the right one: `unknown chord 'Cmaj'. Did you mean 'C'?`, and the same for tracks, patterns, swings, voicings, sections, drum names and commands. In the JSON form the field is `did_you_mean`.
- A track line without `:` after the name has a message that says so.
- Conformance suite: 7 new `X_mixed_*` cases; `X_syntax_before_semantics` became `X_syntax_and_semantics`; the expected list of `E007_tuplets` changes.
- Playground: a Compile button (or Ctrl/⌘+Enter) instead of compiling while typing, links to the repository and to the specification, shareable link of the piece, "copy the errors", a button for the light or dark theme, preview for social networks.
- Documentation in English and in Italian for the changelog, the conformance suite, the experiment and the assignment for the AIs. The report of the experiment is in English.
- Tests on Linux, Windows and macOS; `.gitattributes` to keep the bytes of the suite files on every system.

## 1.0

Language:

- Lyrics: `"text"` in the content of a line (Lyric meta event).
- Numeric pitches `mN`, valid on every track.
- `at` with `ccN=V`, `bend=V`, `"text"` and `tempo=BPM`.
- Numbers limited to 9 digits (`E018`).
- Reserved words cannot be used as names (`E019`).
- Only space and tab are spaces; only ASCII digits are numbers.
- New errors: `E020` (construct of a later version), `E021` (number of segments).
- Limit of 100000 bars and of 1000000 control events after expansion.

Tools:

- `loma decompile`: from MIDI to LOMA, lossless for the files produced by LOMA.
- Reading from standard input with `-`.
- Second implementation in JavaScript (`js/loma.js`).
- Public conformance suite (`conformance/`) with its checking program.
- Comparison of the two implementations on random files (`tools/fuzz_compare.py`).
- EBNF grammar (`spec/grammar.ebnf`), specification in Italian and in English.
- Syntax highlighting for Visual Studio Code.
- Web playground (`docs/index.html`): editor, errors, playback on a piano roll, conversion between LOMA and MIDI in both directions, all in the browser.
- The JavaScript compiler also works in the browser and has its own decompiler (`node js/loma.js decompile`).

## 0.3

- Extended chords: `5 6 m6 dim7 m7b5 mmaj7 7sus4 7b9 7#9 add9 madd9 9 maj9 m9 11 m11 13`.
- Inversions `^K` and bass `/X`.
- Tones `0` (bass), `9`, `11`, `16`, `18`; octave signs `+` and `-`.
- `voicing` and `*NAME` in the content of a line.

## 0.2

- Control change `ccN=V`, pitch bend `bend=V`, ramps `A>B/D`.
- Line velocity ramp `v=N>M`.
- `swing` as an explicit table of offsets.
- Content of a line on several lines.
- Segments `|`: different content for each chord of the bar.
- Pattern lists `use A,B` and variants `pattern ... from`.
- Quintuplets `q` and irregular groups `xA/B`.
- Nestable `repeat` blocks.

## 0.1

- Notes, rests, chords, ties, attributes `v o d a`, pedal, drums.
- Patterns that adapt to the chord, sections, `play`, transposition, `at` for notes.
- Tempo changes and tempo ramps.
- Canonical MIDI, ordering of the events, canonical JSON, errors `E001`–`E019`.

Differences of behaviour from the first 0.1 compiler, all on invalid files: errors are always sorted by line; a wrong header is reported alone; a global statement inside a section is reported only once. The bytes produced by valid files have not changed.
