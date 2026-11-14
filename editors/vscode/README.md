# LOMA per Visual Studio Code

Evidenziazione della sintassi per i file `.loma`: parole chiave, nomi di track, accordi, altezze, durate, attributi, controlli, testi e commenti.

## Installazione

Copia questa cartella nella cartella delle estensioni di Visual Studio Code e riavvia l'editor:

- Linux e macOS: `~/.vscode/extensions/loma-language`
- Windows: `%USERPROFILE%\.vscode\extensions\loma-language`

La grammatica `syntaxes/loma.tmLanguage.json` è in formato TextMate e funziona anche con gli altri editor che lo leggono.

Limite: l'evidenziazione riconosce la forma dei simboli, non la loro validità. Per gli errori usa `loma check`.
