# 🏷️ Akciók – budapesti akciófigyelő Raspberry Pi-re

Egy helyen mutatja a legdurvább akciókat a nagy budapesti láncoknál, gyorséttermeknél és játékboltokban. Van benne AI-os termékkereső (ingyenes Google Gemini kulccsal), bevásárlólista-optimalizáló, árfigyelő és push értesítés. Raspberry Pi-n fut, és Tailscale-en keresztül bárhonnan eléred.

## Mit tud?

| | Funkció |
|---|---|
| 🔥 **Top akciók** | Az összes forrás akciói egy listában. Kedvezmény, megtakarítás, ár vagy lejárat szerint rendezhető. Szűrhető boltra, kategóriára, árra és minimális kedvezményre. |
| ✨ **AI kereső** | Írd le, mit keresel (pl. *„olcsó mosógél 3000 Ft alatt”*). A Gemini kulcsszavakra bontja a kérést, átnézi a találatokat, és megindokolva kiválasztja a legjobbakat. |
| 🧺 **Bevásárlólista** | Soronként egy tétel. Megmutatja, melyik boltban a legolcsóbb a teljes kosár, és mennyi lenne vegyesen vásárolva. |
| ✅ **„Valódi akció?”** | Az app gyűjti az árelőzményt, és jelzi, ha az „eredeti ár” gyanúsan fel lett tornászva. |
| 🔔 **Figyelő** | Pl. „Nutella max 1500 Ft” vagy „Parkside -30%”. Ha megjelenik egy illő akció, szól az appban és push értesítésben is ([ntfy](https://ntfy.sh)). |
| 🍔 **Kuponok** | KFC és Burger King app-kuponok. A BK árait a Gemini olvassa ki a kuponképekről. A McDonald's (és bármi más) akciói kézzel is felvehetők. |
| 🎮 **Játékok** | Az Epic Games ingyenes játékai (most és hamarosan, visszaszámlálóval), a Steam legjobban értékelt akciós és ingyen megtartható játékai. |
| ⭐ **Mentett** | Kedvenc akciók, felhasználónként. |
| 👥 **Több felhasználó** | **Az első regisztrált felhasználó az admin.** Csak ő látja a beállításokat (API kulcs, források, felhasználók). |
| 📱 **PWA** | Telefonon a kezdőképernyőre tehető, és appként működik. Van világos és sötét téma. |

## Adatforrások

| Forrás | Boltok | Megjegyzés |
|---|---|---|
| [GVH Árfigyelő](https://arfigyelo.gvh.hu) | Spar, Aldi, Tesco, Penny, Auchan, Lidl, dm, Rossmann, Müller | Állami árösszehasonlító: kb. 21 000 bolti ár, normál, akciós és hűségkártyás árak |
| lidl.hu | Lidl | Az összes akció, a nem-élelmiszer termékek is (Parkside, Silvercrest stb.) |
| kfc.hu | KFC | App-kuponok árral |
| burgerking.hu | Burger King | App-kuponok (az ár a Gemini kulccsal olvasható ki) |
| Epic Games Store | Epic | Heti ingyenes játékok |
| Steam | Steam | Akciók EUR-ban, ≈ Ft átváltással |
| emag.hu | eMAG | **Kísérleti**: az eMAG captchával védekezik, ezt az app nem kerüli meg. Otthoni IP-ről lehet, hogy átengedi. |
| *kézi* | McDonald's és bármi más | A McDonald's ajánlatai csak a MyMcDonald's appban vannak, ezért kézzel vihetők fel |

A Spar, Aldi, Tesco és társaik saját oldalai blokkolják az automatikus lekérést, ezért ezek adatai az Árfigyelőből jönnek.

## Telepítés Raspberry Pi-re

Kell hozzá: Raspberry Pi 3/4/5 (vagy Zero 2 W), Raspberry Pi OS, internet és a már beállított Tailscale. Megfér a Pi-n már futó más projektek mellett (lásd lent).

```bash
git clone https://github.com/Goatterminator/Akci-k-app.git
```

```bash
cd Akci-k-app
```

```bash
bash deploy/install.sh
```

A telepítő létrehozza a Python környezetet, és `akciok` néven systemd szolgáltatásként elindítja az appot, ami bootoláskor magától indul. A végén kiírja a címeket.

### Ha már más projektek is futnak a Pi-n / Tailscale címen

A telepítő úgy készült, hogy **ne zavarja a meglévő projektjeidet**:

- **Port:** ha a 8080 foglalt, automatikusan az első szabad portot választja (8080–8099), és elmenti a `.env`-be, így frissítéskor is ugyanaz marad. Ha magad akarod megadni:

  ```bash
  PORT=8090 bash deploy/install.sh
  ```

- **Tailscale HTTPS:** a telepítő a `tailscale serve` beállításhoz **nem nyúl**, csak kiírja a mostanit, és javasol egy külön HTTPS portot.

Nézd meg, mi fut már:

```bash
sudo ss -ltnp
```

```bash
sudo tailscale serve status
```

Ezután nyisd meg a böngészőben a `http://<pi-tailscale-neve>:<port>` címet (a portot a telepítő kiírja), és **hozd létre az admin fiókot** (az első regisztráció az admin).

### HTTPS Tailscale-en (ajánlott, külön porton)

Az app telefonra telepítéséhez (PWA) HTTPS kell. Mivel a Tailscale címeden már vannak projektek, az appot **külön HTTPS porton** tedd ki, hogy a meglévő (443-as) beállításod megmaradjon. Az alábbi példában a 8080 helyére a telepítő által kiírt portot írd:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8080
```

Ezután az app a `https://<pi-neve>.<tailnet>.ts.net:8443` címen érhető el, csak a saját Tailscale hálózatodból.

> ⚠️ **Ne** futtasd a sima `sudo tailscale serve --bg 8080` parancsot: az a 443-as HTTPS portot állítja be, és lecserélheti a másik projekted beállítását. Ha a 8443 is foglalt (`tailscale serve status`), válassz másikat, pl. `--https=10000`.

A beállítás visszavonása (csak ezt az egy portot törli):

```bash
sudo tailscale serve --https=8443 off
```

Telefonon: Chrome menü → *Hozzáadás a kezdőképernyőhöz*, Safari → *Megosztás → Főképernyőhöz adás*.

> A böngésző sütijei egy gépnévhez tartoznak, nem porthoz. Az app saját, egyedi nevű sütit (`akciok_session`) használ, így nem akad össze a másik projektjeid bejelentkezésével.

### Frissítés

```bash
bash deploy/update.sh
```

### Hasznos parancsok

```bash
journalctl -u akciok -f
```

```bash
sudo systemctl restart akciok
```

### Docker (alternatíva)

```bash
docker compose up -d --build
```

## Gemini API kulcs (ingyenes)

1. Nyisd meg a <https://aistudio.google.com/apikey> oldalt, és kattints a **Create API key** gombra.
2. Az appban: **Admin beállítások → Gemini AI**, másold be a kulcsot, majd **Kapcsolat tesztelése**.

**Biztonság:**
- A kulcs csak a Pi-n tárolódik (`data/akciok.db`). A `data/` mappa és a `.env` a `.gitignore`-ban van, ezért **nem kerül fel a GitHubra**.
- A felület soha nem küldi vissza a teljes kulcsot, csak az utolsó 4 karakterét.
- Ha kiszivárogna, az AI Studióban egy kattintással letilthatod.

> ⚠️ Az AI keresőbe ne írj személyes adatot. Az ingyenes kulcsnál a Google a beküldött szöveget felhasználhatja a szolgáltatás fejlesztésére.

Kulcs nélkül is működik minden. Ilyenkor az AI kereső egyszerű kulcsszavas keresésre vált, és a BK kuponoknál nem lesz ár.

## Push értesítés telefonra (ntfy)

1. Telepítsd az ingyenes **ntfy** appot (Androidon és iOS-en is elérhető, lásd <https://ntfy.sh>).
2. Iratkozz fel egy egyedi, nehezen kitalálható témára, pl. `akciok-x7k2p9`.
3. Az appban: **Profil → Push értesítés**, írd be ugyanazt, majd **Teszt értesítés**.

Minden felhasználó a saját témáját állítja be, így csak a saját figyelőiről kap értesítést.

## Erőforrásigény

| | |
|---|---|
| RAM, amikor csak fut | kb. 50–60 MB |
| RAM egy teljes frissítés alatt | kb. 70–100 MB (csúcs) |
| Teljes frissítés ideje | kb. 2–3 perc (6 óránként, állítható) |
| Lemez | kb. 16 MB az első frissítés után. Lassan nő, mert csak az árváltozásokat menti, és a régi adatokat törli. |

## Jogi megjegyzés

Az app **privát használatra** készült. Nyilvánosan, belépés nélkül elérhető árakat olvas, ritka (alapból 6 órás) és kíméletes lekéréssel. A captchával vagy más módon védett oldalakat nem kerüli meg. A termékképeket nem másolja, csak az eredeti helyükre linkel. Ha nyilvános szolgáltatást csinálnál belőle, használd a boltok hivatalos API-jait vagy affiliate programjait, és kérj jogi tanácsot.

Az árak tájékoztató jellegűek. Vásárlás előtt ellenőrizd őket a bolt oldalán.

## Fejlesztés

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
```

```bash
.venv/bin/python -m pytest -q
```

```bash
AUTO_REFRESH=0 .venv/bin/python -m app.main
```

Felépítés:

```
app/
  main.py            FastAPI szerver, API végpontok
  auth.py            felhasználók, munkamenetek (az első felhasználó admin)
  db.py              SQLite séma és segédfüggvények
  categories.py      egységes kategóriák, boltok, szövegnormalizálás
  scrapers/          egy fájl forrásonként (arfigyelo, lidl, fastfood, games, emag)
  services/
    refresh.py       frissítés, tárolás, árelőzmény, figyelők, ütemező
    search.py        akciólista, keresés, "valódi akció?", bevásárlólista
    gemini.py        Gemini REST hívások (AI kereső, kuponár-felismerés)
    notify.py        ntfy push értesítés
static/              a webes felület (vanilla JS, build lépés nélkül)
deploy/              Pi telepítő és frissítő script
tests/               tesztek valódi (megvágott) forrásválaszokkal
```

**Új forrás hozzáadása:** írj egy `Scraper` alosztályt az `app/scrapers/` mappába, amelynek `fetch()` metódusa `Deal` listát ad vissza, majd vedd fel a `SCRAPERS` listába az `app/scrapers/__init__.py` fájlban.
