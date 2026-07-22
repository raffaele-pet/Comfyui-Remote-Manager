# ComfyUI Remote Manager

Applicazione desktop per Windows che consente di gestire da PC2 un'installazione di ComfyUI su PC1 tramite SSH e rete Tailscale.

## Funzioni principali

- connessione SSH a PC1;
- menu laterale SSH con profilo `pc-lavoro`, porta configurabile e collegamenti alla home remota;
- memorizzazione opzionale della password protetta tramite la cifratura di Windows;
- controllo, avvio, arresto e aggiornamento di ComfyUI;
- avvio di Cloudflare Tunnel e visualizzazione del link pubblico `trycloudflare.com`;
- browser remoto dei file tramite SFTP;
- caricamento di file e cartelle con avanzamento visibile;
- download diretto di file su PC1 tramite URL;
- download di file da PC1 a PC2;
- rinomina, copia, taglia/incolla, spostamento ed eliminazione di file e cartelle;
- creazione di nuove cartelle;
- apertura di un terminale remoto nella cartella selezionata;
- terminale PowerShell SSH persistente, utilizzabile senza Visual Studio Code;
- apertura e modifica diretta dei file di testo su PC1;
- visualizzazione dei file con modalità elenco, dettagli, icone e anteprima immagini.

## Requisiti

- Windows su PC2 e PC1;
- Python 3 su PC2;
- server SSH attivo su PC1;
- Tailscale configurato su entrambi i computer;
- ComfyUI Portable e `cloudflared` disponibili su PC1.

Installa le dipendenze con:

```powershell
py -m pip install -r requirements.txt
```

## Configurazione

Le impostazioni di PC1 si trovano all'inizio di `comfyui_remote_manager.py`:

- `DEFAULT_HOST` e `DEFAULT_USER`;
- percorsi Windows e SFTP dell'installazione di ComfyUI;
- comandi di avvio, aggiornamento e arresto.

Adatta questi valori se l'indirizzo Tailscale, l'utente o la cartella di ComfyUI sono diversi.

## Avvio

Su Windows puoi avviare l'app con un doppio clic su `Avvia ComfyUI Remote Manager.bat`.

In alternativa, dal terminale:

```powershell
py comfyui_remote_manager.py
```

La password SSH viene richiesta nell'interfaccia e non è salvata nel progetto.
