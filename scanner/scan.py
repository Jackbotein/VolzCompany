#!/usr/bin/env python3
"""EduNestRadar automated scanner.

Each run picks the institutions that were scanned longest ago (plus any
priority leads due for a recheck), asks Claude with web search to read their
board minutes, agendas and facilities master plans, and merges the findings
into admin/source-data/edunest-data.json.

Environment variables
  ANTHROPIC_API_KEY   required
  EDUNEST_MODEL       default claude-sonnet-5-5
  BATCH_SIZE          institutions per run, default 40
  RECHECK_DAYS        recheck priority leads after this many days, default 14
  MAX_SEARCHES        web searches per institution, default 6
  SYSTEMS             comma list to limit scope, e.g. "K12" or "UC,CSU,CCC"; default all
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time

import anthropic

from stakeholders import RULES, filter_contacts
from clients import is_primary, tag

HERE = pathlib.Path(__file__).resolve().parent
DATA = HERE.parent / "admin" / "source-data" / "edunest-data.json"
INST = json.loads((HERE / "institutions.json").read_text(encoding="utf-8"))

MODEL = os.environ.get("EDUNEST_MODEL", "claude-sonnet-5-5")
BATCH = int(os.environ.get("BATCH_SIZE", "40"))
RECHECK = int(os.environ.get("RECHECK_DAYS", "14"))
MAX_SEARCHES = int(os.environ.get("MAX_SEARCHES", "6"))
SYSTEMS = {s.strip() for s in os.environ.get("SYSTEMS", "").split(",") if s.strip()}
TODAY = dt.date.today().isoformat()
DEADLINE = time.time() + 60 * int(os.environ.get("STEP_MINUTES", "25"))

SYSNAME = {"UC": "University of California campus", "CSU": "California State University campus",
           "CCC": "California community college", "K12": "California K-12 school district"}

PROMPT = """You research public education real estate for Volz Company, a California real estate advisory firm. Volz advises public educational institutions on student housing, faculty and staff housing, K-12 employee workforce housing, and related campus real estate (public-private partnerships, ground leases, surplus land).

Institution: {name} ({sysname}{county})
Today: {today}

Read this institution's own governing board minutes, agenda packets and staff reports from the last 24 months (BoardDocs, Simbli, eScribe, Granicus, district and college websites), its facilities master plan (or LRDP / capital plan) and any CEQA filings. Run several searches with different wording (for example: "{name} board minutes housing", "{name} workforce housing", "{name} student housing", "{name} facilities master plan housing", "{name} surplus property housing", "{name} board agenda"). ONLY primary sources count: board minutes, agenda packets, staff reports, resolutions, facilities master plans, capital plans, CEQA filings and the institution's official pages. News articles may help you find a document, but never cite them. Also note any recent large funding boost (bond measure, state or federal grant) relative to the institution's annual budget.

Find any sign the institution is discussing, studying, planning, funding or procuring housing for students, faculty, staff or employees, or leasing/selling land for such housing. Also find:
- the institution's stakeholders (rules below)
- any consultant, advisor, developer or architect already engaged
- funding: bonds, state grants, P3, land sale, none identified
- any upcoming board meeting or deadline where the item will be decided

Rules:
- Every signal must cite a primary document URL (minutes, agenda, staff report, master plan, official page) and a verbatim quote (8-30 words) from it. Drop any signal you can only support with news.
- Every person must come with a way to reach them. Use, in order: their own published email or direct phone ("email_basis": "published"); an email matching a format confirmed by two or more published addresses on the same domain, at least 80% confidence ("format"); their office's published phone or email ("office"); the institution's main published phone ("main"). For "office" or "main", put the office name in "contact_note". Never invent a number or address.
{rules}
- Do not invent anything. If nothing relevant exists, return an empty signals list.

Reply with ONLY one JSON object in a ```json block:
{{"signals":[{{"project":"short name","housing":["Student"|"Faculty & staff"|"Workforce"|"Other campus real estate"],
"stage":1-6,"headline":"one sentence","summary":"two sentences, your own words",
"evidence":[{{"quote":"verbatim","source":"publisher and document","type":"Board minutes|Board agenda|Facilities master plan|News report|District page","date":"Mon D, YYYY","url":"https://..."}}],
"advisors":[{{"name":"","role":""}}],
"contacts":[{{"stakeholder":"President|VP Student Services|VP Administrative Services","name":"","title":"","email":"","email_basis":"published|format|office|main","phone":"","contact_note":"","role":"Key contact|Decision maker|Board","url":"","source":""}}],
"funding":{{"status":"Unfunded|Planned|Partial|Committed|Unknown","source":"","amount":""}},
"upcoming":[{{"date":"YYYY-MM-DD","label":"what is decided","url":""}}],
"next_step":"one sentence advisory angle for Volz"}}]}}

Stages: 1 board discussion / staff directed to explore; 2 feasibility study scoped or under way; 3 housing named in a master plan or capital plan; 4 advisor or consultant hired; 5 developer RFP/RFQ out or partner in negotiation; 6 financing approved, under construction or open."""


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower().replace("ñ", "n").replace("é", "e"))
    return s.strip("-")[:60]


def load():
    return json.loads(DATA.read_text(encoding="utf-8"))


def save(d):
    d["asOf"] = TODAY
    DATA.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def pick(d):
    cov = d.get("coverage", {})
    pool = [i for i in INST if not SYSTEMS or i["system"] in SYSTEMS]
    cutoff = (dt.date.today() - dt.timedelta(days=RECHECK)).isoformat()
    hot_keys = []
    for l in d["leads"]:
        if l.get("stage", 9) <= 4 and l.get("relationship") != "client" and l.get("updated", "") < cutoff:
            hot_keys += l.get("keys", [])
    by_key = {i["key"]: i for i in pool}
    chosen = [by_key[k] for k in dict.fromkeys(hot_keys) if k in by_key][: BATCH // 3]
    rest = sorted((i for i in pool if i not in chosen), key=lambda i: (cov.get(i["key"], ""), i["system"] != "K12"))
    return chosen + rest[: BATCH - len(chosen)]


def ask(client, inst):
    msg = PROMPT.format(name=inst["name"], sysname=SYSNAME[inst["system"]],
                        county=f", {inst['county']} County" if inst.get("county") else "", today=TODAY, rules=RULES)
    for attempt in range(5):
        try:
            r = client.messages.create(
                model=MODEL, max_tokens=4000,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": MAX_SEARCHES}],
                messages=[{"role": "user", "content": msg}])
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            m = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S) or re.findall(r"(\{\s*\"signals\".*\})", text, re.S)
            return json.loads(m[-1]) if m else {"signals": []}
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            wait = 20 * (attempt + 1)
            print(f"  retry in {wait}s: {e}", file=sys.stderr)
            time.sleep(wait)
        except json.JSONDecodeError:
            return {"signals": []}
    return None


def clean_contacts(cs):
    out = []
    for c in cs or []:
        if not c.get("name"):
            continue
        c = {k: v for k, v in c.items() if v}
        if c.get("email") and c.get("email_basis") not in ("published", "format", "office"):
            c.pop("email", None)
        if c.get("contact_note"):
            c["contactNote"] = c.pop("contact_note")
        if c.get("email_basis") == "format":
            c["verify"] = "Address matches the institution’s published email format"
        c.pop("email_basis", None)
        out.append(c)
    return filter_contacts(out)


def merge(d, inst, res):
    leads = {l["id"]: l for l in d["leads"]}
    added = 0
    for s in res.get("signals", []):
        ev = [dict(e, primary=True) for e in s.get("evidence", []) if e.get("url", "").startswith("http") and e.get("quote") and is_primary(e)]
        if not ev:
            continue
        stage = max(1, min(6, int(s.get("stage") or 1)))
        lid = slug(inst["name"]) + "-" + slug(s.get("project") or "housing")[:24]
        existing = next((l for l in leads.values() if inst["key"] in l.get("keys", []) and
                         (l["id"] == lid or slug(l.get("headline", ""))[:24] == slug(s.get("headline", ""))[:24])), None)
        if existing is None:
            existing = next((l for l in leads.values() if l.get("keys") == [inst["key"]]), None) if len(res["signals"]) == 1 else None
        upcoming = [u for u in s.get("upcoming", []) if re.match(r"\d{4}-\d\d-\d\d$", u.get("date", "")) and u["date"] >= TODAY]
        trig = [{"date": u["date"], "label": u.get("label", "Board decision"), "url": u.get("url", ""), "confirmed": True} for u in upcoming]
        fields = {
            "stage": stage, "headline": s.get("headline", ""), "summary": s.get("summary", ""),
            "nextStep": s.get("next_step", ""), "funding": s.get("funding") or {"status": "Unknown"},
            "updated": TODAY, "latestEvidence": TODAY,
        }
        if existing:
            urls = {e.get("url") for e in existing.get("evidence", [])}
            existing["evidence"] = existing.get("evidence", []) + [e for e in ev if e["url"] not in urls]
            names = {c["name"] for c in existing.get("contacts", [])}
            new_c = [c for c in clean_contacts(s.get("contacts")) if c["name"] not in names]
            existing["contacts"] = filter_contacts(existing.get("contacts", []) + new_c)
            anames = {a["name"] for a in existing.get("advisors", [])}
            existing["advisors"] = existing.get("advisors", []) + [a for a in s.get("advisors", []) if a.get("name") and a["name"] not in anames]
            tdates = {(t["date"], t["label"]) for t in existing.get("triggers", [])}
            existing["triggers"] = [t for t in existing.get("triggers", []) if t["date"] >= TODAY] + [t for t in trig if (t["date"], t["label"]) not in tdates]
            if existing.get("relationship") == "client":
                fields.pop("stage")
            existing.update({k: v for k, v in fields.items() if v})
        else:
            lead = {"id": lid, "inst": inst["name"], "keys": [inst["key"]], "system": inst["system"], "state": inst.get("state", "CA"),
                    "county": inst.get("county", ""), "housing": s.get("housing") or ["Workforce" if inst["system"] == "K12" else "Student"],
                    "evidence": ev, "advisors": [a for a in s.get("advisors", []) if a.get("name")],
                    "contacts": clean_contacts(s.get("contacts")), "triggers": trig, "status": "New", "notes": "",
                    "firstSeen": TODAY, "origin": "Automated scan", **fields}
            d["leads"].append(lead)
            leads[lid] = lead
            added += 1
    for l in d["leads"]:
        if inst["key"] in l.get("keys", []):
            tag(l)
            l["needsPrimary"] = not any(e.get("primary") for e in l.get("evidence", []))
    d.setdefault("coverage", {})[inst["key"]] = TODAY
    return added


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY")
    client = anthropic.Anthropic()
    d = load()
    batch = pick(d)
    print(f"Scanning {len(batch)} institutions with {MODEL}")
    total = 0
    for n, inst in enumerate(batch, 1):
        if time.time() > DEADLINE:
            print("Time budget reached; continuing next run")
            break
        print(f"[{n}/{len(batch)}] {inst['name']}")
        res = ask(client, inst)
        if res is None:
            print("  skipped after retries")
            continue
        total += merge(d, inst, res)
        save(d)  # save as we go so a timeout keeps progress
        time.sleep(2)
    print(f"Done. New opportunities: {total}")


if __name__ == "__main__":
    main()
