# Suite di conformità di LOMA 1.0

*[English](README.md) · Italiano*

Questa cartella è la definizione operativa di "compilatore conforme" ([SPEC.it.md §2 e §17](../SPEC.it.md#2-conformità)). Serve a chi scrive un compilatore LOMA in qualsiasi linguaggio.

## Contenuto

- `valid/NOME.loma`: un file valido, con
  - `NOME.mid`: i byte MIDI attesi;
  - `NOME.events.json`: gli eventi attesi in JSON canonico;
  - `NOME.sha256`: lo SHA-256 del MIDI.
- `errors/NOME.loma`: un file non valido, con
  - `NOME.errors.json`: l'elenco atteso di `{"code", "line"}`, nell'ordine in cui vanno riportati.
- `run.py`: il programma di verifica.

I nomi dei casi validi iniziano con un numero: `0xx` linguaggio 0.1, `2xx` 0.2, `3xx` 0.3, `4xx` 1.0. I casi di errore iniziano con il codice che verificano; quelli che iniziano con `X_` controllano l'ordine degli errori e l'assenza di errori a cascata, e quelli `X_mixed_` i file che hanno insieme errori di sintassi e di contenuto (SPEC §13.1).

## Uso

Il compilatore da verificare deve offrire tre comandi:

```
CMD compile FILE -o OUT        stato 0, scrive il MIDI
CMD expand FILE --json         stato 0, JSON canonico sullo standard output
CMD check FILE --json          stato 1 se ci sono errori, array JSON di errori sullo standard output
```

```
python3 conformance/run.py --cmd "python3 -m loma"
python3 conformance/run.py --cmd "node js/loma.js"
python3 conformance/run.py --cmd "./mio-compilatore" --first-error-only
```

Con `--first-error-only` nei file non validi si confronta solo il primo errore: è il minimo che la specifica richiede (MUST). Senza l'opzione si confronta l'elenco completo (SHOULD).

## Origine dei file attesi

I file attesi sono generati dal compilatore di riferimento con `tools/make_conformance.py`. Due eccezioni danno alla suite un punto fermo indipendente dal compilatore:

- `valid/010_minimal.mid` coincide con i byte calcolati a mano in SPEC.it.md §16.1;
- i valori di tempo di `valid/020_tempo_ramp` (100, 92, 85, 77, 70 BPM) e delle rampe di controller sono verificati a mano nei test.

Gli hash dei casi che esistevano già nella 0.1 sono fissati nei test: non possono cambiare.

Rigenerare i file attesi è un cambiamento della specifica: va fatto solo di proposito.
