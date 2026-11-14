# LOMA

*[English](README.md) · Italiano*

LOMA è un linguaggio testuale per descrivere musica, pensato per essere **scritto da un'AI** e **compilato in modo deterministico in un file MIDI**: lo stesso file `.loma` produce lo stesso `.mid`, byte per byte, ogni volta e con qualsiasi compilatore conforme.

- Specifica completa: [SPEC.it.md](SPEC.it.md) (italiano), [SPEC.md](SPEC.md) (inglese)
- Grammatica formale: [spec/grammar.ebnf](spec/grammar.ebnf)
- Novità per versione: [CHANGELOG.it.md](CHANGELOG.it.md)
- Playground: https://manuellomartire.github.io/loma/

## Un esempio

```loma
loma 1.0
title "Primo esempio"
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

L'AI scrive le intenzioni (accordo `Cm`, la sinistra fa l'arpeggio, la melodia cresce da 70 a 88); il compilatore le espande in note a tick interi. `/8` è una croma, `r` una pausa, `{o=-6}` un anticipo di 6 tick, `x2` ripete la sezione.

## Playground

Provalo online: **https://manuellomartire.github.io/loma/**

`docs/index.html` è una pagina web che gira tutta nel browser: incolli o modifichi il LOMA, premi Compila (o Ctrl/⌘+Invio), leggi gli errori accanto alle righe (e li copi per l'AI che ha scritto il file), ascolti il risultato su un piano roll, scarichi il file MIDI, apri un file `.mid` per trasformarlo in LOMA, oppure copi un link che contiene il brano. Contiene il compilatore JavaScript, quindi non serve un server. È pubblicata con GitHub Pages: in un fork scegli la cartella `docs` del ramo principale nelle impostazioni del repository.

Il suono viene da un piccolo sintetizzatore dentro la pagina, non da strumenti veri. Dopo aver cambiato `js/loma.js`, gli esempi o `docs/playground.src.html`, ricostruisci la pagina con `python3 tools/build_web.py`.

## Uso

Serve Python 3.9 o successivo, senza dipendenze. I test girano su Linux, Windows e macOS; la seconda implementazione richiede Node.js 18 o successivo.

```
python3 -m loma compile brano.loma -o brano.mid     # compila
python3 -m loma check brano.loma --json             # solo validazione, errori in JSON
python3 -m loma expand brano.loma --json            # eventi in tick, JSON canonico
python3 -m loma hash brano.loma                     # SHA-256 del MIDI
python3 -m loma test-determinism brano.loma         # compila 100 volte e confronta
python3 -m loma decompile brano.mid -o brano.loma   # da MIDI a LOMA
```

Con `pip install .` il comando diventa `loma`. Il nome del file può essere `-` per leggere dallo standard input. Stato di uscita: 0 riuscito, 1 errori nel file, 2 problema d'uso o di lettura.

Un errore dice dove e cosa correggere, e un nome scritto male propone quello giusto. Gli errori di sintassi e quelli di battuta sono riportati nello stesso giro, così un'AI può correggerli tutti insieme:

```
E005 line 9: unknown chord 'Cmaj'. Did you mean 'C'?
E003 line 14 bar 2 (Ab) track RH: bar length mismatch. Expected 1920 ticks, got 1680. Missing 240 ticks (= /8).
```

## Cosa contiene

| Cartella | Contenuto |
|---|---|
| `loma/` | Compilatore di riferimento in Python: parser, espansione, eventi, scrittura MIDI, decompilatore, riga di comando |
| `js/` | Seconda implementazione in JavaScript (Node.js e browser), usata per verificare la conformità |
| `docs/` | La pagina web del playground: `index.html` è autosufficiente e si può servire con GitHub Pages |
| `conformance/` | Suite di conformità: 95 file validi con i byte attesi, 116 file con gli errori attesi, e il programma che li confronta |
| `spec/` | Grammatica EBNF |
| `tests/` | Test automatici |
| `tools/` | Rigenerazione della suite, confronto su file casuali fra le due implementazioni, costruzione della pagina web |
| `examples/` | Brani di esempio, compreso `showcase.loma` che usa ogni costrutto |
| `experiment/` | Materiale per l'esperimento con più AI: consegna, raccolta dei file, misure |
| `editors/vscode/` | Evidenziazione della sintassi per Visual Studio Code |

## Verifiche

```
python3 -m unittest discover -s tests                       # tutti i test
python3 conformance/run.py --cmd "python3 -m loma"          # suite sul compilatore Python
python3 conformance/run.py --cmd "node js/loma.js"          # suite sul compilatore JavaScript
python3 tools/fuzz_compare.py --count 5000                  # file casuali: Python e JavaScript a confronto
```

Che cosa è verificato:

- **Stessi byte da due implementazioni.** Il compilatore Python e quello JavaScript producono gli stessi eventi e gli stessi byte su tutti i 211 casi della suite e su migliaia di file generati a caso, validi e non.
- **Byte calcolati a mano.** Il file minimo di [SPEC.it.md §16.1](SPEC.it.md#161-esempio-con-i-byte-attesi) è stato calcolato a mano dalla specifica e coincide con l'output.
- **Andata e ritorno.** Ogni MIDI della suite, decompilato e ricompilato, torna identico.

Che cosa **non** è verificato:

- Le due implementazioni hanno lo stesso autore. Un errore di interpretazione della specifica può essere presente in entrambe: la prova decisiva resta un compilatore scritto da un'altra persona partendo solo da `SPEC.it.md` o `SPEC.md`.
- Nessuno ha ancora ascoltato i brani di esempio con criterio: LOMA garantisce che il MIDI sia sempre lo stesso, non che suoni bene.
- L'esperimento con più AI (`experiment/`) ha per ora solo i tre brani scritti dall'autore della specifica.

## Scrivere LOMA con un'AI

[experiment/prompt.it.md](experiment/prompt.it.md) (italiano) e [experiment/prompt.md](experiment/prompt.md) (inglese) contengono un riferimento compatto del linguaggio e le consegne dei tre brani di prova, pronti da incollare. Il ciclo previsto è: l'AI scrive il file, `loma check --json` restituisce gli errori, l'AI corregge solo le righe indicate.

## Stato della roadmap

| Fase | Stato |
|---|---|
| 0.1 — nucleo deterministico | Fatto |
| 0.1 — grammatica EBNF e seconda implementazione | Fatto (stesso autore) |
| 0.1 — esperimento con le AI | Strumenti pronti; mancano i brani scritti da altri modelli |
| 0.2 — espressività e varietà | Fatto |
| 0.3 — armonia avanzata | Fatto |
| 1.0 — specifica stabile, documentazione, suite pubblica | Fatto |
| Da MIDI a LOMA, testi cantati, evidenziazione della sintassi | Fatto |
| Compilatore 1.1 — errori in un solo giro, suggerimenti, link nel playground | Fatto |

## Contribuire

Una modifica deve conservare i byte: lancia i test prima di aprire una pull request. Rigenerare i file attesi della suite (`tools/make_conformance.py`) è un cambiamento della specifica e va fatto di proposito.

## Licenza

MIT, vedi [LICENSE](LICENSE).
