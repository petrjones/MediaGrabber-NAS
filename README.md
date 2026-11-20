# MediaGrabber NAS

**Current beta / Aktuální beta: [0.1.0-beta.24](https://github.com/petrjones/MediaGrabber-NAS/releases/tag/v0.1.0-beta24).**

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
- Internet access to download the installer, check online sources and download media. The beta.24 SPK includes the prebuilt application image and runtime dependencies.

The developer confirms successful **beta.24 installation, application startup and a short-video download on DS1817+ with DSM 7.3.1 Update 1**. Other models, clean installation and installation without internet access have not yet been verified. This beta is intended for a trusted local network and one trusted administrator.

### Installation and updates

1. Open the [beta.24 release](https://github.com/petrjones/MediaGrabber-NAS/releases/tag/v0.1.0-beta24) and download **`MediaGrabber-NAS-0.1.0-0024.spk`** from **Assets**. Its `.spk.sha256` file is provided for integrity verification. Source archives are separate downloads and are not required to install the application.
2. In DSM, choose **Package Center → Manual Install** and select the SPK intact.
3. During first installation, choose an application password. The installer prepares the service account and the `MediaGrabber` shared folder automatically.
4. **Beta.24 loads the prebuilt application image included in the SPK through Container Manager.** It does not build the image or download runtime dependencies during installation. Loading the image and starting the application may take several minutes.
5. Open MediaGrabber NAS from DSM. Direct access at `http://NAS_LAN_IP:8787` uses login name `admin` and the application password chosen during installation.

**To update:** install a newer SPK as an update, without uninstalling the previous package. Settings, queue, history and media are retained. Close and reopen the application window after upgrading.

The destination-folder picker currently shows Synology service directories such as `@eaDir`. Choose `/downloads` or a normal user subfolder. Hiding service directories is planned for a later update. Beta.24 fixes the beta.23 preload-image packaging error.

### Availability and support

MediaGrabber NAS is free of charge. Optional contributions do not unlock features or change functionality. Download availability depends on the source and yt-dlp. Use the application only for content you are permitted to download, in accordance with applicable platform terms.

· [Report an issue](https://github.com/petrjones/MediaGrabber-NAS/issues)

The [Windows edition](https://github.com/petrjones/MediaGrabber) is a separate application with additional features. The NAS About window checks its latest stable version on GitHub and retains the last verified version if a later check fails.


## Screenshots / Snímky aplikace

<img width="1996" height="1215" alt="MediaGrabber NAS" src="https://github.com/user-attachments/assets/19a5bfa2-c32d-4ef6-a3cd-1ebfc6f3733b" />
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
- Připojení k internetu pro stažení instalátoru, sledování online zdrojů a stahování médií. SPK bety.24 obsahuje předem sestavený obraz aplikace i potřebné součásti.

Vývojář potvrzuje úspěšnou **instalaci bety.24, spuštění aplikace a stažení krátkého videa na DS1817+ s DSM 7.3.1 Update 1**. Ostatní modely, čistá instalace a instalace bez připojení k internetu zatím nejsou ověřené. Beta je určená pro důvěryhodnou místní síť a jednoho důvěryhodného správce.

### Instalace a aktualizace

1. Otevři [vydání beta.24](https://github.com/petrjones/MediaGrabber-NAS/releases/tag/v0.1.0-beta24) a v části **Assets** stáhni **`MediaGrabber-NAS-0.1.0-0024.spk`**. Odpovídající soubor `.spk.sha256` slouží ke kontrole integrity. Zdrojové archivy jsou samostatně a k instalaci aplikace je nepotřebuješ.
2. V DSM zvol **Centrum balíčků → Ruční instalace** a vyber celý SPK bez rozbalování.
3. Při první instalaci si nastav heslo aplikace. Průvodce automaticky připraví účet služby a sdílenou složku `MediaGrabber`.
4. **Beta.24 prostřednictvím Container Manageru načte předem sestavený obraz aplikace přibalený v SPK.** Při instalaci se obraz nesestavuje ani se nestahují jeho potřebné součásti. Načtení obrazu a spuštění aplikace může trvat několik minut.
5. Aplikaci otevři z prostředí DSM. Přímý přístup přes `http://IP_ADRESA_NASU:8787` používá jméno `admin` a heslo zvolené při instalaci.

**Aktualizace:** novější SPK nainstaluj jako aktualizaci bez odinstalování předchozího balíčku. Nastavení, fronta, historie a média zůstanou zachované. Po aktualizaci zavři a znovu otevři okno aplikace.

Výběr cílové složky zatím zobrazuje i servisní složky Synology, například `@eaDir`. Vyber `/downloads` nebo běžnou vlastní podsložku. Skrytí servisních složek je plánované do další aktualizace. Beta.24 opravuje chybné zabalení obrazu aplikace v betě.23.

### Dostupnost a podpora

MediaGrabber NAS je zdarma. Dobrovolný příspěvek neodemyká žádné funkce ani nemění funkčnost. Dostupnost stahování závisí na zdroji a nástroji yt-dlp. Stahuj jen obsah, k jehož stažení máš oprávnění, a dodržuj podmínky příslušné platformy.

· [Nahlásit problém](https://github.com/petrjones/MediaGrabber-NAS/issues)

[Verze pro Windows](https://github.com/petrjones/MediaGrabber) je samostatná aplikace s dalšími funkcemi. Okno O aplikaci v NAS verzi ověřuje její aktuální stabilní vydání na GitHubu a při neúspěšné kontrole ponechá poslední ověřený údaj.


## License / Licence

The original NAS code is licensed under **GPL-3.0-or-later**; see [LICENSE](LICENSE), [COPYRIGHT](COPYRIGHT) and [third-party notices](THIRD-PARTY-NOTICES.md). The corresponding NAS application source/build archive is included in the SPK, downloadable from About, and attached to the [beta.24 release](https://github.com/petrjones/MediaGrabber-NAS/releases/tag/v0.1.0-beta24). The same release also includes a separate matching runtime-source archive for the components in its application image; neither source archive is required for installation. Third-party components retain their own licenses. The separate Windows edition keeps its existing licensing. See [PRIVACY.md](PRIVACY.md) for data handling and retention.

Původní NAS kód je pod **GPL-3.0-or-later**; viz [LICENSE](LICENSE), [COPYRIGHT](COPYRIGHT) a [licence použitých součástí](THIRD-PARTY-NOTICES.md). Odpovídající zdrojový archiv NAS aplikace včetně sestavení je přibalený v SPK, dostupný z okna O aplikaci a přiložený k [vydání beta.24](https://github.com/petrjones/MediaGrabber-NAS/releases/tag/v0.1.0-beta24). Totéž vydání obsahuje samostatný odpovídající archiv zdrojů součástí obrazu aplikace; k instalaci nepotřebuješ ani jeden ze zdrojových archivů. Použité součásti si ponechávají vlastní licence. Licence samostatné Windows verze se nemění. Zacházení s údaji a jejich uchování popisuje [PRIVACY.md](PRIVACY.md).
