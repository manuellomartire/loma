# Consegna per l'esperimento LOMA

*[English](prompt.md) · Italiano*

Incolla tutto questo testo a un'AI. Non aggiungere altro: l'esperimento misura quanto il linguaggio è facile da scrivere partendo solo da queste istruzioni.

---

Devi scrivere musica nel linguaggio LOMA 1.0. Un compilatore trasformerà il tuo file in MIDI. Rispondi solo con il file, dentro un blocco di codice, senza spiegazioni.

## Riferimento rapido

```loma
loma 1.1
title "Titolo"
tempo 96
meter 4/4
key Am

track Mel ch=1 program=73
track Pno ch=2 program=0
track Kit drums

pattern arp base=3 dur=/8 : 1 3 5 3 1 3 5 3
pattern arpB from arp : 8=8
pattern meta base=3 dur=/8 : 1 5 8 5
swing lieve grid=/8 : 0 12
voicing aperto base=3 : 1 5 10

section a
  bar Am
    Mel{v=80}: A4/4 C5/8 B4/8 A4/2{a=leg}
    Pno{v=56 swing=lieve}: use arp
    Kit{v=64}: kick/4 hat/4 snare/4 hat/8 hat/8
  bar F G
    Mel{v=70>90}: C5/2 | D5/4. B4/8{o=-6}
    Pno{v=56}: use meta | *aperto/2
    Kit{v=64}: kick/4 hat/4 | snare/4 hat/4
end

section fine
  bar Am tempo=96>70
    Mel{v=64}: pedal+ [A4 C5 E5]/1{a=leg} pedal-
    Pno{v=50}: use arpB
    Pno{v=40}: A1/1
    Kit{v=50}: crash/1
end

section valzer
  bar Dm meter=3/4 key=Dm
    Mel{v=72}: D5/2 F5/4
    Pno{v=50}: D3/4 [F3 A3]/4 [F3 A3]/4
    Kit{v=50}: kick/4 hat/4 hat/4
end

play a x2
play valzer x2
play fine
```

Regole:

1. **Intestazione.** Prima riga `loma 1.1`. Poi `tempo` (BPM), `meter`, `key`, e un `track` per strumento: `track NOME ch=N program=P` (canale 1–16 escluso 10, uno per track; `program` è lo strumento General MIDI 0–127) oppure `track NOME drums`.
2. **Durate.** `/1` = 1920 tick, `/2` = 960, `/4` = 480, `/8` = 240, `/16` = 120. Puntata: `/4.` = 720, `/8.` = 360. Terzina: `/8t` = 160, `/4t` = 320. Quintina: `/8q` = 192. Tick esatti: `/#100`.
3. **Note.** `C4/4` (C4 = Do centrale), pausa `r/4`, accordo `[C4 E4 G4]/2`, legatura `C4/2~ C4/4` (stessa altezza, la seconda nota senza attributi). Batteria: `kick snare hat ohat crash ride tom1 tom2`.
4. **Ogni linea deve riempire esattamente la battuta**: in 4/4 la somma è 1920 tick, in 3/4 è 1440. Somma le durate prima di rispondere. Due linee dello stesso track in una battuta sono due voci indipendenti (melodia e basso di un pianoforte, per esempio): ognuna riempie la battuta per conto suo.
5. **Attributi** tra graffe dopo la nota: `v=` velocity 1–127 (mai 0), `o=` anticipo o ritardo in tick, `a=leg|norm|stac`, `d=` durata sonora in tick. Dopo il nome del track valgono per tutta la linea: `Mel{v=80}: ...`. Sulla linea puoi scrivere anche una rampa `v=60>90` e `swing=NOME`.
6. **Accordi della battuta.** `bar Am`, `bar F G` (due accordi: metà battuta ciascuno, 960 tick in 4/4). Qualità: maggiore, `m`, `7`, `maj7`, `m7`, `dim`, `aug`, `sus2`, `sus4`, `6`, `9`, `maj9`, `m9`, `add9`, `m7b5`, `dim7`, `13`. Basso: `C/E`.
7. **Pattern.** I numeri sono le note dell'accordo: `1` la prima, `3` la seconda, `5` la terza, `7` la quarta (solo sugli accordi di quattro note), `8 10 12` le stesse un'ottava sopra, `0` il basso. `(1 5)` suona più toni insieme, `r` è una pausa. `use NOME` occupa l'intera linea o l'intero segmento e si ripete fino a riempire **ogni accordo**: la lunghezza del pattern deve dividere esattamente la durata dell'accordo (un pattern di 1920 tick non entra in un accordo di 960: in `bar F G` usane uno più corto). I pattern non si usano sulla batteria.
8. **Segmenti.** In una battuta con più accordi puoi separare le parti con `|`: esattamente tante parti quanti accordi, e ogni parte riempie solo la sua porzione (960 tick ciascuna in `bar F G`). Non usare mai `|` in una battuta con un solo accordo.
9. **Controlli**, senza durata: `pedal+` `pedal-`, `cc7=100`, `bend=0`, rampe `cc11=40>100/1`.
10. **Struttura.** `section NOME ... end`, dentro una sezione `repeat N ... end`, poi `play NOME`, `play NOME x2`, `play NOME transpose=+2`. Cambio di tempo: `bar Am tempo=80`, rallentando `bar Am tempo=96>70`. Cambio di metro o di tonalità: `bar Dm meter=3/4 key=Dm`, valido da quella battuta alla fine della sua sezione; ogni sezione ricomincia nel metro e nella tonalità dell'intestazione.
11. Un commento inizia con `#` dopo uno spazio. I nomi sono lettere, cifre e `_`.
12. Niente casualità: se vuoi una variazione, scrivila. Scrivi l'espressività: velocity diverse per melodia e accompagnamento, qualche `o=`, `a=leg` o `a=stac` dove serve.

Se ricevi un elenco di errori, correggi solo le righe indicate e rispondi di nuovo con il file completo.

## I tre brani

Scrivi tre file separati, con melodie originali.

**Brano 1.** 8 battute, pianoforte solo, melodia e accompagnamento, una sola tonalità.

**Brano 2.** 16 battute, tre strumenti, con pattern, ripetizioni e variazioni dinamiche, e almeno alcune battute con due accordi.

**Brano 3.** 32 battute, quattro o cinque strumenti, almeno un cambio di tempo, articolazioni e micro-timing (`o=`), struttura in più sezioni.
