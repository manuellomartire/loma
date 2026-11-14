# Risultati dell'esperimento LOMA

Generato da `experiment/run_experiment.py`. Le colonne *Fedeltà* e *Ascolto* vanno compilate da una persona.

| Modello | Brano | Tentativi | Valido al primo | Valido alla fine | Battute | Strumenti | Note | LOMA (byte) | MIDI (byte) | Eventi JSON (byte) | Stessi byte su 20 compilazioni | Consegna | Fedeltà | Ascolto |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| reference | brano1 | 1 | sì | sì | 8 | 2 | 88 | 873 | 917 | 12151 | sì | rispettata | da valutare | da valutare |
| reference | brano2 | 1 | sì | sì | 16 | 3 | 303 | 2062 | 2854 | 43287 | sì | rispettata | da valutare | da valutare |
| reference | brano3 | 1 | sì | sì | 32 | 5 | 746 | 4748 | 9094 | 148719 | sì | rispettata | da valutare | da valutare |

## Errori più frequenti

Nessun errore in nessun tentativo.

## Copertura

Modelli presenti: reference.

Sono presenti solo i brani `reference`, scritti dall'autore della specifica e del compilatore: non sono una misura indipendente. L'esperimento è completo quando ci sono i brani di altri modelli, scritti partendo solo da `experiment/prompt.md` o `experiment/prompt.it.md`.
