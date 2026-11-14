# Experiment: can AIs write LOMA?

*English · [Italiano](README.it.md)*

The hypothesis to verify is this: can a model write music in LOMA more reliably, compactly and controllably than with the alternatives?

## Protocol

1. Give an AI the text of [prompt.md](prompt.md) (English) or of [prompt.it.md](prompt.it.md) (Italian), with nothing else. Note which one you used: the two versions have the same rules, but the language can change the result.
2. Save every answer as it is (the folder names `brano1`, `brano2`, `brano3` are Piece 1, 2 and 3 of the assignment):

   ```
   experiment/submissions/MODEL_NAME/brano1/attempt1.loma
   experiment/submissions/MODEL_NAME/brano2/attempt1.loma
   experiment/submissions/MODEL_NAME/brano3/attempt1.loma
   ```

3. Check the file:

   ```
   python3 -m loma check experiment/submissions/MODEL_NAME/brano1/attempt1.loma --json
   ```

4. If there are errors, paste to the AI **only** the output of the command and save the new answer as `attempt2.loma`. Repeat until the file is valid or up to five attempts. Do not fix anything by hand.
5. Compute the measurements:

   ```
   python3 experiment/run_experiment.py
   ```

   The program writes `results.md` and `results.json`.

6. Compile the MIDI file of the last attempt, listen to it and fill in by hand the columns *Fidelity* (does the MIDI match what the AI says it wrote?) and *Listening* (does it sound convincing?).

## What is measured

| Indicator | How |
|---|---|
| Compilation attempts | number of `attemptN.loma` files |
| Most frequent errors | error codes of all the attempts |
| Size | bytes of the LOMA file, of the MIDI file and of the expanded events |
| Compliance with the assignment | bars, instruments, patterns, chords, tempo, sections |
| Reproducibility | 20 compilations, same SHA-256 |
| Musical fidelity | by hand |
| Listening quality | by hand |

## Status

`submissions/reference/` contains the three pieces written by the author of the specification and of the compiler. They prove that the tools work and serve as a term of comparison: **they are not an independent measurement**, because whoever wrote them already knew all the rules. The experiment is complete when there are pieces by other models.
