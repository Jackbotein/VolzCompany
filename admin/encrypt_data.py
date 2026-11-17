#!/usr/bin/env python3
"""Encrypt EduNestRadar data for upload.

Usage:
  pip install cryptography
  python3 encrypt_data.py --user VolzCompany --password Irvine

Reads  source-data/edunest-data.json
Writes ../site/assets/edunest-data.js  (upload this file to the server)

The login page derives an AES-256 key from the username and password, so the
data on the server is unreadable without them. Change the password by running
this script again with a new --password and re-uploading edunest-data.js.
"""
import argparse, base64, json, os, pathlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ITER = 310000
here = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--user", required=True)
ap.add_argument("--password", required=True)
ap.add_argument("--src", default=str(here / "source-data" / "edunest-data.json"))
ap.add_argument("--out", default=str(here.parent / "site" / "assets" / "edunest-data.js"))
a = ap.parse_args()

secret = (a.user.strip().lower() + ":" + a.password).encode("utf-8")
salt, iv = os.urandom(16), os.urandom(12)
key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(secret)
plain = json.dumps(json.load(open(a.src, encoding="utf-8")), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
ct = AESGCM(key).encrypt(iv, plain, None)
b64 = lambda b: base64.b64encode(b).decode()
payload = {"v": 1, "iter": ITER, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)}
pathlib.Path(a.out).write_text("window.EDUNEST_ENC=" + json.dumps(payload) + ";\n", encoding="utf-8")
print("Wrote", a.out)
