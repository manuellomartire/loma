# Assignment for the LOMA experiment

*English · [Italiano](prompt.it.md)*

Paste all of this text to an AI. Add nothing else: the experiment measures how easy the language is to write starting from these instructions alone.

---

You must write music in the LOMA 1.0 language. A compiler will turn your file into MIDI. Answer only with the file, inside a code block, without explanations.

## Quick reference

```loma
loma 1.0
title "Title"
tempo 96
meter 4/4
key Am

track Mel ch=1 program=73
track Pno ch=2 program=0
track Kit drums

pattern arp base=3 dur=/8 : 1 3 5 3 1 3 5 3
pattern arpB from arp : 8=8
pattern half base=3 dur=/8 : 1 5 8 5
swing light grid=/8 : 0 12
voicing open base=3 : 1 5 10

section a
  bar Am
    Mel{v=80}: A4/4 C5/8 B4/8 A4/2{a=leg}
    Pno{v=56 swing=light}: use arp
    Kit{v=64}: kick/4 hat/4 snare/4 hat/8 hat/8
  bar F G
    Mel{v=70>90}: C5/2 | D5/4. B4/8{o=-6}
    Pno{v=56}: use half | *open/2
    Kit{v=64}: kick/4 hat/4 | snare/4 hat/4
end

section ending
  bar Am tempo=96>70
    Mel{v=64}: pedal+ [A4 C5 E5]/1{a=leg} pedal-
    Pno{v=50}: use arpB
    Kit{v=50}: crash/1
end

play a x2
play ending
```

Rules:

1. **Header.** First line `loma 1.0`. Then `tempo` (BPM), `meter`, `key`, and one `track` per instrument: `track NAME ch=N program=P` (channel 1–16 except 10, one per track; `program` is the General MIDI instrument 0–127) or `track NAME drums`.
2. **Durations.** `/1` = 1920 ticks, `/2` = 960, `/4` = 480, `/8` = 240, `/16` = 120. Dotted: `/4.` = 720, `/8.` = 360. Triplet: `/8t` = 160, `/4t` = 320. Quintuplet: `/8q` = 192. Exact ticks: `/#100`.
3. **Notes.** `C4/4` (C4 = middle C), rest `r/4`, chord `[C4 E4 G4]/2`, tie `C4/2~ C4/4` (same pitch, the second note without attributes). Drums: `kick snare hat ohat crash ride tom1 tom2`.
4. **Every line must fill the bar exactly**: in 4/4 the sum is 1920 ticks, in 3/4 it is 1440. Add up the durations before answering.
5. **Attributes** in braces after the note: `v=` velocity 1–127, `o=` early or late offset in ticks, `a=leg|norm|stac`, `d=` sounding duration in ticks. After the track name they apply to the whole line: `Mel{v=80}: ...`. On the line you can also write a ramp `v=60>90` and `swing=NAME`.
6. **Chords of the bar.** `bar Am`, `bar F G` (two chords: half a bar each). Qualities: major, `m`, `7`, `maj7`, `m7`, `dim`, `aug`, `sus2`, `sus4`, `6`, `9`, `maj9`, `m9`, `add9`, `m7b5`, `dim7`, `13`. Bass: `C/E`.
7. **Patterns.** The numbers are the notes of the chord: `1` the first, `3` the second, `5` the third, `7` the fourth (only on four-note chords), `8 10 12` the same an octave up, `0` the bass. `(1 5)` plays several tones together, `r` is a rest. `use NAME` takes the whole line or the whole segment and repeats until it fills **each chord**: the length of the pattern must divide the duration of the chord exactly. Patterns are not used on drums.
8. **Segments.** In a bar with several chords you can separate the parts with `|`, one per chord; each part fills its own portion.
9. **Controls**, without duration: `pedal+` `pedal-`, `cc7=100`, `bend=0`, ramps `cc11=40>100/1`.
10. **Structure.** `section NAME ... end`, inside a section `repeat N ... end`, then `play NAME`, `play NAME x2`, `play NAME transpose=+2`. Tempo change: `bar Am tempo=80`, rallentando `bar Am tempo=96>70`.
11. A comment starts with `#` after a space. Names are letters, digits and `_`.
12. No randomness: if you want a variation, write it. Write the expression: different velocities for melody and accompaniment, some `o=`, `a=leg` or `a=stac` where needed.

If you receive a list of errors, fix only the lines indicated and answer again with the complete file.

## The three pieces

Write three separate files, with original melodies.

**Piece 1.** 8 bars, solo piano, melody and accompaniment, a single key.

**Piece 2.** 16 bars, three instruments, with patterns, repeats and dynamic variations, and at least some bars with two chords.

**Piece 3.** 32 bars, four or five instruments, at least one tempo change, articulations and micro-timing (`o=`), a structure in several sections.
