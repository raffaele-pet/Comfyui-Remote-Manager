# ComfyUI Remote Manager

Applicazione Windows per gestire ComfyUI Portable su **PC A** da **PC B**. PC B si collega a PC A tramite Tailscale e SSH; il pulsante **Avvia** lancia ComfyUI e un Cloudflare Quick Tunnel, mostrando il link nell'app.

## Installazione su PC A

PC A deve avere ComfyUI Portable per Windows, con un batch `run*.bat` e `python_embeded\python.exe` nella cartella principale.

1. Scarica `install-pc-a.exe` su PC A e aprilo con un doppio clic. Windows chiederà l'autorizzazione amministratore.
2. Nella finestra scegli la cartella di ComfyUI Portable, il batch di avvio e l'utente Windows per SSH. Premi **Installa componenti** e segui l'avanzamento mostrato nella finestra. Verranno preparati OpenSSH Server, Tailscale e `cloudflared`.
3. Premi **Apri Tailscale**, completa l'accesso nel browser e poi **Verifica accesso**. Usa la stessa tailnet su entrambi i PC. L'installer prova ad abilitare **Run Unattended**; se non riesce, abilitalo dalle preferenze Tailscale.
4. La schermata Cloudflare spiega che il Quick Tunnel usato dall'app non richiede un account Cloudflare. Premi **Verifica cloudflared**.
5. Premi **Salva comfyui-remote-config.json**, scegli dove salvarlo e copialo su PC B. Il file non contiene password.

L'account Windows di PC A deve avere una password utilizzabile via SSH; il PIN di Windows Hello non la sostituisce. Per il Quick Tunnel non serve un account Cloudflare: l'app avvia `cloudflared` soltanto quando premi **Avvia**.

## Installazione su PC B

1. Scarica `install-pc-b.exe` su PC B e aprilo con un doppio clic. La finestra mostra l'avanzamento. L'installer include il codice dell'app: non serve clonare il repository.
2. L'installer prepara Tailscale, Python, le dipendenze dell'app, `run.bat` e un collegamento nel menu Start con l'[icona richiesta di Icons8](https://icons8.it/icon/rJGwKUDZzg4L/ai).
3. Premi **Apri Tailscale**, accedi alla stessa tailnet di PC A e poi **Verifica accesso**.
4. Scegli **Importa configurazione**, **Inserisci a mano** oppure **Apri il programma** e compila i dati lì. Inserisci la password SSH nell'app.

Nessun passaggio richiede di aprire PowerShell. Gli installer sono eseguibili per Windows x64; serve una connessione Internet per scaricare i componenti tramite WinGet e le dipendenze Python. I sorgenti Tkinter sono `install_pc_a.py`, `install_pc_b.py` e `installer_common.py`.

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

Icona del collegamento: [Icons8](https://icons8.it/icon/rJGwKUDZzg4L/ai). Per ricostruire i due eseguibili su Windows, installa PyInstaller e lancia `py build_installers.py`.
