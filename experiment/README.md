# Esperimento: le AI sanno scrivere LOMA?

L'ipotesi da verificare è questa: un modello riesce a scrivere musica in LOMA in modo più affidabile, compatto e controllabile rispetto alle alternative?

## Protocollo

1. Dai a un'AI il testo di [prompt.md](prompt.md), senza altro.
2. Salva ogni risposta così com'è:

   ```
   experiment/submissions/NOME_MODELLO/brano1/attempt1.loma
   experiment/submissions/NOME_MODELLO/brano2/attempt1.loma
   experiment/submissions/NOME_MODELLO/brano3/attempt1.loma
   ```

3. Controlla il file:

   ```
   python3 -m loma check experiment/submissions/NOME_MODELLO/brano1/attempt1.loma --json
   ```

4. Se ci sono errori, incolla all'AI **solo** l'uscita del comando e salva la nuova risposta come `attempt2.loma`. Ripeti fino a un file valido o fino a cinque tentativi. Non correggere nulla a mano.
5. Calcola le misure:

   ```
   python3 experiment/run_experiment.py
   ```

   Il programma scrive `results.md` e `results.json`.

6. Compila il MIDI dell'ultimo tentativo, ascoltalo e riempi a mano le colonne *Fedeltà* (il MIDI corrisponde a quello che l'AI dice di aver scritto?) e *Ascolto* (suona in modo convincente?).

## Che cosa si misura

| Indicatore | Come |
|---|---|
| Tentativi di compilazione | numero di file `attemptN.loma` |
| Errori più frequenti | codici di errore di tutti i tentativi |
| Dimensione | byte del file LOMA, del MIDI e degli eventi espansi |
| Rispetto della consegna | battute, strumenti, pattern, accordi, tempo, sezioni |
| Riproducibilità | 20 compilazioni, stesso SHA-256 |
| Fedeltà musicale | a mano |
| Qualità all'ascolto | a mano |

## Stato

In `submissions/reference/` ci sono i tre brani scritti dall'autore della specifica e del compilatore. Servono a provare che gli strumenti funzionano e come termine di confronto: **non sono una misura indipendente**, perché chi li ha scritto conosceva già tutte le regole. L'esperimento è completo quando ci sono i brani di altri modelli.
