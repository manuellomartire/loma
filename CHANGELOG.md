# Changelog

Le versioni del linguaggio sono cumulative: un file valido in una versione produce gli stessi byte se dichiara una versione successiva. Il compilatore 1.0 accetta `loma 0.1`, `0.2`, `0.3` e `1.0`.

## 1.0

Linguaggio:

- Testi cantati: `"testo"` nel contenuto di una linea (meta-evento Lyric).
- Altezze numeriche `mN`, valide su ogni track.
- `at` con `ccN=V`, `bend=V`, `"testo"` e `tempo=BPM`.
- Numeri limitati a 9 cifre (`E018`).
- Parole riservate non usabili come nomi (`E019`).
- Solo spazio e tab sono spazi; solo cifre ASCII sono numeri.
- Nuovi errori: `E020` (costrutto di una versione successiva), `E021` (numero di segmenti).
- Limite di 100000 battute e di 1000000 eventi di controllo dopo l'espansione.

Strumenti:

- `loma decompile`: da MIDI a LOMA, senza perdite per i file prodotti da LOMA.
- Lettura dallo standard input con `-`.
- Seconda implementazione in JavaScript (`js/loma.js`).
- Suite di conformità pubblica (`conformance/`) con il suo programma di verifica.
- Confronto su file casuali fra le due implementazioni (`tools/fuzz_compare.py`).
- Grammatica EBNF (`spec/grammar.ebnf`), specifica in italiano e in inglese.
- Evidenziazione della sintassi per Visual Studio Code.
- Playground web (`docs/index.html`): editor, errori, riproduzione su piano roll, conversione fra LOMA e MIDI nei due sensi, tutto nel browser.
- Il compilatore JavaScript funziona anche nel browser e ha il suo decompilatore (`node js/loma.js decompile`).

## 0.3

- Accordi estesi: `5 6 m6 dim7 m7b5 mmaj7 7sus4 7b9 7#9 add9 madd9 9 maj9 m9 11 m11 13`.
- Inversioni `^K` e basso `/X`.
- Toni `0` (basso), `9`, `11`, `16`, `18`; segni d'ottava `+` e `-`.
- `voicing` e `*NOME` nel contenuto di una linea.

## 0.2

- Control change `ccN=V`, pitch bend `bend=V`, rampe `A>B/D`.
- Rampa di velocity di linea `v=N>M`.
- `swing` come tabella esplicita di offset.
- Contenuto di una linea su più righe.
- Segmenti `|`: contenuti diversi per ogni accordo della battuta.
- Elenchi di pattern `use A,B` e varianti `pattern ... from`.
- Quintine `q` e gruppi irregolari `xA/B`.
- Blocchi `repeat` annidabili.

## 0.1

- Note, pause, accordi, legature, attributi `v o d a`, pedale, batteria.
- Pattern adattivi sull'accordo, sezioni, `play`, trasposizione, `at` per le note.
- Cambi di tempo e rampe di tempo.
- MIDI canonico, ordinamento degli eventi, JSON canonico, errori `E001`–`E019`.

Differenze di comportamento rispetto al primo compilatore 0.1, tutte su file non validi: gli errori sono sempre ordinati per riga; un'intestazione sbagliata viene riportata da sola; un'istruzione globale dentro una sezione viene segnalata una volta sola. I byte prodotti dai file validi non sono cambiati.
