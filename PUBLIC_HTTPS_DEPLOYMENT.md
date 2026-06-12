# Verejne HTTPS nasazeni dashboardu

Datum vytvoreni: 2026-06-10

## Cil

Vystavit aktivni Streamlit dashboard a souvisejici FastAPI bezpecne na internet pres verejne duveryhodne HTTPS.

Planovana architektura:

```text
dashboard.<verejna-domena>
  -> verejna IP 77.95.46.168
  -> router: TCP 80/443
  -> SERVER4A: 192.168.2.249
  -> Caddy
  -> /api/*: FastAPI na 127.0.0.1:8000
  -> ostatni pozadavky: Streamlit na 127.0.0.1:8001
```

Tailscale Serve zustane behem pripravy a po nasazeni jako neveřejny servisni a zalozni pristup.

## Aktualni stav

- Verejna IP: `77.95.46.168`
- Internetove rozhrani SERVER4A: `192.168.2.249`
- Interni ARMEX rozhrani SERVER4A: `192.168.3.249`
- Stavajici verejny pristup: `http://77.95.46.168:8080`
- FastAPI nasloucha jen na `127.0.0.1:8000`.
- Streamlit nasloucha jen na `127.0.0.1:8001`.
- Caddy je nainstalovan v `C:\Program Files\Caddy`.
- Aktivni konfigurace je `C:\Program Files\Caddy\Caddyfile`.
- Caddy zprostredkovava `/api/*` do FastAPI a ostatni provoz do Streamlit.
- Verejna stranka zobrazuje primo standardni Streamlit login bez druheho
  browser Basic Auth dialogu.
- FastAPI omezuje neuspesne pokusy na `/api/v1/auth/login` podle uctu a
  duveryhodne klientske IP.
- Tailscale Serve poskytuje funkcni soukromy HTTPS pristup.
- `start_api_dashboard.bat` spousti Windows Planovac uloh pri spusteni systemu.
  Procesy se proto obnovi bez prihlaseni uzivatele do Windows.

## Spousteni a obnova procesu

Produkci spousti Windows Planovac uloh:

- Program: `start_api_dashboard.bat`
- Aktivacni udalost: `Pri spusteni systemu`
- Ucel: spustit FastAPI, Streamlit, scheduler a Caddy bez nutnosti
  interaktivniho prihlaseni uzivatele.

Procesy bezici z teto naplanovane ulohy jsou v neinteraktivni relaci. Jejich
konzolova okna nejsou pozdeji dostupna pro beznou obsluhu. Soucasny podporovany
postup pro obnoveni cele sady procesu je restart cele Windows stanice.

Provozni pravidla:

1. Nespoustet rucne dalsi kopii `start_api_dashboard.bat`, pokud planovana sada
   procesu stale bezi.
2. Pri zmene launcheru nebo jeho startovacich argumentu pocitat s restartem
   stanice, aby Planovac uloh spustil novou konfiguraci.
3. Pred kazdym restartem zapsat do `SESSION_NOTES.md` predrestartovy handoff
   podle sablony nize.
4. Po restartu vzdy overit FastAPI, Streamlit, scheduler, Caddy, listenery a
   verejne HTTPS podle restart checklistu.
5. Samostatne ukoncovani a znovuspousteni produkcnich procesu nepovazovat za
   podporovany recovery postup, dokud nebude provozni model zmenen.

### Povinny predrestartovy handoff

Pred restartem se musi zapsat:

1. Datum a cas, duvod restartu a aktualni cil prace.
2. Co je dokonceno, co zustava otevrene a co ma dalsi relace udelat jako prvni.
3. `git status --short`, relevantni zmenene soubory a informace, zda jsou zmeny
   nasazene do runtime umisteni.
4. Citlive nebo provozni soubory, ktere se nesmi tisknout, menit, mazat ani
   commitovat.
5. Ocekavane procesy po restartu:
   - FastAPI/Uvicorn
   - Streamlit
   - scheduler `main.py`
   - Caddy
6. Ocekavane listenery:
   - FastAPI `127.0.0.1:8000`
   - Streamlit `127.0.0.1:8001`
   - Caddy TCP `80`, `443`
   - Caddy admin `127.0.0.1:2019`
7. Ocekavany scheduler lock, heartbeat, posledni/nejblizsi job a stav metrik.
8. Ocekavanou Caddy konfiguraci, shodu tracked/runtime souboru a verejne
   smerovani.
9. Presne post-restart kontroly a ocekavane HTTP statusy.
10. Kontroly specificke pro zmenu, kvuli ktere se restart provadi.

Restart se nema zahajit ani doporucit, dokud tento handoff neni zapsany.
Po restartu se do `SESSION_NOTES.md` doplni skutecny stav a vsechny odchylky.

## Bezpecnostni pravidla

- Porty FastAPI `8000` a Streamlit `8001` se nesmi publikovat primo do internetu.
- Verejny provoz musi vstupovat pouze pres Caddy.
- Verejny port `8080` se vypne az po uspesnem overeni HTTPS na portu `443`.
- Produkcni API token secret nesmi byt ulozen jako pevna vyvojova hodnota ve spoustecim BAT souboru.
- Uvicorn nesmi byt ve verejnem provozu spusten s `--reload`.
- Pred zverejnenim se musi overit hesla a ochrana prihlasovaciho endpointu.
- Pri kazdem kroku musi zustat funkcni Tailscale jako zalozni pristup.
- Uvicorn prijima forwarded klientskou IP pouze od Caddy na `127.0.0.1`.
- Aplikace necte raw `X-Forwarded-For`; pouziva klientskou IP z duveryhodneho
  request scope.

## Checklist

### 1. Verejna domena

- [ ] Vybrat nebo zaregistrovat verejnou domenu.
- [ ] Vybrat konecny hostname, napr. `dashboard.example.cz`.
- [ ] Potvrdit pristup ke sprave verejneho DNS.

Podminka dokonceni:

```text
Je znam konecny verejny hostname a mame pristup k jeho DNS zone.
```

### 2. Zabezpeceni aplikace pred zverejnenim

- [x] Odstranit pevne zapsany vyvojovy `API_TOKEN_SECRET` ze `start_api_dashboard.bat`.
- [x] Vygenerovat dlouhy nahodny produkcni `API_TOKEN_SECRET`.
- [x] Ulozit secret mimo verzovany kod, napr. do lokalniho `.env` nebo zabezpeceneho systemoveho prostredi.
- [ ] Odstranit `--reload` ze spousteni Uvicorn.
- [ ] Overit, ze `.env` a dalsi soubory se secrets nejsou verzovane ani verejne dostupne.
- [ ] Overit silna hesla vsech aktivnich dashboard uzivatelu.
- [x] Doplnit omezeni pokusu o prihlaseni nebo jinou ochranu proti hrube sile.
- [ ] Zkontrolovat delku prihlasovaci relace/tokenů pro verejny provoz.
- [ ] Overit, ze administracni a datove endpointy vyzaduji spravne opravneni.

Podminka dokonceni:

```text
Aplikace nepouziva vyvojovy secret ani Uvicorn reload a prihlaseni je chraneno proti opakovanym pokusum.
```

### 3. Verejne DNS

- [ ] Vytvorit verejny `A` zaznam:

```text
dashboard.example.cz -> 77.95.46.168
```

- [ ] Nepridavat `AAAA` zaznam, pokud IPv6 neni vedome nakonfigurovano.
- [ ] Overit propagaci pres verejne DNS resolvery.

Overeni:

```powershell
Resolve-DnsName dashboard.example.cz -Server 1.1.1.1
Resolve-DnsName dashboard.example.cz -Server 8.8.8.8
```

Podminka dokonceni:

```text
Verejne DNS resolvery vraceji 77.95.46.168.
```

### 4. Router a firewall

- [ ] Na internetovem routeru presmerovat `WAN TCP 80` na `192.168.2.249:80`.
- [ ] Na internetovem routeru presmerovat `WAN TCP 443` na `192.168.2.249:443`.
- [ ] Povolit ve Windows Firewall prichozi TCP `80` a `443` pro odpovidajici sitovy profil.
- [ ] Neotvirat verejne porty `8000` ani `8001`.
- [ ] Zatim ponechat `8080` pouze jako docasnou navratovou cestu.

Podminka dokonceni:

```text
Porty 80 a 443 jsou z internetu smerovany na Caddy na SERVER4A.
```

### 5. Produkcni Caddy konfigurace

- [ ] Pridat verejny hostname do `Caddyfile`.
- [ ] Pro verejny hostname nepouzit `tls internal`.
- [ ] Zachovat same-origin routovani `/api/*` do FastAPI.
- [ ] Zachovat ostatni provoz do Streamlit.
- [ ] Nastavit kontaktni e-mail pro ACME ucet.
- [ ] Validovat konfiguraci.
- [ ] Reloadovat Caddy.
- [ ] Overit vydani a automatickou spravu verejne duveryhodneho certifikatu.

Predpokladana konfigurace:

```caddyfile
dashboard.example.cz {
	import dashboard_proxy
}
```

Overeni:

```powershell
& "C:\Program Files\Caddy\caddy.exe" validate --config "C:\Program Files\Caddy\Caddyfile" --adapter caddyfile
& "C:\Program Files\Caddy\caddy.exe" reload --config "C:\Program Files\Caddy\Caddyfile" --adapter caddyfile --address 127.0.0.1:2019
```

Podminka dokonceni:

```text
https://dashboard.example.cz pouziva verejne duveryhodny certifikat bez varovani prohlizece.
```

### 6. Funkcni a bezpecnostni overeni

- [ ] Testovat z mobilnich dat, nikoliv jen z lokalni site.
- [ ] Overit automaticke presmerovani HTTP na HTTPS.
- [ ] Overit prihlaseni a odhlaseni.
- [ ] Overit obnovení stranky a Streamlit websocket.
- [ ] Overit FastAPI volani pres stejnou domenu `/api/*`.
- [ ] Overit mapove vrstvy a autorizovane fotografie.
- [ ] Overit mobilni geolokaci.
- [ ] Overit uzivatelska, administracni, sekcni a zarizeni opravneni.
- [ ] Overit, ze porty `8000` a `8001` nejsou dostupne z internetu.
- [ ] Zkontrolovat Caddy, FastAPI a Streamlit logy.

Podminka dokonceni:

```text
Vsechny hlavni dashboard workflow funguji pres verejne HTTPS a interni sluzby nejsou primo publikovane.
```

### 7. Uzavreni stareho HTTP pristupu

- [ ] Odstranit presmerovani verejneho portu `8080` na routeru.
- [ ] Odebrat nepotrebne verejne firewall pravidlo pro `8080`.
- [ ] Rozhodnout, zda lokalni Caddy listener `:8080` zustane pouze pro LAN, nebo se odstrani.
- [ ] Overit, ze `http://77.95.46.168:8080` uz neni z internetu dostupne.
- [ ] Aktualizovat provozni dokumentaci a pouzivane odkazy.

Podminka dokonceni:

```text
Verejny pristup je mozny pouze pres HTTPS na konecnem hostname.
```

### 8. Provozni dokonceni

- [x] Overit automaticky start Caddy, FastAPI, Streamlit a scheduleru po restartu.
- [x] Overit obnoveni dashboardu po restartu SERVER4A.
- [ ] Zavest zalohovani Caddy datoveho adresare a lokalni konfigurace.
- [ ] Zavest kontrolu dostupnosti HTTPS endpointu.
- [ ] Zkontrolovat a pravidelne aktualizovat Caddy, Tailscale a Python zavislosti.
- [x] Zdokumentovat navratovy postup pri vypadku verejneho HTTPS.

## Navratovy postup

Pokud verejne HTTPS po zmene nefunguje:

1. Pouzit Tailscale Serve pro servisni pristup.
2. Pokud je problem pouze v Caddy konfiguraci, obnovit posledni validni
   `C:\Program Files\Caddy\Caddyfile`, validovat ji a reloadovat Caddy pres
   admin endpoint `127.0.0.1:2019`.
3. Pokud je nutne obnovit aplikacni procesy nebo celou runtime sadu,
   restartovat Windows stanici. Toto je soucasny podporovany recovery postup.
4. Po restartu zkontrolovat FastAPI na `127.0.0.1:8000`, Streamlit na
   `127.0.0.1:8001`, scheduler heartbeat, Caddy listenery a verejne HTTPS.
5. Nespoustet rucne druhou sadu procesu vedle procesu spustenych Planovacem
   uloh.

## Ochrana prihlaseni

FastAPI omezuje `/api/v1/auth/login` soucasne podle normalizovaneho
uzivatelskeho jmena a klientské IP. Po peti neuspesnych pokusech pro jeden ucet
zacina docasny lockout 30 sekund a pri dalsich selhanich roste az na 15 minut.
Po dvaceti neuspesnych pokusech z jedne IP behem 15 minut se IP docasne blokuje
na 15 minut.

Caddy jiz nevyzaduje druhou sadu prihlasovacich udaju. Soubory
`C:\ProgramData\monitorovaci_platforma\caddy-dashboard-auth.env` a
`C:\ProgramData\monitorovaci_platforma\dashboard-proxy-credentials.txt` jsou
vyrazene z provozu, ale nadale se povazuji za citlive. Nesmi se tisknout,
commitovat ani mazat bez samostatneho schvaleni.

### Authentication audit log

FastAPI zapisuje autentizacni a uctove bezpecnostni udalosti jako JSONL do:

```text
C:\ProgramData\monitorovaci_platforma\logs\auth_audit.jsonl
```

Soubor se denne rotuje a standardne uchovava 90 zaloh. Cestu a retenci lze
zmenit pres `AUTH_AUDIT_LOG_PATH` a `AUTH_AUDIT_RETENTION_DAYS`. Adresar musi
zustat mimo verejne servirovane cesty a musi dedit omezeny ACL ProgramData.

Audit obsahuje normalizovany identifikator uctu, duveryhodnou zdrojovou IP,
vysledek, kategorii duvodu a bezpecne citace. Nesmi obsahovat hesla, bearer
tokeny ani hodnoty cookies. Alert zaznamy se severity `warning` vznikaji pri:

- vstupu uctu do lockoutu po 5 neuspesnych pokusech,
- IP lockoutu po 20 neuspesnych pokusech napric ucty,
- 3 neuspesnych pokusech na administratorsky ucet behem 15 minut.

### Password policy

Nove nebo menene dashboardove heslo musi mit 15 az 1024 znaku. Mezery,
Unicode, dlouhe passphrase a hodnoty z password manageru jsou povolene.
Nevyzaduje se kombinace velkych a malych pismen, cislic a symbolu ani
periodicka zmena hesla.

Slaba hesla jsou odmitana pres lokalni soubor:

```text
moduly\apps\dashboard\password_blocklist.txt
```

Hesla se pred hashovanim normalizuji do Unicode NFC a ukladaji jako
PBKDF2-HMAC-SHA256 s 600 000 iteracemi. Starsi platne PBKDF2 hashe se po
uspesnem prihlaseni automaticky prehashuji. Hromadny reset existujicich hesel
neni vyzadovan.

Nasazeni tracked konfigurace do `C:\Program Files\Caddy` se provadi z
elevovaneho PowerShellu:

```powershell
.\scripts\deploy_caddy_runtime.ps1
```

Skript pred kopii validuje konfiguraci, vytvori timestampovanou zalohu a pri
selhani reloadu obnovi predchozi runtime konfiguraci.

Rollback:

1. Obnovit posledni validni zalohu `Caddyfile`.
2. Validovat a reloadovat Caddy.
3. Overit dashboard HTTP 200 a FastAPI HTTP 401 na chranene API trase bez
   bearer tokenu.
4. Overit, ze neuspesne login pokusy vraceji generickou chybu a po limitu HTTP
   429 s `Retry-After`.

## Prvni dalsi krok

Zjistit:

1. Zda je k dispozici verejna domena.
2. Jeji presny nazev.
3. Pozadovany hostname dashboardu.
4. U koho je spravovano verejne DNS.
