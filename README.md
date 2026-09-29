# ComfyUI Remote Manager

Applicazione Windows per gestire ComfyUI Portable su **PC A** da **PC B**. PC B si collega a PC A tramite Tailscale e SSH; il pulsante **Avvia** lancia ComfyUI e un Cloudflare Quick Tunnel, mostrando il link nell'app.

## Installazione su PC A

PC A deve avere ComfyUI Portable per Windows, con un batch `run*.bat` e `python_embeded\python.exe` nella cartella principale.

1. Scarica il repository o almeno `install-pc-a.ps1` su PC A.
2. Apri **PowerShell come amministratore** ed esegui:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\install-pc-a.ps1
   ```

3. Inserisci il percorso della cartella di ComfyUI Portable, scegli il batch di avvio e indica l'utente Windows che userai per SSH. Lo script installa e abilita OpenSSH Server, Tailscale e `cloudflared` se mancanti.
4. Accedi a Tailscale dal browser e torna allo script per la verifica dell'indirizzo Tailscale. Lo script prova ad abilitare **Run Unattended** per rendere PC A raggiungibile anche senza una sessione Windows aperta; se non riesce, abilitalo nelle preferenze Tailscale.
5. Copia su PC B il file `comfyui-remote-config.json` generato sul Desktop. Contiene indirizzo, utente e percorsi; **non contiene password**.

L'account Windows di PC A deve avere una password utilizzabile via SSH; il PIN di Windows Hello non la sostituisce. Per il Quick Tunnel non serve un account Cloudflare: l'app avvia `cloudflared` soltanto quando premi **Avvia**.

## Installazione su PC B

Apri PowerShell su PC B e lancia `install-pc-b.ps1` dalla cartella del repository:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-pc-b.ps1
```

Lo script installa Tailscale e Python se mancanti, copia l'app in `%LOCALAPPDATA%\Programs\ComfyUIRemoteManager`, crea un ambiente Python con le dipendenze e aggiunge un collegamento nel menu Start. Se hai soltanto lo script, prova a clonare il repository: GitHub potrebbe chiederti di autenticarti nel browser.

Accedi a Tailscale con la **stessa tailnet** usata su PC A. Dopo l'installazione, apri l'app dal menu Start e premi **Importa configurazione PC A**, oppure compila a mano host/IP Tailscale, porta SSH, utente e cartella ComfyUI Portable. Inserisci la password SSH nell'app. Puoi anche fornire il file allo script:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-pc-b.ps1 -ConfigPath 'D:\comfyui-remote-config.json'
```

## Se sposti o rinomini ComfyUI

Su PC B modifica **Cartella ComfyUI Portable su PC A** e premi **Salva percorso e batch**. Puoi cambiare anche il **Batch di avvio** (per esempio `run_cpu.bat`). Il percorso viene usato per Avvia, Spegni, Aggiorna, scorciatoie del browser remoto e download da URL. Se l'utente Windows di PC A cambia, aggiorna anche il campo **Utente** e riconnettiti.

Il profilo della connessione è salvato solo su PC B in `%LOCALAPPDATA%\ComfyUIRemoteManager\connection.json`. La password è facoltativa e, se scegli di ricordarla, è protetta con la cifratura di Windows. L'app non crea file di log, link o configurazioni di download sul Desktop di PC A; il link Cloudflare resta visibile nell'app.

## Funzioni

- Controllo, avvio, arresto e aggiornamento di ComfyUI.
- Avvio del tunnel Cloudflare e visualizzazione del link pubblico.
- Browser file SFTP con caricamento, download, anteprime, rinomina, spostamento ed eliminazione.
- Download diretto da URL su PC A, senza script o configurazioni persistenti su PC A.
- Terminale PowerShell SSH persistente e modifica di file di testo remoti.

Il link `trycloudflare.com` è pubblico e temporaneo. [Cloudflare indica i Quick Tunnel per test e sviluppo](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/); non usarlo per dati che richiedono accesso privato.
