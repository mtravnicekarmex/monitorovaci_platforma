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
- Tailscale Serve poskytuje funkcni soukromy HTTPS pristup.

## Bezpecnostni pravidla

- Porty FastAPI `8000` a Streamlit `8001` se nesmi publikovat primo do internetu.
- Verejny provoz musi vstupovat pouze pres Caddy.
- Verejny port `8080` se vypne az po uspesnem overeni HTTPS na portu `443`.
- Produkcni API token secret nesmi byt ulozen jako pevna vyvojova hodnota ve spoustecim BAT souboru.
- Uvicorn nesmi byt ve verejnem provozu spusten s `--reload`.
- Pred zverejnenim se musi overit hesla a ochrana prihlasovaciho endpointu.
- Pri kazdem kroku musi zustat funkcni Tailscale jako zalozni pristup.

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

- [ ] Odstranit pevne zapsany vyvojovy `API_TOKEN_SECRET` ze `start_api_dashboard.bat`.
- [ ] Vygenerovat dlouhy nahodny produkcni `API_TOKEN_SECRET`.
- [ ] Ulozit secret mimo verzovany kod, napr. do lokalniho `.env` nebo zabezpeceneho systemoveho prostredi.
- [ ] Odstranit `--reload` ze spousteni Uvicorn.
- [ ] Overit, ze `.env` a dalsi soubory se secrets nejsou verzovane ani verejne dostupne.
- [ ] Overit silna hesla vsech aktivnich dashboard uzivatelu.
- [ ] Doplnit omezeni pokusu o prihlaseni nebo jinou ochranu proti hrube sile.
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

- [ ] Overit automaticky start Caddy, FastAPI, Streamlit a scheduleru po restartu.
- [ ] Overit obnoveni dashboardu po restartu SERVER4A.
- [ ] Zavest zalohovani Caddy datoveho adresare a lokalni konfigurace.
- [ ] Zavest kontrolu dostupnosti HTTPS endpointu.
- [ ] Zkontrolovat a pravidelne aktualizovat Caddy, Tailscale a Python zavislosti.
- [ ] Zdokumentovat navratovy postup pri vypadku verejneho HTTPS.

## Navratovy postup

Pokud verejne HTTPS po zmene nefunguje:

1. Pouzit Tailscale Serve pro servisni pristup.
2. Obnovit posledni validni `C:\Program Files\Caddy\Caddyfile`.
3. Validovat konfiguraci pres `C:\Program Files\Caddy\caddy.exe`.
4. Reloadovat Caddy pres admin endpoint `127.0.0.1:2019`.
5. Zkontrolovat, ze FastAPI bezi na `127.0.0.1:8000`.
6. Zkontrolovat, ze Streamlit bezi na `127.0.0.1:8001`.
7. Docasny port `8080` odstranit az po potvrzeni funkcniho HTTPS.

## Prvni dalsi krok

Zjistit:

1. Zda je k dispozici verejna domena.
2. Jeji presny nazev.
3. Pozadovany hostname dashboardu.
4. U koho je spravovano verejne DNS.
