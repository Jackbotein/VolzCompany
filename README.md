# EduNestRadar — A Copia Rentals technology

Education housing opportunity intelligence, prepared for Volz Company.
Sign-in: username `VolzCompany`, password `Irvine`.

## What's in this package

| Folder | Goes on the website? | Contents |
|---|---|---|
| `site/` | **Yes** | The web app (`index.html`), encrypted data (`assets/edunest-data.js`), `.htaccess`, `robots.txt` |
| `scanner/` | No | `scan.py`, the automated scanner, and `institutions.json` (all 1,084 UC, CSU, community college and K-12 institutions) |
| `admin/` | No, keep private | Unencrypted data (`source-data/edunest-data.json`) and `encrypt_data.py` |
| `.github/workflows/scan.yml` | No | The nightly job that scans, encrypts and uploads |

## Quick install (no auto-update)

Upload everything inside `site/` to a folder on copiarentals.com (for example `public_html/edunestradar/`) and open it over **https**.

## Turn on auto-update (one-time setup, about 20 minutes)

The site updates itself every night: a GitHub Actions job runs the scanner, re-encrypts the data and uploads it to your server.

1. **Create a private GitHub repository** and upload the whole `EduNestRadar` folder to it (including the hidden `.github` folder). Keep the repository private, since `admin/` holds unencrypted data.
2. **Get an Anthropic API key** at console.anthropic.com. An organization admin must turn on **web search** in the Console's privacy/feature settings, or the scanner can't search.
3. In the repository, go to **Settings → Secrets and variables → Actions** and add these **secrets**:

   | Secret | Value |
   |---|---|
   | `ANTHROPIC_API_KEY` | your API key |
   | `EDUNEST_USER` | `VolzCompany` |
   | `EDUNEST_PASSWORD` | `Irvine` (or a stronger passphrase) |
   | `FTP_SERVER` | your host's FTP server, e.g. `ftp.copiarentals.com` |
   | `FTP_USERNAME` | FTP username |
   | `FTP_PASSWORD` | FTP password |
   | `FTP_SERVER_DIR` | folder on the server, ending in `/`, e.g. `public_html/edunestradar/` |

   Optional **variables** (same page, Variables tab): `BATCH_SIZE` (default 40), `ENRICH_LIMIT` (default 60), `SYSTEMS` (e.g. `K12`), `EDUNEST_MODEL` (default `claude-sonnet-5-5`).
4. Go to **Actions → EduNestRadar nightly scan → Run workflow** to test it. After it finishes, reload the site; the footer shows the last scan date and new opportunities are tagged **New**.

If your host doesn't offer FTP (Netlify, Cloudflare Pages, Vercel), leave the FTP secrets blank and connect that service to the repository with `site` as the publish folder. It redeploys automatically after each nightly commit.

## Coverage: 12 states

California is scanned institution by institution (all 1,084 UC, CSU, community college and K-12 institutions). Oregon, Washington, Nevada, Arizona, Utah, Illinois, Iowa, Wisconsin, Minnesota, Indiana and Missouri are covered by `scanner/discover.py`, which each night runs the state-and-sector sweeps (universities, community/technical colleges, K-12 districts) done longest ago. `SWEEPS_PER_RUN` (default 6) sets how many; all 33 sweeps cycle about every six days. Set the `STATES` variable (e.g. `OR,WA`) to focus on some states. Governing bodies per state are listed in `scanner/states.json`.

## Stakeholders

Each opportunity lists only these three people, one per role:

| Role | Colleges and universities | K-12 districts |
|---|---|---|
| President | President, or campus/district chancellor | Superintendent |
| VP Student Services | VP or vice chancellor of student services / student affairs | Assistant superintendent of student or educational services |
| VP Administrative Services | VP or vice chancellor of administrative or business services, CFO, chief business officer | Assistant superintendent of business services |

Trustees, directors and assistants are not listed. The rules live in `scanner/stakeholders.py`.

## Contact details for every stakeholder

Each nightly run starts and ends with `scanner/enrich.py`, which makes sure every person shown has a way to reach them and every opportunity has at least one person:

1. **K-12 districts** are filled from the California Department of Education School Directory (superintendent, phone, email and chief business official). This is free and needs no API calls.
2. For everyone else, Claude looks up, in order: the person's own published email or direct phone; an email matching the institution's confirmed address format (80%+ confidence); their office's published line (for example Business Services); the institution's main number. Office and main lines are labeled on the contact card.
3. Opportunities with nobody listed get a chief business officer, facilities lead or president, in that order.

`ENRICH_LIMIT` (default 60) caps the web lookups per night. People already filled are never looked up again.

## How scanning works

- Each night the scanner takes the institutions scanned longest ago, starting with the K-12 districts that have never been scanned, and rechecks active pre-RFP leads every 14 days.
- For each one, Claude searches board minutes, agenda packets, facilities master plans and local coverage, and returns signals with verbatim quotes and source links, decision makers, advisors, funding and upcoming meeting dates.
- Emails are kept only when published on an official page or matched to the institution's confirmed format; otherwise the name and title are shown.
- At 40 institutions a night, the full list of 1,084 is covered in about four weeks, then the cycle repeats. To finish K-12 faster, run the workflow manually with `systems = K12` and a larger batch.

API usage (model tokens and web searches) is billed to your Anthropic account. Start with the default batch and check usage in the Console before raising it.

## Change the password

Update the `EDUNEST_PASSWORD` secret; the next run re-encrypts with it. Without GitHub:

```bash
cd admin
pip install cryptography
python3 encrypt_data.py --user VolzCompany --password "a-longer-passphrase"
```

then upload `site/assets/edunest-data.js`.

## Notes

- The data on the server is AES-256 encrypted with a key derived from the username and password. `Irvine` is short and guessable by someone who copies the file; use a longer passphrase for real protection.
- Follow-up status, notes, stage moves and loss reasons are saved in each user's own browser. Use **Export report (CSV)** to share them.
