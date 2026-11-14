# LOMA

*English · [Italiano](README.it.md)*

LOMA is a text language for describing music, designed to be **written by an AI** and **compiled deterministically to a MIDI file**: the same `.loma` file gives the same `.mid`, byte for byte, every time and with any conforming compiler.

- Full specification: [SPEC.md](SPEC.md) (English), [SPEC.it.md](SPEC.it.md) (Italian)
- Formal grammar: [spec/grammar.ebnf](spec/grammar.ebnf)
- Changes by version: [CHANGELOG.md](CHANGELOG.md)

## An example

```loma
loma 1.0
title "First example"
tempo 100
meter 4/4
key Cm

track RH ch=1 program=0
track LH ch=2 program=0

pattern arp8 base=3 dur=/8 : 1 3 5 3 1 3 5 3

section verse
  bar Cm
    RH{v=78}: Eb5/8 D5/8 C5/4 G4/4 r/4
    LH{v=60}: use arp8
  bar Ab
    RH{v=70>88}: C5/4 Eb5/4{o=-6} Ab4/2{a=leg}
    LH{v=60}: use arp8
end

play verse x2
```

The AI writes intentions (chord `Cm`, the left hand plays the arpeggio, the melody grows from 70 to 88); the compiler expands them into notes on integer ticks. `/8` is an eighth note, `r` a rest, `{o=-6}` plays 6 ticks early, `x2` repeats the section.

## Playground

`docs/index.html` is a web page that runs entirely in the browser: paste or edit LOMA, read the errors next to their lines, play the result on a piano roll, download the MIDI file, or open a `.mid` file to turn it into LOMA. It embeds the JavaScript compiler, so there is no server. To publish it with GitHub Pages, choose the `docs` folder of the main branch in the repository settings.

The sound comes from a small synthesizer inside the page, not from real instruments. After changing `js/loma.js`, the examples or `docs/playground.src.html`, rebuild the page with `python3 tools/build_web.py`.

## Usage

Python 3.9 or later, no dependencies (tested with Python 3.11, 3.12 and 3.13; the second implementation with Node.js 22).

```
python3 -m loma compile song.loma -o song.mid       # compile
python3 -m loma check song.loma --json              # validate only, errors as JSON
python3 -m loma expand song.loma --json             # events in ticks, canonical JSON
python3 -m loma hash song.loma                      # SHA-256 of the MIDI file
python3 -m loma test-determinism song.loma          # compile 100 times and compare
python3 -m loma decompile song.mid -o song.loma     # from MIDI to LOMA
```

After `pip install .` the command is `loma`. The file name may be `-` to read standard input. Exit status: 0 success, 1 errors in the file, 2 usage or I/O problem.

An error says where and what to fix:

```
E003 line 14 bar 2 (Ab) track RH: bar length mismatch. Expected 1920 ticks, got 1680. Missing 240 ticks (= /8).
```

## What is in the repository

| Folder | Content |
|---|---|
| `loma/` | Reference compiler in Python: parser, expansion, events, MIDI writer, decompiler, command line |
| `js/` | Second implementation in JavaScript (Node.js and browser), used to check conformance |
| `docs/` | The playground web page: `index.html` is self-contained and can be served with GitHub Pages |
| `conformance/` | Conformance suite: 95 valid files with the expected bytes, 109 files with the expected errors, and the program that compares them |
| `spec/` | EBNF grammar |
| `tests/` | Automated tests |
| `tools/` | Regeneration of the suite, comparison of the two implementations on random files, build of the web page |
| `examples/` | Example pieces, including `showcase.loma`, which uses every construct |
| `experiment/` | Material for the experiment with several AIs: assignment, collection of the files, measurements |
| `editors/vscode/` | Syntax highlighting for Visual Studio Code |

## Checks

```
python3 -m unittest discover -s tests                       # all tests
python3 conformance/run.py --cmd "python3 -m loma"          # suite on the Python compiler
python3 conformance/run.py --cmd "node js/loma.js"          # suite on the JavaScript compiler
python3 tools/fuzz_compare.py --count 5000                  # random files: Python against JavaScript
```

What is verified:

- **Same bytes from two implementations.** The Python and the JavaScript compilers produce the same events and the same bytes on all 204 cases of the suite and on thousands of randomly generated files, valid and invalid.
- **Bytes worked out by hand.** The minimal file in [SPEC.md §16.1](SPEC.md#161-example-with-the-expected-bytes) was computed by hand from the specification and matches the output.
- **Round trip.** Every MIDI file of the suite, decompiled and compiled again, comes back identical.

What is **not** verified:

- Both implementations have the same author. A misreading of the specification may be present in both: the decisive proof is still a compiler written by someone else from `SPEC.md` alone.
- Nobody has yet listened critically to the example pieces: LOMA guarantees that the MIDI is always the same, not that it sounds good.
- The experiment with several AIs (`experiment/`) so far contains only the three pieces written by the author of the specification.

## Writing LOMA with an AI

[experiment/prompt.md](experiment/prompt.md) (in Italian) contains a compact reference of the language and the assignments for the three test pieces, ready to paste. The intended loop: the AI writes the file, `loma check --json` returns the errors, the AI fixes only the lines indicated.

## Roadmap status

| Phase | Status |
|---|---|
| 0.1 — deterministic core | Done |
| 0.1 — EBNF grammar and second implementation | Done (same author) |
| 0.1 — experiment with AIs | Tools ready; pieces written by other models are missing |
| 0.2 — expression and variety | Done |
| 0.3 — advanced harmony | Done |
| 1.0 — stable specification, documentation, public suite | Done |
| MIDI to LOMA, lyrics, syntax highlighting | Done |

## Contributing

A change must keep the bytes: run the tests before opening a pull request. Regenerating the expected files of the suite (`tools/make_conformance.py`) is a change of the specification and must be deliberate.

## License

MIT, see [LICENSE](LICENSE).
