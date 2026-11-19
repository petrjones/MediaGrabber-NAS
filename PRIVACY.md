# MediaGrabber NAS — information about data / informace o údajích

Updated 19 November 2026. Developer and support: PJSoft / Petr Jones, jones.petr@gmail.com.

## English

MediaGrabber NAS runs on the NAS operated by you or your administrator. It stores download/watch URLs, titles, output and scheduling settings, queue/history/results, file paths/sizes and discovery/duplicate records in local application state. It does not automatically send this history or your downloaded media to the developer.

Authentication uses a password hash, application sessions and temporary failed-login limits that include the connecting IP address. A restricted installer credential file also retains the separate application password for service startup. Private stopped-state backups can include this file. They must be protected as credentials; they do not contain only hashes.

Native DSM sign-in validates an existing administrator session without requesting the DSM password. The host launcher exchanges a short-lived, single-use grant. The portal strips DSM cookies and tokens before requests reach the application container. MediaGrabber sessions are independent of DSM logout, expire within 12 hours and can be ended using the app's Logout button. DSM and reverse-proxy logs are controlled by the NAS administrator and may contain request/network information.

Online installation obtains software from Docker image, Debian and PyPI distribution services. Source checks and downloads contact YouTube and its delivery/metadata servers. Opening About may retrieve public Windows release metadata from GitHub. These services receive the information needed for those requests, including the public IP address. There is no separate telemetry sender to PJSoft. External links deliberately opened by you are subject to their providers' terms.

Browser storage remembers the interface language and tooltip preference. A session cookie keeps you signed in. The optional support dialog provides bank-transfer details; the application sends no payment.

Records remain on the NAS until removed. Clearing history preserves media, discovery/duplicate tracking and private backups. JSON export excludes credentials, sessions and media but can include personal URLs, titles, history and paths. A full private backup includes credentials. During package removal you can explicitly choose to erase private application settings, history, source records, credentials and private backups. Leaving that choice unchecked retains them for reinstallation. Downloaded media is retained in either case. An upgrade never applies this erasure option.

If you voluntarily email diagnostics to support, the developer receives the information you include. Do not include passwords, private keys or unnecessary personal data. Support correspondence is kept as needed to handle the request and applicable obligations; contact the support address about access, correction or deletion. If an organization operates this software for others, that operator is responsible for its deployment, permissions and any additional notices required for that use.

## Česky

MediaGrabber NAS běží na NASu provozovaném tebou nebo tvým správcem. Lokálně ukládá odkazy ke stažení a sledované zdroje, názvy, nastavení výstupu a plánování, frontu, historii a výsledky, cesty a velikosti souborů a evidenci nalezených a stažených položek. Historii ani stažená média automaticky neposílá vývojáři.

Přihlašování používá hash hesla, relace aplikace a dočasnou evidenci neúspěšných pokusů včetně IP adresy připojení. Soukromý instalační soubor navíc uchovává samostatné heslo aplikace pro spouštění služby. Soukromé zálohy vytvořené za zastavené služby mohou tento soubor obsahovat. Chraň je jako přihlašovací údaje; neobsahují pouze hashe.

Přihlášení z DSM ověřuje existující relaci správce, aniž by požadovalo heslo DSM. Hostitelský spouštěč předává krátkodobý jednorázový grant a proxy před vstupem do kontejneru odstraňuje cookies a tokeny DSM. Relace MediaGrabberu je nezávislá na odhlášení DSM, platí nejvýše 12 hodin a lze ji ukončit tlačítkem Odhlásit v aplikaci. Logy DSM a reverzní proxy spravuje provozovatel NASu; mohou obsahovat informace o požadavcích a síti.

Online instalace získává součásti z distribučních služeb Dockeru, Debianu a PyPI. Kontroly a stahování kontaktují YouTube a jeho servery pro média a metadata. Okno O aplikaci může načíst veřejné údaje o vydání Windows z GitHubu. Tyto služby obdrží údaje nutné k požadavku včetně veřejné IP adresy. Samostatné odesílání telemetrie PJSoft aplikace nemá. Externí odkazy otevřené na tvůj pokyn se řídí podmínkami příslušných služeb.

Prohlížeč si pamatuje jazyk a volbu bublinkové nápovědy. Přihlášení udržuje relační cookie. Dialog Podpořit pouze poskytuje údaje pro dobrovolný bankovní převod; aplikace platbu neodesílá.

Záznamy zůstávají na NASu do odstranění. Smazání historie zachovává média, evidenci sledování a duplicit a soukromé zálohy. JSON export nepřenáší hesla, relace ani média, může ale obsahovat osobní odkazy, názvy, historii a cesty. Úplná soukromá záloha zahrnuje přihlašovací soubory. Při odinstalaci lze výslovně zvolit odstranění soukromého nastavení, historie, zdrojů, hesla a soukromých záloh. Bez zaškrtnutí této volby se tyto údaje zachovají pro opětovnou instalaci. Stažená média se zachovávají v obou případech. Aktualizace tuto volbu výmazu nikdy nepoužije.

Pokud sám odešleš diagnostiku e-mailem, vývojář získá údaje, které přiložíš. Neposílej hesla, soukromé klíče ani nepotřebné osobní údaje. Podpůrná komunikace se uchovává podle potřeby vyřízení požadavku a příslušných povinností; o přístup, opravu nebo výmaz požádej na uvedeném e-mailu podpory. Provozovatel, který aplikaci nasazuje pro další osoby, odpovídá za své nasazení, oprávnění a případné další požadované informace.
