#!/usr/bin/env python3
"""Run EduNestRadar scanning nonstop on any always-on machine (VPS, office server).

Alternative to the GitHub Actions schedule. Each cycle: fill stakeholders, scan California,
discover other states, find high-growth institutions, fill new stakeholders, encrypt and
(optionally) upload. Then it starts again.

  export ANTHROPIC_API_KEY=... EDUNEST_USER=VolzCompany EDUNEST_PASSWORD=...
  # optional upload: FTP_HOST FTP_USER FTP_PASS FTP_DIR (e.g. public_html/edunestradar)
  python3 scanner/run_forever.py
"""
import ftplib
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAUSE = int(os.environ.get("PAUSE_MINUTES", "5"))
STEPS = ["scanner/enrich.py", "scanner/scan.py", "scanner/discover.py", "scanner/growth.py", "scanner/enrich.py"]


def upload():
    host = os.environ.get("FTP_HOST")
    if not host:
        return
    with ftplib.FTP_TLS(host) as ftp:
        ftp.login(os.environ["FTP_USER"], os.environ["FTP_PASS"])
        ftp.prot_p()
        ftp.cwd(os.environ.get("FTP_DIR", "."))
        try:
            ftp.cwd("assets")
        except ftplib.error_perm:
            ftp.mkd("assets"); ftp.cwd("assets")
        with open(ROOT / "site/assets/edunest-data.js", "rb") as f:
            ftp.storbinary("STOR edunest-data.js", f)
    print("Uploaded edunest-data.js")


while True:
    for step in STEPS:
        print(f"== {step}", flush=True)
        subprocess.run([sys.executable, str(ROOT / step)], cwd=ROOT)
    subprocess.run([sys.executable, str(ROOT / "admin/encrypt_data.py"), "--user", os.environ["EDUNEST_USER"],
                    "--password", os.environ["EDUNEST_PASSWORD"]], cwd=ROOT, check=True)
    try:
        upload()
    except Exception as e:
        print(f"Upload failed: {e}")
    time.sleep(PAUSE * 60)
