# MediaGrabber NAS

**Video and audio downloads, a persistent queue, and automatic YouTube monitoring for Synology NAS.**

[Download and release notes](https://github.com/petrjones/MediaGrabber-NAS/releases) · [Česky](#česky) · [Windows edition](https://github.com/petrjones/MediaGrabber)

## English

MediaGrabber NAS by **PJSoft** lets you manage downloads in your browser while your NAS does the work. Downloads and scheduled source checks continue after you close the browser or switch off your computer.

The current beta is available as an **SPK package for Synology DSM**. It is an independent project, not an official or Synology-certified application.

### Features

- Download YouTube videos or audio, with quality, subtitle and destination settings.
- Preview playlists and select or exclude individual items.
- Paste multiple links or load a UTF-8 TXT list. Each batch shares one profile; add links separately for different settings.
- Monitor public YouTube channels and playlists, downloading new items automatically.
- Persistent queue, pause/resume, retry failed items and duplicate checking that verifies recorded files still exist.
- Daily download window, bandwidth limit and minimum free-space check.
- Write available metadata and artwork to supported audio formats.
- Compact history with detailed results and an option to clear records while keeping downloaded media.
- Export/import settings, monitored sources, queue and history as JSON. Media files and passwords are not included.
- Interface in English, Czech, Spanish, German, French, Portuguese (Portugal), Portuguese (Brazil), Polish and Italian.

### Requirements

- Synology NAS with an **x86-64 processor**.
- **DSM 7.2.2-72806 or newer**.
- **Container Manager 20.10.23-1437 or newer**, installed and running.
- Internet access for initial installation and source/download operations.

The developer has tested the application on **DS1817+ with DSM 7.3.1 Update 1**, including beta.20 and its updated About window. Other models have not yet been verified. This beta is intended for a trusted local network and one trusted administrator.

### Installation and updates

1. Open [Releases](https://github.com/petrjones/MediaGrabber-NAS/releases) and download the `.spk` file from the newest applicable release's **Assets**. A `.spk.sha256` file is provided for integrity verification.
2. In DSM, choose **Package Center → Manual Install** and select the SPK intact.
3. During first installation, choose an application password. The installer prepares the service account and the `MediaGrabber` shared folder automatically.
4. **The first installation requires internet and may take several minutes** while the NAS downloads dependencies and builds the container.
5. Open MediaGrabber NAS from DSM. Direct access at `http://NAS_LAN_IP:8787` uses login name `admin` and the application password chosen during installation.

**To update:** install a newer SPK as an update, without uninstalling the previous package. Settings, queue, history and media are retained. Close and reopen the application window after upgrading.

### Availability and support

MediaGrabber NAS is free of charge. Optional contributions do not unlock features or change functionality. Download availability depends on the source and yt-dlp. Use the application for content you own or have permission to download.

Support: **jones.petr@gmail.com** · [Report an issue](https://github.com/petrjones/MediaGrabber-NAS/issues)

The [Windows edition](https://github.com/petrjones/MediaGrabber) is a separate application with additional features. The NAS About window checks its latest stable version on GitHub and retains the last verified version if a later check fails.


## Screenshots / Snímky aplikace

<img width="1996" height="1215" alt="MediaGrabber NAS" src="https://github.com/user-attachments/assets/19a5bfa2-c32d-4ef6-a3cd-1ebfc6f3733b" />
<img width="1946" height="1097" alt="MediaGrabber NAS_2" src="https://github.com/user-attachments/assets/eb8cb117-3dcc-410e-b93a-60d50557728e" />
<img width="2017" height="1222" alt="MediaGrabber NAS_3" src="https://github.com/user-attachments/assets/129ab366-7914-4df4-ad0c-20e4b2aa5a85" />
<img width="2042" height="1211" alt="MediaGrabber NAS_4" src="https://github.com/user-attachments/assets/916d47c5-ee01-4065-ae55-69ab81c3f6a8" />

---

## Česky

**MediaGrabber NAS od PJSoft** umožňuje stahovat video a zvuk z YouTube, spravovat frontu a automaticky sledovat nové položky kanálů a playlistů. Vše ovládáš v prohlížeči a NAS pokračuje v práci i po jeho zavření nebo vypnutí počítače.

Současná beta je dostupná jako **SPK balíček pro Synology DSM**. Jde o nezávislý projekt, který dosud není oficiální ani certifikovanou aplikací Synology.

### Funkce

- Stahování videa nebo zvuku s výběrem kvality, titulků a cílové složky.
- Náhled playlistu, výběr jednotlivých položek a vynechání nechtěných záznamů.
- Hromadné vložení odkazů nebo načtení UTF-8 TXT seznamu. Jedna dávka používá společné nastavení; pro různé nastavení přidávej odkazy samostatně.
- Automatické sledování novinek veřejných kanálů a playlistů YouTube.
- Trvalá fronta, pozastavení a obnovení, opakování neúspěšných položek a kontrola duplicit včetně existence zaznamenaného souboru.
- Časové plánování, omezení rychlosti a kontrola minimálního volného místa.
- Zápis dostupných metadat a obalů do podporovaných zvukových formátů.
- Kompaktní historie s podrobnými výsledky a možností smazat záznamy bez odstranění stažených médií.
- Export a import nastavení, sledovaných zdrojů, fronty a historie ve formátu JSON. Média ani hesla se nepřenášejí.
- Rozhraní v devíti jazycích včetně češtiny.

### Požadavky

- Synology s procesorem **x86-64**.
- **DSM 7.2.2-72806 nebo novější**.
- Nainstalovaný a spuštěný **Container Manager 20.10.23-1437 nebo novější**.
- Připojení k internetu pro první instalaci, sledování zdrojů a stahování.

Vývojář aplikaci vyzkoušel na **DS1817+ s DSM 7.3.1 Update 1**, včetně beta.20 a upraveného okna O aplikaci. Ostatní modely zatím nejsou ověřené. Beta je určená pro důvěryhodnou místní síť a jednoho důvěryhodného správce.

### Instalace a aktualizace

1. Otevři [vydání aplikace](https://github.com/petrjones/MediaGrabber-NAS/releases) a v části **Assets** nejnovějšího vhodného vydání stáhni soubor `.spk`. Soubor `.spk.sha256` slouží ke kontrole jeho integrity.
2. V DSM zvol **Centrum balíčků → Ruční instalace** a vyber celý SPK bez rozbalování.
3. Při první instalaci si nastav heslo aplikace. Průvodce automaticky připraví účet služby a sdílenou složku `MediaGrabber`.
4. **První instalace potřebuje internet a může trvat několik minut**, než NAS stáhne potřebné součásti a sestaví kontejner.
5. Aplikaci otevři z prostředí DSM. Přímý přístup přes `http://IP_ADRESA_NASU:8787` používá jméno `admin` a heslo zvolené při instalaci.

**Aktualizace:** novější SPK nainstaluj jako aktualizaci bez odinstalování předchozího balíčku. Nastavení, fronta, historie a média zůstanou zachované. Po aktualizaci zavři a znovu otevři okno aplikace.

### Dostupnost a podpora

MediaGrabber NAS je zdarma. Dobrovolný příspěvek neodemyká žádné funkce ani nemění funkčnost. Dostupnost stahování závisí na zdroji a nástroji yt-dlp. Stahuj obsah, který vlastníš nebo k jehož stažení máš svolení.

Podpora: **jones.petr@gmail.com** · [Nahlásit problém](https://github.com/petrjones/MediaGrabber-NAS/issues)

[Verze pro Windows](https://github.com/petrjones/MediaGrabber) je samostatná aplikace s dalšími funkcemi. Okno O aplikaci v NAS verzi ověřuje její aktuální stabilní vydání na GitHubu a při neúspěšné kontrole ponechá poslední ověřený údaj.
