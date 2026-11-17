# LOMA 1.1 — Specifica del linguaggio

Versione del linguaggio: **1.1**. Estensione dei file: `.loma`. Versione inglese: [SPEC.md](SPEC.md). Se i due testi non coincidono, decide la suite di conformità.

LOMA è un linguaggio testuale per descrivere musica, pensato per essere scritto da un'AI e compilato in modo deterministico in un file MIDI: lo stesso file `.loma` produce lo stesso `.mid`, byte per byte, con qualsiasi compilatore conforme.

## Indice

1. [Principi](#1-principi)
2. [Conformità](#2-conformità)
3. [Aritmetica](#3-aritmetica)
4. [Struttura del testo](#4-struttura-del-testo)
5. [Istruzioni globali](#5-istruzioni-globali)
6. [Altezze e durate](#6-altezze-e-durate)
7. [Contenuto di una linea](#7-contenuto-di-una-linea)
8. [Accordi e toni](#8-accordi-e-toni)
9. [Pattern, swing, voicing](#9-pattern-swing-voicing)
10. [Sezioni e battute](#10-sezioni-e-battute)
11. [Esecuzione: `play` e `at`](#11-esecuzione-play-e-at)
12. [Limiti](#12-limiti)
13. [Errori](#13-errori)
14. [Risoluzione delle note](#14-risoluzione-delle-note)
15. [Eventi: ordine e JSON canonico](#15-eventi-ordine-e-json-canonico)
16. [MIDI canonico](#16-midi-canonico)
17. [Riga di comando e suite di conformità](#17-riga-di-comando-e-suite-di-conformità)
18. [Versioni del linguaggio](#18-versioni-del-linguaggio)
19. [Esempio completo](#19-esempio-completo)

La grammatica formale è in [spec/grammar.ebnf](spec/grammar.ebnf).

---

## 1. Principi

1. **Deterministico.** Nessuna casualità, nessun numero in virgola mobile, nessun dato che dipenda da data, sistema o versione del compilatore.
2. **Scritto, non calcolato.** L'espressività (anticipi, ritardi, dinamica) è scritta nel file. Il compilatore non inventa nulla: applica regole intere.
3. **Dichiarativo e limitato.** Pochi comandi, sintassi regolare, niente `if`, niente cicli liberi, niente `random`.
4. **Errori leggibili da un'AI.** Ogni errore ha codice, riga, causa e valore atteso.
5. **Due livelli.** Il livello *strutturale* (accordi, battute, pattern, sezioni) sta sopra il livello *espressivo* (velocity, micro-timing, articolazione, controlli).

LOMA **non** genera audio (il suono dipende dal sintetizzatore che esegue il MIDI), **non** compone e **non** garantisce la qualità musicale: garantisce che una descrizione produca sempre lo stesso MIDI.

## 2. Conformità

Le parole **MUST**, **SHOULD** e **MAY** hanno il significato della RFC 2119. Dove il testo dice "deve" senza maiuscole, vale come MUST.

Un compilatore è **conforme** se:

- per ogni file valido produce esattamente gli eventi (§15) e i byte MIDI (§16) definiti qui (MUST);
- per ogni file non valido rifiuta il file e riporta come **primo** errore lo stesso codice e la stessa riga del compilatore di riferimento (MUST); l'elenco completo degli errori SHOULD coincidere;
- supera la suite in `conformance/` (§17).

La definizione operativa di conformità è la suite: due compilatori indipendenti devono produrre gli stessi byte dagli stessi file.

## 3. Aritmetica

Tutti i calcoli sono su **interi**. Con i limiti di §12 ogni valore intermedio sta in un intero a 64 bit con segno (e sotto 2^53).

**`floor_div(a, b)`** è ⌊a / b⌋, la divisione arrotondata verso −∞, per qualsiasi segno. Tutte le divisioni di questa specifica scritte `//` sono `floor_div`.

| Espressione | `floor_div` (MUST) | Troncamento verso zero (NON conforme) |
|---|---|---|
| `7 // 3` | 2 | 2 |
| `-7 // 3` | -3 | -2 |
| `7 // -3` | -3 | -2 |
| `-7 // -3` | 2 | 2 |

C, Java, Rust e JavaScript troncano verso zero: chi implementa in questi linguaggi deve scrivere `floor_div` a mano. Dove la specifica richiede un risultato esatto (durate, divisione di una battuta fra accordi) il compilatore dà errore invece di arrotondare.

Risoluzione: **480 tick per semiminima** (PPQ), non configurabile. Una semibreve vale 1920 tick.

## 4. Struttura del testo

- **Codifica**: UTF-8. Un BOM iniziale è ignorato. Un file che non è UTF-8 valido dà `E001` alla riga 1.
- **Righe**: terminate da LF o CR LF.
- **Spazi**: solo SPAZIO e TAB. Altri caratteri di spaziatura Unicode non separano nulla e danno errore. L'indentazione è libera.
- **Commenti**: `#` inizia un commento solo a inizio riga o dopo uno spazio, e mai dentro le virgolette. Quindi `F#3` è un'altezza e `"a # b"` è un testo.
- **Numeri**: solo cifre ASCII `0`–`9`, al massimo 9 cifre (altrimenti `E018`).
- **Nomi** (track, pattern, swing, voicing, sezioni): una lettera ASCII seguita da lettere, cifre o `_`. Ogni categoria ha il proprio spazio dei nomi; dentro una categoria i nomi sono unici (`E019`).
- **Parole riservate**, non usabili come nomi (`E019`): `loma title tempo meter key track pattern swing voicing section play at bar end repeat use from r pedal bend drums`.
- Le righe vuote sono ignorate. Ogni istruzione sta su una riga, tranne il contenuto di una linea di track che può continuare (§10.3).

La prima riga non vuota deve essere `loma VERSIONE` con versione `0.1`, `0.2`, `0.3` o `1.0`. Se manca o è sbagliata, il compilatore riporta solo quell'errore. La versione dichiarata decide quali costrutti sono ammessi (§18): usarne uno più recente dà `E020`.

## 5. Istruzioni globali

Dopo l'intestazione, le istruzioni globali possono comparire in qualsiasi ordine, fuori dalle sezioni.

```
loma 1.0
title "Nome brano"
tempo 100
meter 4/4
key Cm
track RH ch=1 program=0
track Kit drums
```

| Istruzione | Regole | Default |
|---|---|---|
| `title "TESTO"` | Al massimo una. Il testo non contiene `"`. | nessun titolo |
| `tempo N` | Al massimo una. BPM in **semiminime** al minuto, intero 4–400 (`E015`). | 120 |
| `meter N/D` | Al massimo una. N da 1 a 64, D in 1, 2, 4, 8, 16, 32, 64 (`E018`). Dalla 1.1 una battuta può cambiarlo (§10.2). | 4/4 |
| `key K` | Al massimo una. Non cambia le note: viene scritta nel MIDI come Key Signature. Tonalità valide in §16 (`E013`). Dalla 1.1 una battuta può cambiarla (§10.2). | nessuna |
| `track NOME ch=N [program=P]` | Canale 1–16 escluso 10, esclusivo per ogni track (`E011`). Program 0–127. | program 0 |
| `track NOME drums` | Batteria sul canale 10; al massimo una (`E011`). Nessuna opzione. | |

Ripetere `title`, `tempo`, `meter` o `key` dà `E001`. Un track deve essere dichiarato **prima** della riga che lo usa (`E008`). L'ordine di dichiarazione dei track è l'ordine dei track nel file MIDI. Pattern, swing, voicing e sezioni possono essere usati prima della loro definizione, tranne la sorgente di `pattern ... from` (§9.2).

## 6. Altezze e durate

### 6.1 Altezze

`C4` è il Do centrale, MIDI 60. Valore: `12 * (ottava + 1) + semitono + alterazione`, con C=0, D=2, E=4, F=5, G=7, A=9, B=11, `#` = +1, `b` = −1. L'ottava può essere negativa (`C-1` = 0). Il risultato deve essere 0–127 (`E006`).

Dalla 1.0 un'altezza si può scrivere anche come numero MIDI: `m60`. Vale su ogni track.

Sui track `drums` si usano i nomi di percussione (o `mN`):

| Nome | MIDI | Nome | MIDI |
|---|---|---|---|
| `kick` | 36 | `crash` | 49 |
| `snare` | 38 | `ride` | 51 |
| `hat` | 42 | `tom1` | 50 |
| `ohat` | 46 | `tom2` | 47 |

Un nome di percussione su un track melodico, o un nome di nota su un track `drums`, dà `E001`.

### 6.2 Durate

Una durata è `/` seguito da un valore. È la **durata scritta**: quanto avanza il tempo.

| Scritto | Tick | Scritto | Tick | Scritto | Tick |
|---|---|---|---|---|---|
| `/1` | 1920 | `/2.` | 1440 | `/2t` | 640 |
| `/2` | 960 | `/4.` | 720 | `/4t` | 320 |
| `/4` | 480 | `/8.` | 360 | `/8t` | 160 |
| `/8` | 240 | `/16.` | 180 | `/16t` | 80 |
| `/16` | 120 | `/32.` | 90 | `/32t` | 40 |
| `/32` | 60 | `/64.` | 45 | `/64t` | 20 |
| `/64` | 30 | | | | |

Calcolo: `base = 1920 // n` con `n` in 1, 2, 4, 8, 16, 32, 64 (altrimenti `E007`); poi un solo suffisso opzionale:

| Suffisso | Significato | Formula |
|---|---|---|
| `.` | puntata | `base * 3 / 2` |
| `..` | doppia puntata | `base * 7 / 4` |
| `t` | terzina (3 nel tempo di 2) | `base * 2 / 3` |
| `q` | quintina (5 nel tempo di 4), dalla 0.2 | `base * 4 / 5` |
| `xA/B` | gruppo irregolare: A note nel tempo di B, dalla 0.2 | `base * B / A` |

Se il risultato non è intero (per esempio `/64..` o `/8x7/4`: 480 non è divisibile per 7) il compilatore dà `E007`. `/8q` vale 192 tick, `/16q` 96, `/4x5/4` 384.

Durata in tick esatti: `/#N`, con N ≥ 1 (`/#210` = 210 tick). Serve per tutto ciò che i valori musicali non coprono.

## 7. Contenuto di una linea

Il contenuto di una linea di track è una sequenza di elementi separati da spazi. Un **cursore** parte da 0 all'inizio della battuta (o del segmento, §10.4) e avanza della durata scritta di note, pause e accordi.

### 7.1 Note, pause, accordi

```
C4/4                 nota
r/4                  pausa
[C4 Eb4 G4]/2        accordo: note simultanee, stessa durata
*aperto/2            accordo corrente suonato con un voicing (§9.4)
```

Gli elementi devono essere separati da spazi (`C4/4C4/4` è `E001`).

### 7.2 Legature

`~` si scrive subito dopo la durata, prima delle graffe: `C4/2~ C4/4`, `C4/2~{v=80} C4/4`.

- La nota successiva dello stesso track (dalla 1.1: della stessa voce del track, §10.3) deve avere la **stessa altezza** e iniziare esattamente dove finisce questa. Per gli accordi: lo stesso insieme di altezze.
- La nota legata successiva **non può avere attributi propri** (né sull'elemento né sulle singole note).
- Velocity, offset e articolazione sono quelli della **prima** nota. La durata scritta della nota fusa è la somma delle durate.
- Una legatura può attraversare battute, segmenti, sezioni e blocchi `repeat`, ma non il confine fra due `play` diversi.
- Fra due note legate possono esserci controlli (§7.5) e testi, non pause.
- Non si legano le pause né le note di un track `drums`.

Ogni violazione dà `E012`, alla riga della nota che porta `~`.

### 7.3 Attributi

Tra graffe, subito dopo l'elemento: `Eb5/8{v=78 o=-6}`.

| Attributo | Significato | Default |
|---|---|---|
| `v=N` | velocity 1–127 | 80 |
| `o=N` | offset in tick, con segno: anticipo o ritardo | 0 |
| `d=N` | durata **sonora** in tick, N ≥ 1 | da `a=` |
| `a=` | articolazione: `leg` 100%, `norm` 90%, `stac` 50% della durata scritta | `norm` |

Gli attributi si possono scrivere a quattro livelli. Vince il più specifico:

**nota dentro un accordo > elemento > linea > default**

```
RH{v=50}: [C4 E4{v=70} G4]/2{v=60}      # C4 e G4 a 60, E4 a 70
```

Una pausa non ha attributi. Un attributo ripetuto nella stessa graffa vale l'ultimo.

**Durata scritta e durata sonora.** La durata scritta (`/8`) fa avanzare il cursore; la durata sonora dice per quanto la nota suona. Senza `d=`, la durata sonora è `max(1, scritta * pct // 100)`.

**Offset.** Sposta solo gli eventi MIDI della nota, non il cursore: `inizio = max(0, posizione + o)`, `fine = inizio + durata_sonora`. Gli offset possono creare sovrapposizioni fra note diverse; per la stessa altezza vale §14.

### 7.4 Attributi di linea (dalla 0.2)

Solo nelle graffe dopo il nome del track:

- **`v=N>M`**: rampa di velocity lungo la battuta. Una nota alla posizione `p` (tick dall'inizio della battuta, prima dell'offset) riceve `N + (M - N) * p // lunghezza_battuta`. È il valore di linea: `v=` sull'elemento o sulla nota lo sostituisce. Vale anche per le note di un pattern.
- **`swing=NOME`**: applica una tabella di swing (§9.3). L'offset della tabella si **somma** all'`o=` della nota.

### 7.5 Controlli

I controlli non hanno durata propria: scattano alla posizione del cursore e non lo spostano.

| Elemento | Evento | Da |
|---|---|---|
| `pedal+` / `pedal-` | controller 64 a 127 / 0. Non ammesso sui track `drums`. | 0.1 |
| `ccN=V` | control change N (0–127) con valore V (0–127) | 0.2 |
| `bend=V` | pitch bend, V da −8192 a 8191 (0 = centro) | 0.2 |
| `ccN=A>B/D`, `bend=A>B/D` | rampa lineare da A a B lungo la durata D | 0.2 |

**Rampa.** Con `inizio` = posizione del cursore e `len` = tick della durata D, gli eventi sono:

- uno ogni 60 tick: per `k = 0, 1, 2, ...` finché `k * 60 < len`, al tick `inizio + k * 60`, con valore `A + (B - A) * (k * 60) // len`;
- uno finale al tick `inizio + len`, con valore `B`.

Vengono emessi tutti, anche se due valori consecutivi coincidono. La rampa non sposta il cursore: scorre "sotto" le note che seguono e può superare la fine della battuta.

Esempio: `cc1=10>0/4` (len = 480) dà i valori 10, 8, 7, 6, 5, 3, 2, 1 ai tick 0, 60, ..., 420 e 0 al tick 480. Con il troncamento verso zero uscirebbero 9, 8, 7, 5, 4, 3, 2: non conforme.

### 7.6 Testi (dalla 1.0)

`"testo"` attacca un testo cantato (meta-evento Lyric) alla posizione del cursore, nel track della linea. Il testo non può essere vuoto né contenere `"`.

```
Voce: "Fra" C4/4 "Mar" D4/4 "ti" E4/4 "no" C4/4
```

## 8. Accordi e toni

Ogni battuta dichiara uno o più accordi. Un accordo serve ai pattern e ai voicing: non influenza le note scritte a mano.

### 8.1 Sigle

`FONDAMENTALE QUALITÀ [^INVERSIONE] [/BASSO]`, senza spazi. Fondamentale e basso sono una lettera `A`–`G` con eventuale `#` o `b`.

| Qualità | Intervalli | Qualità | Intervalli |
|---|---|---|---|
| (vuota) | 0 4 7 | `sus2` | 0 2 7 |
| `m` | 0 3 7 | `sus4` | 0 5 7 |
| `7` | 0 4 7 10 | `dim` | 0 3 6 |
| `maj7` | 0 4 7 11 | `aug` | 0 4 8 |
| `m7` | 0 3 7 10 | | |

Dalla 0.3:

| Qualità | Intervalli | Qualità | Intervalli |
|---|---|---|---|
| `5` | 0 7 | `add9` | 0 4 7 14 |
| `6` | 0 4 7 9 | `madd9` | 0 3 7 14 |
| `m6` | 0 3 7 9 | `9` | 0 4 7 10 14 |
| `dim7` | 0 3 6 9 | `maj9` | 0 4 7 11 14 |
| `m7b5` | 0 3 6 10 | `m9` | 0 3 7 10 14 |
| `mmaj7` | 0 3 7 11 | `11` | 0 4 7 10 14 17 |
| `7sus4` | 0 5 7 10 | `m11` | 0 3 7 10 14 17 |
| `7b9` | 0 4 7 10 13 | `13` | 0 4 7 10 14 21 |
| `7#9` | 0 4 7 10 15 | | |

Una sigla non riconosciuta dà `E005`.

### 8.2 Inversioni e basso (dalla 0.3)

- **`^K`**: inversione K. Le K note più basse salgono di un'ottava (`+12`), poi gli intervalli si riordinano in modo crescente. `C^1` ha intervalli 4 7 12; `C^2` 7 12 16. K deve essere minore del numero di note (`E005`).
- **`/BASSO`**: nota di basso (slash chord). Non cambia gli intervalli: definisce il tono `0`.

### 8.3 Toni

Pattern e voicing indicano le note dell'accordo con **numeri di tono**. Sono **indici ordinali** delle note dell'accordo in ordine crescente (dopo l'inversione), **non gradi della scala**: su `Csus4` il tono `3` è F.

| Tono | Nota |
|---|---|
| `1`, `3`, `5`, `7`, `9`, `11` | prima, seconda, ..., sesta nota dell'accordo |
| `8`, `10`, `12`, `14`, `16`, `18` | le stesse sei note un'ottava sopra |
| `0` | il basso (dalla 0.3) |

I toni `9`, `11`, `16`, `18` e `0` richiedono la 0.3. Dalla 0.3 un tono può avere **segni d'ottava**: ogni `+` alza di 12 semitoni, ogni `-` abbassa (`5-`, `1++`).

Con `base` = ottava indicata dal pattern o dal voicing, `pc(X)` = semitono della nota X più alterazione (quindi `pc(Cb)` = −1 e `pc(B#)` = 12):

- tono di indice `i`: `12 * (base + 1) + pc(fondamentale) + intervalli[i] + spostamento`;
- tono `0` con `/BASSO`: `12 * base + pc(basso) + spostamento` (la nota di basso nell'ottava `base − 1`);
- tono `0` senza `/BASSO`: `12 * base + pc(fondamentale) + intervalli[0] + spostamento` (la nota più bassa dell'accordo, un'ottava sotto).

Un numero di tono inesistente (`2`, `13`, `20`...) dà `E010` alla definizione. Un tono che l'accordo non ha (per esempio `7` su una triade) dà `E010` nella battuta che lo usa. Un'altezza fuori da 0–127 dà `E006`.

## 9. Pattern, swing, voicing

### 9.1 Pattern

```
pattern NOME base=OTTAVA dur=/DURATA : PASSO PASSO ...
```

- `base`: ottava della fondamentale, da −1 a 9 (`E006`). `dur`: durata di default dei passi. Le due opzioni possono stare in qualsiasi ordine.
- Un passo è un tono (`1`), una pausa (`r`) o un gruppo di toni simultanei (`(1 5 8)`), seguito da una durata propria opzionale (`1/4`) e da attributi opzionali (`1{v=70}`). Una pausa non ha attributi.
- La lunghezza del pattern è la somma delle durate dei passi.

```
pattern arp8 base=3 dur=/8 : 1 3 5 3 1 3 5 3
```

Su `Cm` suona C3 Eb3 G3 Eb3 C3 Eb3 G3 Eb3.

### 9.2 Varianti (dalla 0.2)

```
pattern NOME from ALTRO [base=OTTAVA] : INDICE=PASSO ...
```

Copia il pattern `ALTRO`, che deve essere già definito **prima** di questa riga (`E004`), e sostituisce i passi indicati (indici da 1). Un passo sostitutivo senza durata eredita la durata del passo che sostituisce. L'elenco dopo i due punti può essere vuoto. `base=` cambia l'ottava.

```
pattern arpB from arp8 : 4=8 8=r
```

### 9.3 Swing (dalla 0.2)

```
swing NOME grid=/DURATA : OFFSET OFFSET ...
```

Una tabella di offset in tick, con segno. Una linea con `swing=NOME` applica a ogni nota che cade sulla griglia l'offset `tabella[(p // grid) % lunghezza_tabella]`, dove `p` è la posizione della nota nella battuta. Le note che non cadono sulla griglia (`p % grid != 0`) non ricevono nulla.

```
swing shuffle grid=/8 : 0 40        # ritarda di 40 tick ogni ottavo in levare
```

### 9.4 Voicing (dalla 0.3)

```
voicing NOME base=OTTAVA : TONO TONO ...
```

Un modo di disporre l'accordo corrente. Nel contenuto di una linea melodica, `*NOME/DURATA` suona l'accordo attivo alla posizione del cursore con quei toni; accetta `~` e attributi come un accordo scritto a mano. Non è ammesso sui track `drums` (`E001`); un voicing non definito dà `E004`.

```
voicing aperto base=3 : 1 5 10
RH: *aperto/2 *aperto/2
```

### 9.5 Usare un pattern

```
LH: use arp8
LH: use arp8,arpB       # dalla 0.2
```

- `use` è l'intero contenuto di una linea o di un segmento: non si mescola con note scritte a mano (`E016`). Non è ammesso sui track `drums`.
- Il pattern viene ripetuto fino a riempire **ogni segmento di accordo** (§10.4), ripartendo da capo a ogni segmento con l'accordo di quel segmento.
- Con un elenco, i pattern si alternano ciclicamente: A, B, A, B...
- Il riempimento deve essere esatto: se un pattern supererebbe la fine del segmento, `E009`.
- Le note del pattern ricevono gli attributi della linea (comprese rampa e swing) e poi quelli del passo.

## 10. Sezioni e battute

### 10.1 Sezioni

```
section NOME
  bar ...
  ...
end
```

Una sezione è una sequenza di battute e di blocchi `repeat`. Una sezione mai eseguita viene comunque validata.

### 10.2 Battute

```
bar ACCORDO [ACCORDO ...] [len=/D] [tempo=N | tempo=N>M] [meter=N/D] [key=K]
```

- Almeno un accordo. Accordi e opzioni possono stare in qualsiasi ordine.
- **Lunghezza**: `numeratore * (1920 // denominatore)` dal metro in vigore (4/4 = 1920, 3/4 = 1440, 6/8 = 1440), oppure `len=/D` per battute irregolari e anacrusi.
- **`tempo=N`**: cambio di tempo all'inizio della battuta.
- **`tempo=N>M`**: rallentando o accelerando lineare che arriva a `M` alla fine della battuta. Eventi: uno ogni 480 tick, per `k = 0, 1, ...` finché `k * 480 < len`, con `bpm = N + (M - N) * (k * 480) // len`; più uno finale al tick di fine battuta con valore `M`. Esempio, 4/4, `tempo=100>70`: 100, 92, 85, 77 ai tick 0, 480, 960, 1440 e 70 al tick 1920.
- I BPM sono interi da 4 a 400 (`E015`). Tutta la curva si calcola in BPM; la conversione in microsecondi avviene solo scrivendo il MIDI.
- Nel brano c'è **al massimo un tempo per tick: vince l'ultimo** dichiarato, in quest'ordine: `tempo` iniziale, battute nell'ordine di esecuzione, poi gli `at ... tempo=` nell'ordine del file.
- **`meter=N/D`** (dalla 1.1): cambia il metro **da questa battuta alla fine della sezione**, seguendo l'ordine in cui le battute sono scritte (un blocco `repeat` non lo limita). **Ogni sezione comincia nel metro dell'intestazione**: la lunghezza di una battuta dipende solo dal testo della sua sezione, mai da ciò che è stato suonato prima. Stessi limiti di `meter` (`E018`). `len=` continua a fissare la lunghezza di una sola battuta senza cambiare il metro.
- **`key=K`** (dalla 1.1): cambia la tonalità allo stesso modo, da questa battuta alla fine della sezione; ogni sezione comincia nella tonalità dell'intestazione. Come `key`, non cambia le note, e `transpose` non la modifica.
- **Indicazioni nel file MIDI.** Una battuta scrive una Time Signature al suo inizio quando il suo metro è diverso da quello della battuta suonata prima (per la prima battuta: da quello dell'intestazione), e una Key Signature quando la sua tonalità è diversa dall'ultima scritta. Una battuta senza tonalità in vigore (nessun `key` nell'intestazione, nessun `key=` prima di lei nella sezione) non ne scrive.
- Nel brano c'è **al massimo un'indicazione di metro e una di tonalità per tick: vince l'ultima** dichiarata, in quest'ordine: l'intestazione, le battute nell'ordine di esecuzione, poi gli `at ... meter=` e `at ... key=` nell'ordine del file. Quella che vince al tick 0 prende il posto di quella dell'intestazione.

```
section waltz
  bar C meter=3/4        # 1440 tick, e così le battute che seguono
    P: C4/2.
  bar G
    P: G4/2.
end
```

### 10.3 Linee di track

```
TRACK{attributi di linea}: contenuto
```

- Fino alla 1.0 un track ha al massimo una linea per battuta (`E001`). Dalla 1.1 può averne più d'una: vedi *Voci* più sotto. Un track non nominato tace.
- Dalla 0.2 il contenuto può continuare sulle righe successive: ogni riga che non è `bar`, `repeat`, `end` o una nuova linea di track continua la linea precedente.
- Una linea senza alcun contenuto dà `E001`.
- Il contenuto deve riempire **esattamente** la battuta, altrimenti `E003`.

```
RH{v=70}:
  C5/8 D5/8 E5/4
  G5/2
```

**Voci (dalla 1.1).** Quando un track ha più linee in una battuta, ogni linea è una **voce** indipendente: la prima linea del track nella battuta è la voce 0, la seconda la voce 1, e così via.

- Ogni voce ha i suoi attributi di linea e riempie la battuta esattamente per conto suo; può usare pattern e segmenti come ogni linea.
- Tutte le voci suonano sul canale del track. Fra loro vale la regola di duplicati e sovrapposizioni (§14): la stessa altezza che inizia allo stesso tick in due voci dà `E017`, e una nota che inizia mentre la stessa altezza sta suonando in un'altra voce la tronca.
- Una legatura unisce note con lo **stesso numero di voce**: la voce 1 di una battuta continua nella voce 1 della battuta suonata dopo.

```
bar C
  Pno{v=85}: E5/2 G5/2        # voce 0: melodia
  Pno{v=55}: C3/1             # voce 1: basso
```

### 10.4 Più accordi nella stessa battuta

`bar Cm Ab Bb` divide la battuta in **segmenti uguali**, uno per accordo. Sono ammesse tutte le divisioni intere in tick (4/4 con tre accordi: 640 tick ciascuno); altrimenti `E014`. L'accordo attivo cambia all'inizio di ogni segmento.

Una linea può essere scritta in due modi:

- **Senza `|`**: copre l'intera battuta. Con `use`, il pattern riparte a ogni segmento. Le note scritte a mano possono attraversare il confine fra segmenti.
- **Con `|`** (dalla 0.2): una parte per segmento. Il numero di parti deve essere uguale al numero di accordi (`E021`). Ogni parte è `use ...` oppure note, e deve riempire esattamente il proprio segmento (`E003`, `E009`).

```
bar Cm Ab
  LH: use arp4 | C3/4 Eb3/4
```

### 10.5 Blocchi `repeat` (dalla 0.2)

```
repeat N
  bar ...
end
```

Ripete N volte (1–1000) le battute che contiene. I blocchi si possono annidare. Il numero di battuta riportato negli errori è la posizione della battuta nel testo della sezione, non nell'esecuzione.

## 11. Esecuzione: `play` e `at`

### 11.1 `play`

```
play NOME [xN] [transpose=±S]
```

L'ordine dei `play` è l'ordine del brano. `xN` ripete la sezione N volte (1–1000). `transpose` sposta di S semitoni tutte le note dei track melodici, comprese quelle di pattern, voicing e `mN`; la batteria non viene trasposta. Una nota che esce da 0–127 dà `E006`.

### 11.2 `at`

Eventi a tick assoluti, contati dall'inizio del brano dopo l'espansione. Si scrivono fuori dalle sezioni.

```
at TICK TRACK ALTEZZA d=TICK [v=VELOCITY]
at TICK TRACK ccN=V             # dalla 1.0
at TICK TRACK bend=V            # dalla 1.0
at TICK TRACK "testo"           # dalla 1.0
at TICK tempo=BPM               # dalla 1.0
at TICK meter=N/D               # dalla 1.1
at TICK key=K                   # dalla 1.1
```

- La nota è già risolta: `d=` è obbligatorio ed è la durata sonora; non ha offset, articolazione né legature; `v=` vale 80 se omesso.
- Le note `at` partecipano al controllo di duplicati e sovrapposizioni (§14).
- Le forme `at` non accettano rampe e non vengono trasposte.
- `at ... meter=` e `at ... key=` scrivono soltanto un'indicazione nel file MIDI (§10.2): non cambiano la lunghezza di nessuna battuta.

`loma decompile` usa queste forme per riscrivere un file MIDI come sorgente LOMA senza perdite; il sorgente dichiara `loma 1.1` solo quando il file ha indicazioni dopo il tick 0.

## 12. Limiti

Un compilatore conforme MUST rifiutare i file che superano questi limiti.

| Elemento | Limite | Errore |
|---|---|---|
| Cifre di un numero | al massimo 9 | `E018` |
| Numeratore / denominatore del `meter` | 1–64 / 1, 2, 4, 8, 16, 32, 64 | `E018` |
| Ripetizioni (`xN`, `repeat N`) | 1–1000 | `E018` |
| Battute dopo l'espansione | al massimo 100000 | `E018` |
| Tick di qualsiasi evento | ≤ 268435455 | `E018` |
| Note (dopo l'espansione, prima delle legature) | al massimo 1000000 | `E018` |
| Eventi di controllo (cc, bend, testi) | al massimo 1000000 | `E018` |
| Elementi espansi (note, pause, controlli, passi di pattern) | al massimo 4000000 | `E018` |
| Blocchi `repeat` annidati | al massimo 16 livelli | `E018` |
| Tempo | 4–400 BPM | `E015` |

I limiti su battute, note, controlli, elementi espansi e lunghezza del brano sono **fatali**: il compilatore si ferma e riporta solo quell'errore.

## 13. Errori

Ogni errore ha un **codice**, una **riga** e un messaggio; dove ha senso, anche sezione, battuta, accordi, track e valori numerici.

```
E003 line 14 bar 2 (Ab) track RH: bar length mismatch. Expected 1920 ticks, got 1680. Missing 240 ticks (= /8).
```

Forma JSON (`--json`): un array di oggetti. `code` e `line` sono obbligatori; gli altri campi SHOULD esserci. Un compilatore MAY aggiungere `suggestion` (per esempio `"suggestion": "add_rest", "duration": "/8"`) e, per un nome che sembra scritto male, `did_you_mean` con il nome valido più vicino (per esempio `"did_you_mean": "Cmaj7"`), ma non modifica mai il file. La suite di conformità confronta solo `code` e `line`: messaggi e suggerimenti non sono normativi.

```json
[{"code": "E003", "line": 14, "section": "verse", "bar": 2, "chord": "Ab", "track": "RH",
  "message": "bar length mismatch. Expected 1920 ticks, got 1680. Missing 240 ticks (= /8).",
  "expected": 1920, "got": 1680, "missing": 240, "suggestion": "add_rest", "duration": "/8"}]
```

| Codice | Significato |
|---|---|
| E001 | Errore di sintassi (anche: valore di un attributo o di un'opzione fuori dall'intervallo ammesso) |
| E002 | Comando sconosciuto |
| E003 | Il contenuto non riempie esattamente la battuta o il segmento |
| E004 | Nome non definito: pattern, sezione, swing o voicing |
| E005 | Sigla di accordo sconosciuta o inversione impossibile |
| E006 | Altezza fuori da 0–127, o ottava `base` fuori da −1..9 |
| E007 | Durata non valida (denominatore non ammesso o risultato non intero in tick) |
| E008 | Track non dichiarato |
| E009 | Il pattern non riempie esattamente la battuta o il segmento |
| E010 | Tono inesistente, o non presente nell'accordo |
| E011 | Canale già usato, canale 10 su un track melodico, o più di un track `drums` |
| E012 | Legatura non valida |
| E013 | Tonalità non valida |
| E014 | Battuta non divisibile in parti intere fra gli accordi |
| E015 | Tempo fuori da 4–400 BPM |
| E016 | `use` mescolato a note nello stesso segmento |
| E017 | Note duplicate: stessa altezza, stesso canale, stesso tick di inizio |
| E018 | Limite superato (§12) |
| E019 | Nome non valido, riservato o duplicato |
| E020 | Costrutto non disponibile nella versione dichiarata (§18) |
| E021 | Numero di segmenti (`|`) diverso dal numero di accordi |

### 13.1 Ordine e fasi

Gli errori sono riportati **ordinati per riga**, poi per codice, senza ripetizioni (stesso codice, stessa riga, stesso track).

1. **Fase sintattica**, riga per riga: al massimo **un errore per riga**.
2. **Fase semantica**: una sezione non definita in un `play` (`E004`); per ogni battuta il **primo** errore, seguendo le linee di track nell'ordine in cui sono scritte (`E014`, `E021`, `E004`, `E009`, `E010`, `E006`, `E003`); poi le legature (`E012`), poi note duplicate ed eventi oltre il limite (`E017`, `E018`). Le sezioni mai eseguite sono validate battuta per battuta.

Le due fasi sono riportate insieme, così un solo giro di correzioni vede più errori possibile. Quando la fase sintattica ha trovato errori, la fase semantica è **ridotta** a ciò che non dipende dalle righe mancanti:

- si eseguono solo il controllo delle sezioni non definite e i controlli di battuta; legature, note duplicate e limiti (`E012`, `E017`, `E018`) si controllano solo su un file sintatticamente pulito;
- una battuta con la riga `bar` sbagliata non viene controllata, e se quella riga contiene `meter=` non lo sono nemmeno le battute che la seguono nella sezione (la loro lunghezza non è nota); nelle altre battute una linea di track con un errore di sintassi (anche vuota) viene saltata, e il primo errore si cerca fra le linee rimanenti;
- l'uso di un pattern, uno swing, un voicing o una sezione la cui definizione ha un errore di sintassi non è un errore: quella linea di track (o quel `play`) viene saltata. Il nome di una definizione fallita è il più lungo nome valido all'inizio della parola che segue la parola chiave;
- una sezione con la riga `section` sbagliata viene validata come una sezione mai eseguita;
- ogni battuta è controllata una volta per ogni `play` che usa la sua sezione, con la trasposizione di quel `play`;
- se la riga `loma` o l'istruzione `meter` è sbagliata, la fase semantica non parte;
- se durante la fase ridotta si supera un limite fatale (§12), i suoi errori sono scartati e si riportano solo gli errori di sintassi.

Regole di ripresa nella fase sintattica, per non segnalare errori a cascata (SHOULD):

- una riga `bar` sbagliata fa ignorare le sue linee di track;
- una linea di track sbagliata fa ignorare le sue righe di continuazione;
- una dichiarazione `track` sbagliata fa ignorare le righe che usano quel nome;
- un'intestazione `section` o `repeat` sbagliata non impedisce di analizzarne il corpo;
- un'istruzione globale dentro una sezione dà `E001` ("manca `end`") e chiude la sezione.

Riga riportata: quella dove è scritto il costrutto. Per `E003` è la riga dell'ultimo elemento della linea o del segmento (la prima riga della linea, se il segmento è vuoto); per `E004` su una sezione è la riga del `play`; per `E009`, `E021` e gli errori dei pattern è la prima riga della linea di track; per `E014` è la riga `bar`; per `E017` è la riga della seconda nota.

## 14. Risoluzione delle note

Per ogni nota un compilatore MUST applicare i passi in quest'ordine:

1. **Espansione.** `play`, ripetizioni, `repeat`, trasposizione, pattern e voicing producono per ogni voce di ogni track una sequenza di note con posizione (cursore) e durata scritta.
2. **Attributi.** Default, poi linea (con rampa di velocity e swing calcolati alla posizione della nota), poi elemento, poi nota.
3. **Legature.** Dentro ogni voce, le note legate si fondono in una sola: durata scritta = somma, attributi della prima.
4. **Durata sonora.** `d=` se presente, altrimenti `max(1, durata_scritta * pct // 100)`.
5. **Offset.** `inizio = max(0, posizione + o + swing)`, `fine = inizio + durata_sonora`.
6. **Duplicati e sovrapposizioni**, fra tutte le note con la stessa altezza sullo stesso canale (comprese le note `at`), ordinate per inizio: due note con lo stesso inizio danno `E017`; se una nota riparte mentre la precedente suona ancora, la fine della precedente viene portata all'inizio della nuova.
7. **Eventi.** Note-on, note-off, controlli, tempo e indicazioni passano all'ordinamento di §15.

## 15. Eventi: ordine e JSON canonico

### 15.1 Ordinamento

Tutti gli eventi sono ordinati per la chiave:

```
(tick, tipo, indice_track, canale, altezza, numero_progressivo)
```

Tipi nello stesso tick: **−2** indicazione di metro, **−1** indicazione di tonalità, **0** tempo, **1** note-off, **2** controlli (control change, pitch bend, testi), **3** note-on. Un note-off prima del note-on permette di ribattere la stessa nota; un controllo prima del note-on agisce sulla nota che inizia in quel tick.

- Gli eventi di tempo e le indicazioni hanno `indice_track = -1`, canale 0, altezza 0, numero progressivo 0.
- I controlli hanno altezza 0, quindi nello stesso tick restano nell'ordine in cui sono stati generati.
- `numero_progressivo` è un contatore **per track** che parte da 0. Si assegna dopo le legature, percorrendo gli elementi del track **voce per voce** (tutta la voce 0, poi tutta la voce 1, e così via), ciascuna nell'ordine di espansione (battute in ordine di esecuzione; dentro una battuta, le parti e gli elementi nell'ordine scritto; i passi di un pattern in ordine): ogni evento di controllo prende un numero (una rampa: uno per ciascun evento); ogni nota ne prende due consecutivi, note-on e note-off; le note di un accordo nell'ordine scritto, quelle di un gruppo o di un voicing nell'ordine dei toni. Una nota fusa da una legatura è numerata al posto della sua prima nota. Gli eventi `at` sono numerati **dopo** tutti gli altri eventi del track, nell'ordine del file.

Un compilatore non deve mai affidarsi all'ordine implicito di dizionari, insiemi o librerie: costruisce la lista e la ordina con questa chiave.

### 15.2 JSON canonico

`loma expand FILE --json` stampa gli eventi nell'ordine di §15.1. Serve a capire dove divergono due compilatori: nell'interpretazione (LOMA → eventi) o nella scrittura dei byte (eventi → MIDI).

Formato: un array JSON su una sola riga, seguito da un solo a capo. Ogni evento è un oggetto con le **chiavi in ordine alfabetico**, senza spazi, con separatori `,` e `:`. Le stringhe sono in UTF-8 senza escape dei caratteri non ASCII.

| `type` | Campi |
|---|---|
| `tempo` | `bpm`, `tick`, `type` |
| `meter` | `den`, `num`, `tick`, `type` |
| `key` | `mi`, `sf`, `tick`, `type` |
| `note_on` | `ch`, `pitch`, `tick`, `track`, `type`, `vel` |
| `note_off` | `ch`, `pitch`, `tick`, `track`, `type` |
| `cc` | `ch`, `controller`, `tick`, `track`, `type`, `value` |
| `bend` | `ch`, `tick`, `track`, `type`, `value` |
| `lyric` | `text`, `tick`, `track`, `type` |

Le indicazioni di metro e di tonalità al tick 0 non sono eventi: come il titolo e i programmi, fanno parte dell'inizio del file MIDI (§16). Gli eventi `meter` e `key` esistono solo dopo il tick 0, con `sf` e `mi` come nella tabella di §16.

```
[{"bpm":120,"tick":0,"type":"tempo"},{"ch":1,"pitch":60,"tick":0,"track":"P","type":"note_on","vel":80},{"ch":1,"pitch":60,"tick":1728,"track":"P","type":"note_off"}]
```

## 16. MIDI canonico

- Standard MIDI File **formato 1**, 480 tick per semiminima.
- `MThd`: lunghezza 6, formato 1, numero di track = 1 + numero di `track` dichiarati, divisione `0x01E0`.
- **Track 0 (conductor)**, al tick 0 in quest'ordine:
  1. Track Name `FF 03` con il `title`, se presente (UTF-8);
  2. Time Signature `FF 58 04 nn dd 18 08` del metro al tick 0: `nn` numeratore, `dd` log2 del denominatore;
  3. Key Signature `FF 59 02 sf mi` della tonalità al tick 0, se c'è (tabella sotto);
  4. gli eventi Set Tempo `FF 51 03 tttttt`, ciascuno al suo tick. Valore: `60000000 // bpm` microsecondi per semiminima, su 3 byte. Dalla 1.1 qui si scrivono anche gli eventi Time Signature e Key Signature dopo il tick 0, con gli stessi byte indicati sopra, tutti nell'ordine di §15.1.
- Un track MIDI per ogni `track`, nell'ordine di dichiarazione. Al tick 0: Track Name `FF 03` con il nome LOMA, poi Program Change `Cn pp` (non per `drums`), poi gli eventi del track nell'ordine di §15.1.
- Codifica, con `n` = canale − 1:

| Evento | Byte |
|---|---|
| note-on | `9n pp vv` |
| note-off | `8n pp 40` (release velocity fissa a 64) |
| control change | `Bn cc vv` |
| pitch bend | `En ll mm`, con `x = valore + 8192`, `ll = x & 0x7F`, `mm = x >> 7` |
| testo | `FF 05 len testo` (UTF-8) |

- Delta time in VLQ. **Nessun running status**: ogni evento scrive il proprio byte di stato.
- **End of Track** `FF 2F 00` in ogni track, anche vuoto, tutti allo stesso tick: `fine = max(lunghezza totale delle battute eseguite, tick dell'ultimo evento)`.
- La lunghezza di ogni chunk `MTrk` è il numero di byte che contiene. Nessun altro metadato: niente timestamp, nome o versione del software.

**Tonalità.** `sf` è il numero di diesis (positivo) o bemolle (negativo), su un byte con segno; `mi` è 0 per maggiore, 1 per minore.

| sf | Maggiore | Minore | sf | Maggiore | Minore |
|---|---|---|---|---|---|
| 0 | `C` | `Am` | | | |
| 1 | `G` | `Em` | −1 | `F` | `Dm` |
| 2 | `D` | `Bm` | −2 | `Bb` | `Gm` |
| 3 | `A` | `F#m` | −3 | `Eb` | `Cm` |
| 4 | `E` | `C#m` | −4 | `Ab` | `Fm` |
| 5 | `B` | `G#m` | −5 | `Db` | `Bbm` |
| 6 | `F#` | `D#m` | −6 | `Gb` | `Ebm` |
| 7 | `C#` | `A#m` | −7 | `Cb` | `Abm` |

### 16.1 Esempio con i byte attesi

Questi byte sono stati calcolati a mano dalla specifica, non presi da un compilatore.

```loma
loma 0.1
tempo 120
meter 4/4
track P ch=1 program=0
section s
  bar C
    P: C4/1
end
play s
```

La nota dura `1920 * 90 // 100 = 1728` tick; il brano finisce al tick 1920. Il file è lungo 72 byte.

```
4D 54 68 64  00 00 00 06  00 01  00 02  01 E0        MThd, formato 1, 2 track, 480 PPQ
4D 54 72 6B  00 00 00 14                             MTrk (conductor), 20 byte
  00 FF 58 04 04 02 18 08                            time signature 4/4
  00 FF 51 03 07 A1 20                               tempo 500000 us (120 BPM)
  8F 00 FF 2F 00                                     end of track, delta 1920
4D 54 72 6B  00 00 00 16                             MTrk (P), 22 byte
  00 FF 03 01 50                                     track name "P"
  00 C0 00                                           program change 0, canale 1
  00 90 3C 50                                        note-on  C4 (60), velocity 80
  8D 40 80 3C 40                                     note-off C4, delta 1728
  81 40 FF 2F 00                                     end of track, delta 192
```

SHA-256: `ab4d7aaa44d5b98d3df8d7df7937dbee852d20ce3869a8b5d4612758349bb460`.

## 17. Riga di comando e suite di conformità

La suite parla con un compilatore attraverso tre comandi. Un compilatore che vuole essere verificato MUST offrirli:

| Comando | Comportamento |
|---|---|
| `CMD compile FILE -o OUT` | Scrive il MIDI. Stato di uscita 0; 1 se il file ha errori. |
| `CMD expand FILE --json` | Stampa il JSON canonico (§15.2). Stato 0. |
| `CMD check FILE --json` | File valido: stampa `[]`, stato 0. File non valido: stampa l'array di errori (§13), stato 1. |

`FILE` può essere `-` per leggere dallo standard input (SHOULD).

La suite è in `conformance/`:

- `valid/NOME.loma` con `NOME.mid`, `NOME.events.json`, `NOME.sha256`: il compilatore deve produrre gli stessi byte e lo stesso JSON;
- `errors/NOME.loma` con `NOME.errors.json`: il compilatore deve riportare gli stessi `code` e `line`, nello stesso ordine (con `--first-error-only` si confronta solo il primo, il minimo richiesto da §2).

```
python3 conformance/run.py --cmd "python3 -m loma"
python3 conformance/run.py --cmd "node js/loma.js"
```

## 18. Versioni del linguaggio

Ogni versione è un soprainsieme della precedente: un file valido in una versione produce gli stessi byte se dichiara una versione successiva. Usare un costrutto senza dichiarare la versione che lo introduce dà `E020`.

| Versione | Aggiunge |
|---|---|
| **0.1** | Note, pause, accordi, legature, attributi, pedale, batteria, pattern, sezioni, `play`, trasposizione, `at` per le note, cambi di tempo |
| **0.2** | `ccN=`, `bend=` e rampe; rampa di velocity `v=N>M`; `swing`; contenuto su più righe; segmenti con `\|`; elenchi `use A,B`; `pattern ... from`; quintine `q` e gruppi `xA/B`; blocchi `repeat` |
| **0.3** | Accordi estesi; inversioni `^K`; basso `/X` e tono `0`; toni `9 11 16 18`; segni d'ottava; `voicing` e `*NOME` |
| **1.0** | Testi `"..."`; altezze numeriche `mN`; `at` con `cc`, `bend`, testo e `tempo` |
| **1.1** | Opzioni di battuta `meter=` e `key=`; `at` con `meter` e `key`; più voci su un track |

## 19. Esempio completo

```loma
loma 1.0
title "Esempio"
tempo 100
meter 4/4
key Cm

track RH ch=1 program=0
track LH ch=2 program=0
track Kit drums

pattern arp8 base=3 dur=/8 : 1 3 5 3 1 3 5 3
pattern arpB from arp8 : 8=8
swing lieve grid=/8 : 0 12
voicing aperto base=3 : 1 5 10

section verse
  bar Cm
    RH{v=78}: Eb5/8 D5/8 C5/4 G4/4 r/4
    LH{v=60 swing=lieve}: use arp8
    Kit{v=64}: kick/4 hat/4 snare/4 hat/4
  bar Ab Bb
    RH{v=70>90}: C5/4 Eb5/4 | D5/4. F5/8{o=-6}
    LH{v=60}: *aperto/2 | *aperto/2
    Kit{v=64}: kick/4 hat/4 | snare/4 hat/8 hat/8
  repeat 2
    bar Gm
      RH{v=72}: "la" G4/2~ G4/4 Bb4/4{a=stac}
      LH{v=55}: use arpB
  end
end

section ending
  bar Cm tempo=100>70
    RH{v=70}: pedal+ cc11=100>40/1 [C4 Eb4 G4]/1{a=leg} pedal-
    LH{v=55}: C2/1{a=leg}
    Kit{v=50}: crash/1
end

play verse x2
play ending
```
