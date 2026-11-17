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

## Scan from the website (no GitHub needed)

The **Scan** tab runs scans straight from the browser with your Anthropic API key (stored only in that browser):

- **California institutions not yet scanned**: community colleges and K-12 first, then UC and CSU. Choose how many per run, or "All remaining".
- **California institutions scanned longest ago**: re-scans to keep everything current.
- **Find stakeholders for opportunities missing them**: president, VP of student services and VP of administrative services; at minimum the president with the president's public email.
- **Re-verify leads awaiting board minutes**: replaces news-based evidence with board minutes, agendas or master plans.

Results show up immediately and are saved in that browser. To publish them to everyone, click **Download website data file** and upload the file to `assets/` on the server, replacing `edunest-data.js`.

## Evidence rules

Only primary sources are cited: board minutes, agenda packets, staff reports, resolutions, facilities master plans, capital plans, CEQA filings and the institution's official pages. Opportunities supported only by news are hidden until re-verified (tick **Include leads awaiting board-minutes verification** to see them).

## Funding boosts

The scanners record bond measures, state and federal grants and appropriations with the institution's annual budget, so boosts are ranked by **% of budget**, not dollars. Community colleges and K-12 districts come first. Sort by **Biggest funding boost (% of budget)** or tick **Big funding boost only**.

## Existing Volz Company relationships

Past and current clients listed in `scanner/clients.json` are tagged **Existing Volz Company relationship** with the scope of work, both in the app and on anything new the scanners find. Edit that file to add clients.

## Continuous re-scanning

The GitHub Actions job now runs **every 2 hours, around the clock** (not just nightly). Each run spends up to `STEP_MINUTES` (default 22) on each step, saves progress as it goes, and picks up where the last run stopped:

1. Fill stakeholders and contact details (`enrich.py`, up to `ENRICH_LIMIT` = 120 lookups)
2. California institution scan (`scan.py`, `BATCH_SIZE` = 40, oldest-scanned first, active pre-RFP leads rechecked every 14 days)
3. Other-state discovery (`discover.py`, `SWEEPS_PER_RUN` = 8 state/sector/theme sweeps, each told which institutions are already known so it finds new ones)
4. High-growth detection (`growth.py`, 2 states per run)
5. Fill contacts for anything new, encrypt, commit, upload

At these settings all 1,084 California institutions are rescanned about every 2–3 days and all 99 out-of-state sweeps about every day, so the list keeps growing and refreshing. Expect **500+ opportunities within the first several days** of running; the count depends on what each state's boards have actually published.

Prefer a server over GitHub? Run `python3 scanner/run_forever.py` on any always-on machine (instructions at the top of that file). It loops through the same steps nonstop and uploads the data file by FTP.

API cost scales with these settings. Check usage in the Anthropic Console after the first day and lower `BATCH_SIZE`, `SWEEPS_PER_RUN` or `ENRICH_LIMIT`, or change the cron line in `.github/workflows/scan.yml`, to fit your budget.

## High-growth institutions

`growth.py` looks for sudden capital injections in the last 36 months: capital campaigns that are the largest in the institution's history, record single gifts, record bond measures and record facilities appropriations. Matching opportunities get a green **Growth** tag; institutions with no housing signal yet are added as "Growth signal" opportunities. In the app, choose **Sort by: Highest growth first** or tick **High-growth institutions only**.

## Coverage: 12 states

California is scanned institution by institution (all 1,084 UC, CSU, community college and K-12 institutions). Oregon, Washington, Nevada, Arizona, Utah, Illinois, Iowa, Wisconsin, Minnesota, Indiana and Missouri are covered by `scanner/discover.py`, which each night runs the state-and-sector sweeps (universities, community/technical colleges, K-12 districts) done longest ago. Each state has 9 sweeps (3 sectors x 3 themes), 99 in total. Set the `STATES` variable (e.g. `OR,WA`) to focus on some states. Governing bodies per state are listed in `scanner/states.json`.

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
