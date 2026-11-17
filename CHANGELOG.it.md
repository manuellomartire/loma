# Changelog

*[English](CHANGELOG.md) · Italiano*

Le versioni del linguaggio sono cumulative: un file valido in una versione produce gli stessi byte se dichiara una versione successiva. Il compilatore accetta `loma 0.1`, `0.2`, `0.3`, `1.0` e `1.1`.

## 1.1 (compilatore 1.2.0)

Linguaggio:

- **Cambi di metro.** Opzione di battuta `meter=N/D`: il metro cambia da quella battuta alla fine della sua sezione. Ogni sezione comincia nel metro dell'intestazione, quindi la lunghezza di una battuta dipende solo dal testo della sua sezione.
- **Cambi di tonalità.** Opzione di battuta `key=K`, con la stessa validità. Scrive una Key Signature e non cambia le note.
- **Più voci su un track.** Un track può avere più linee in una battuta: ogni linea è una voce indipendente che riempie la battuta per conto suo. Le legature restano dentro una voce; duplicati e sovrapposizioni si controllano fra tutte le voci.
- `at TICK meter=N/D` e `at TICK key=K`, usati da `loma decompile` per conservare le indicazioni di un file MIDI.
- Nuovi tipi di evento `meter` e `key` nel JSON canonico, ordinati prima di `tempo` nello stesso tick.
- I file che dichiarano `loma 1.0` o precedenti producono gli stessi byte di prima.

Strumenti:

- Suite di conformità: 7 nuovi casi validi (`5xx`) e 10 nuovi casi di errore.
- `loma decompile` conserva i cambi di metro e di tonalità (dichiara `loma 1.1` solo quando il file ne ha).
- La consegna per le AI insegna `loma 1.1` ed è più esplicita sugli sbagli visti nei primi brani scritti da altri modelli (battute con due accordi, `|`, lunghezza dei pattern).
- Nuovo esempio `examples/carillon.loma`; primi brani di altri modelli in `experiment/submissions/`.

## Compilatore 1.1.0 (linguaggio 1.0)

I byte prodotti dai file validi non cambiano. Cambia quali errori vengono riportati per i file non validi.

- **Errori in un solo giro.** Gli errori di sintassi e i controlli di battuta sulle righe leggibili sono riportati insieme (prima gli errori di contenuto comparivano solo dopo aver corretto tutta la sintassi). Le regole sono in SPEC §13.1; legature, note duplicate e limiti restano controllati solo su un file sintatticamente pulito.
- **Suggerimenti.** Un nome scritto male propone quello giusto: `unknown chord 'Cmaj'. Did you mean 'C'?`, e lo stesso per track, pattern, swing, voicing, sezioni, nomi di batteria e comandi. Nel JSON il campo è `did_you_mean`.
- Una linea di track senza `:` dopo il nome ha un messaggio che lo dice.
- Suite di conformità: 7 nuovi casi `X_mixed_*`; `X_syntax_before_semantics` è diventato `X_syntax_and_semantics`; cambia l'elenco atteso di `E007_tuplets`.
- Playground: pulsante Compila (o Ctrl/⌘+Invio) invece della compilazione mentre si scrive, link al repository e alla specifica, link condivisibile del brano, "copia gli errori", pulsante per il tema chiaro o scuro, anteprima per i social.
- Documentazione in inglese e in italiano per changelog, suite di conformità, esperimento e consegna per le AI. Il rapporto dell'esperimento è in inglese.
- Test su Linux, Windows e macOS; `.gitattributes` per mantenere i byte dei file della suite su ogni sistema.

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
