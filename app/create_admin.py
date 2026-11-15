"""Admin fiók létrehozása parancssorból (még mielőtt az app nyilvános lenne).

Használat a Pi-n, a projekt mappájából:
    .venv/bin/python -m app.create_admin
"""
from __future__ import annotations

import getpass
import sys

from fastapi import HTTPException

from . import auth, db


def main() -> int:
    db.init_db()
    if auth.user_count() > 0:
        print("Már van felhasználó, így admin is van. Lépj be a webes felületen.")
        return 1
    username = input("Admin felhasználónév: ").strip()
    if len(username) < 2:
        print("Legalább 2 karakter kell.")
        return 1
    password = getpass.getpass("Jelszó (min. 6 karakter, nem látszik gépelés közben): ")
    if len(password) < 6:
        print("Legalább 6 karakteres jelszó kell.")
        return 1
    if getpass.getpass("Jelszó még egyszer: ") != password:
        print("A két jelszó nem egyezik.")
        return 1
    try:
        user = auth.create_user(username, password)
    except HTTPException as exc:
        print(exc.detail)
        return 1
    print(f"Kész! '{user['username']}' admin fiók létrehozva.")
    print("Mások sima (nem admin) fiókot regisztrálhatnak; ezt az Admin beállításokban kapcsolhatod ki.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
