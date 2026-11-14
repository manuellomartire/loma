#!/usr/bin/env python3
"""Measures the LOMA experiment: how reliably different AIs write LOMA.

Layout of the submissions:

    experiment/submissions/MODEL/PIECE/attempt1.loma
    experiment/submissions/MODEL/PIECE/attempt2.loma      (after the errors of attempt 1), ...

PIECE is brano1, brano2 or brano3. The last attempt is the final answer.

    python3 experiment/run_experiment.py                  # prints the report and writes results.md / results.json

Two indicators cannot be measured by a program and are left for a person to fill in:
fidelity to the composer's intentions and quality when listening.
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from loma.api import compile_text, sha256
from loma.errors import LomaErrors
from loma.events import canonical_json
from loma.expander import flatten
from loma.model import WHOLE
from loma.parser import parse

REQUIREMENTS = {
    "brano1": {"bars": 8, "instruments": (1, 2)},
    "brano2": {"bars": 16, "instruments": (3, 3), "patterns": True, "two_chord_bars": True, "dynamics": True},
    "brano3": {"bars": 32, "instruments": (4, 5), "tempo_change": True, "sections": 2, "offsets": True},
}


def attempt_number(path):
    m = re.search(r"attempt([0-9]+)\.loma$", path)
    return int(m.group(1)) if m else 0


def analyse(text):
    """Facts about a valid file, used to check the assignment."""
    song = parse(text)
    compiled, midi = compile_text(text)
    bars, two_chord, tempo_change, played = 0, False, False, set()
    for play in song.plays:
        flat = []
        flatten(song.sections[play.name].body, flat)
        bars += play.times * len(flat)
        played.add(play.name)
        for bar in flat:
            two_chord = two_chord or len(bar.chords) > 1
            tempo_change = tempo_change or bar.tempo is not None
    tempo_change = tempo_change or any(a.kind == "tempo" for a in song.ats)
    with_notes = sorted({e.track for e in compiled.events if e.kind == "note_on"})
    velocities = {e.data["vel"] for e in compiled.events if e.kind == "note_on"}
    events = canonical_json(compiled.events, compiled.track_names)
    meter_len = song.meter[0] * (WHOLE // song.meter[1])
    return {
        "bars": bars,
        "bars_by_length": compiled.end_tick // meter_len,
        "instruments": len(with_notes),
        "patterns": bool(re.search(r":\s*use\s", text) or re.search(r"\|\s*use\s", text)),
        "two_chord_bars": two_chord,
        "dynamics": len(velocities) >= 4,
        "tempo_change": tempo_change,
        "sections": len(played),
        "offsets": bool(re.search(r"\bo=[+-]?[1-9]", text)),
        "notes": sum(1 for e in compiled.events if e.kind == "note_on"),
        "loma_bytes": len(text.encode("utf-8")),
        "loma_lines": len(text.splitlines()),
        "midi_bytes": len(midi),
        "events_json_bytes": len(events.encode("utf-8")),
        "sha256": sha256(midi),
        "deterministic": all(sha256(compile_text(text)[1]) == sha256(midi) for _ in range(20)),
    }


def unmet(piece, facts):
    req, out = REQUIREMENTS.get(piece, {}), []
    if "bars" in req and facts["bars"] != req["bars"]:
        out.append("battute %d invece di %d" % (facts["bars"], req["bars"]))
    if "instruments" in req and not req["instruments"][0] <= facts["instruments"] <= req["instruments"][1]:
        out.append("strumenti %d" % facts["instruments"])
    if "sections" in req and facts["sections"] < req["sections"]:
        out.append("una sola sezione")
    for key, label in (("patterns", "nessun pattern"), ("two_chord_bars", "nessuna battuta con due accordi"),
                       ("dynamics", "dinamica piatta"), ("tempo_change", "nessun cambio di tempo"),
                       ("offsets", "nessun micro-timing")):
        if req.get(key) and not facts[key]:
            out.append(label)
    return out


def evaluate(model, piece, paths):
    attempts = []
    for path in paths:
        with open(path, "rb") as f:
            raw = f.read()
        try:
            text = raw.decode("utf-8")
            compile_text(text)
            attempts.append({"file": os.path.basename(path), "errors": []})
        except UnicodeDecodeError:
            attempts.append({"file": os.path.basename(path), "errors": [{"code": "E001", "line": 1}]})
        except LomaErrors as e:
            attempts.append({"file": os.path.basename(path), "errors": [{"code": x.code, "line": x.line} for x in e.errors]})
    result = {"model": model, "piece": piece, "attempts": len(attempts), "attempt_details": attempts,
              "valid_at_first_attempt": not attempts[0]["errors"], "final_valid": not attempts[-1]["errors"]}
    if result["final_valid"]:
        with open(paths[-1], "rb") as f:
            facts = analyse(f.read().decode("utf-8"))
        result.update(facts)
        result["unmet_requirements"] = unmet(piece, facts)
    return result


def report(results):
    lines = ["# Risultati dell'esperimento LOMA", "",
             "Generato da `experiment/run_experiment.py`. Le colonne *Fedeltà* e *Ascolto* vanno compilate da una persona.", "",
             "| Modello | Brano | Tentativi | Valido al primo | Valido alla fine | Battute | Strumenti | Note | LOMA (byte) | MIDI (byte) | Eventi JSON (byte) | Stessi byte su 20 compilazioni | Consegna | Fedeltà | Ascolto |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        if r["final_valid"]:
            consegna = "rispettata" if not r["unmet_requirements"] else "; ".join(r["unmet_requirements"])
            lines.append("| %s | %s | %d | %s | sì | %d | %d | %d | %d | %d | %d | %s | %s | da valutare | da valutare |" % (
                r["model"], r["piece"], r["attempts"], "sì" if r["valid_at_first_attempt"] else "no", r["bars"],
                r["instruments"], r["notes"], r["loma_bytes"], r["midi_bytes"], r["events_json_bytes"],
                "sì" if r["deterministic"] else "NO", consegna))
        else:
            lines.append("| %s | %s | %d | no | no | | | | | | | | | | |" % (r["model"], r["piece"], r["attempts"]))
    counts = {}
    for r in results:
        for a in r["attempt_details"]:
            for e in a["errors"]:
                counts[e["code"]] = counts.get(e["code"], 0) + 1
    lines += ["", "## Errori più frequenti", ""]
    if counts:
        lines += ["| Codice | Occorrenze |", "|---|---|"]
        lines += ["| %s | %d |" % (code, n) for code, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    else:
        lines.append("Nessun errore in nessun tentativo.")
    models = sorted({r["model"] for r in results})
    lines += ["", "## Copertura", "",
              "Modelli presenti: %s." % (", ".join(models) if models else "nessuno")]
    if models == ["reference"]:
        lines.append("")
        lines.append("Sono presenti solo i brani `reference`, scritti dall'autore della specifica e del compilatore: "
                     "non sono una misura indipendente. L'esperimento è completo quando ci sono i brani di altri modelli, "
                     "scritti partendo solo da `experiment/prompt.md`.")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="LOMA experiment report")
    ap.add_argument("--submissions", default=os.path.join(HERE, "submissions"))
    ap.add_argument("--no-write", action="store_true", help="print only, do not write results.md and results.json")
    args = ap.parse_args()
    results = []
    for model_dir in sorted(glob.glob(os.path.join(args.submissions, "*"))):
        if not os.path.isdir(model_dir):
            continue
        for piece_dir in sorted(glob.glob(os.path.join(model_dir, "*"))):
            paths = sorted(glob.glob(os.path.join(piece_dir, "attempt*.loma")), key=attempt_number)
            if paths:
                results.append(evaluate(os.path.basename(model_dir), os.path.basename(piece_dir), paths))
    text = report(results)
    sys.stdout.write(text)
    if not args.no_write:
        with open(os.path.join(HERE, "results.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        with open(os.path.join(HERE, "results.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
