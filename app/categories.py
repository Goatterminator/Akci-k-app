"""Egységes kategóriák, boltok és szövegnormalizálás."""
from __future__ import annotations

import re
import unicodedata

CATEGORIES: list[dict[str, str]] = [
    {"key": "elelmiszer", "label": "Élelmiszer", "icon": "🥦"},
    {"key": "ital", "label": "Italok", "icon": "🥤"},
    {"key": "drogeria", "label": "Drogéria", "icon": "🧴"},
    {"key": "haztartas", "label": "Háztartás", "icon": "🧽"},
    {"key": "baba", "label": "Baba", "icon": "🍼"},
    {"key": "otthon", "label": "Otthon & konyha", "icon": "🏠"},
    {"key": "barkacs", "label": "Barkács & kert", "icon": "🛠️"},
    {"key": "sport", "label": "Sport & szabadidő", "icon": "⚽"},
    {"key": "ruha", "label": "Ruházat", "icon": "👕"},
    {"key": "elektronika", "label": "Elektronika", "icon": "💻"},
    {"key": "gyorsetterem", "label": "Gyorsétterem", "icon": "🍔"},
    {"key": "jatek", "label": "Videójáték", "icon": "🎮"},
    {"key": "egyeb", "label": "Egyéb", "icon": "📦"},
]
CATEGORY_KEYS = {c["key"] for c in CATEGORIES}

# Bolt metaadatok a felülethez (szín = márkaszín jellegű kiemelés).
# A láncok appjának megnyitásához (kuponok). A kfc.hu és a BK app-linkje (Branch) a láncok
# saját appjához van regisztrálva (Android App Links / iOS Universal Links), így telefonon
# az appot nyitják meg. Konkrét kuponra mutató nyilvános linket egyik lánc sem ad.
STORE_APPS: dict[str, dict[str, str]] = {
    "KFC": {
        "name": "KFC",
        "link": "https://kfc.hu/kuponok",
        "android_package": "com.kfc_hu",
        "play": "https://play.google.com/store/apps/details?id=com.kfc_hu",
        "appstore": "https://apps.apple.com/hu/app/kfc-magyarorsz%C3%A1g/id1358657152",
    },
    "Burger King": {
        "name": "Burger King",
        "link": "https://burgerkinghu.app.link/yQBrwHwcqNb",  # a burgerking.hu saját kuponlinkje
        "android_package": "com.expremio.burgerking",
        "play": "https://play.google.com/store/apps/details?id=com.expremio.burgerking",
        "appstore": "https://apps.apple.com/hu/app/burger-king/id1427220042",
    },
}

STORES: dict[str, dict[str, str]] = {
    "Lidl": {"color": "#0050aa"},
    "Spar": {"color": "#e2001a"},
    "Aldi": {"color": "#00205b"},
    "Tesco": {"color": "#00539f"},
    "Penny": {"color": "#cd1719"},
    "Auchan": {"color": "#e30613"},
    "dm": {"color": "#002878"},
    "Rossmann": {"color": "#c3002f"},
    "Müller": {"color": "#f39200"},
    "KFC": {"color": "#a3080c"},
    "Burger King": {"color": "#d62300"},
    "McDonald's": {"color": "#da291c"},
    "eMAG": {"color": "#005eb8"},
    "Steam": {"color": "#1b2838"},
    "Epic Games": {"color": "#2a2a2a"},
}


def normalize(text: str | None) -> str:
    """Kisbetűs, ékezet nélküli, egyszerűsített szöveg kereséshez."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9%.,]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Kulcsszó alapú besorolás olyan forrásokhoz, ahol nincs jó kategória-adat.
_KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("ital", ("ital", "udito", "sor ", "bor ", "viz", "gyumolcsle", "kave", "tea ",
              "energiaital", "pezsgo", "palinka", "whisky", "vodka")),
    ("drogeria", ("drogeria", "szepseg", "kozmetik", "sampon", "tusfurdo", "fogkrem", "dezodor",
                  "higienia", "testapol", "parfum", "smink")),
    ("haztartas", ("haztartas", "mososzer", "tisztito", "oblito", "papirtorlo", "wc papir",
                   "mosogato")),
    ("baba", ("baba", "pelenka", "bebi", "tapszer")),
    ("barkacs", ("barkacs", "kert", "szerszam", "parkside", "furo", "fureszt", "furesz",
                 "csavar", "akkus", "lancfuresz", "funyiro")),
    ("sport", ("sport", "szabadido", "kerekpar", "fitnesz", "crivit", "kemping", "jatek & ")),
    ("ruha", ("ruha", "divat", "cipo", "bakancs", "polo", "nadrag", "kabat", "zokni", "esmara",
              "livergy", "pulover", "dzseki")),
    ("elektronika", ("elektronika", "laptop", "telefon", "okostelefon", "tv ", "televizio",
                     "monitor", "fulhallgato", "tablet", "konzol", "silvercrest", "nyomtato",
                     "hangszoro", "okosora", "processzor", "videokartya", "ssd")),
    ("otthon", ("otthon", "konyha", "lakas", "butor", "agynemu", "edeny", "serpenyo", "lampa",
                "livarno", "ernesto", "dekor")),
    ("elelmiszer", ("elelmiszer", "etel", "food", "zoldseg", "gyumolcs", "hus", "sajt", "tej",
                    "pekaru", "kenyer", "edesseg", "csokolade", "fagyasztott")),
]


_NORMALIZED_RULES: list[tuple[str, tuple[str, ...]]] = [
    # A szóközre végződő kulcsszó csak egész szóra illeszkedik (pl. "sor " ne illeszkedjen "sorozat"-ra).
    (key, tuple(normalize(w) + (" " if w.endswith(" ") else "") for w in words if normalize(w)))
    for key, words in _KEYWORD_RULES
]


def guess_category(*texts: str | None, default: str = "egyeb") -> str:
    """Az első olyan kategória, amelynek valamelyik kulcsszavával kezdődik egy szó a szövegben."""
    blob = " " + " ".join(normalize(t) for t in texts if t) + " "
    for key, words in _NORMALIZED_RULES:
        if any(" " + w in blob for w in words):
            return key
    return default
