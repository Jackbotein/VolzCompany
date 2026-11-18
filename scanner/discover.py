#!/usr/bin/env python3
"""EduNestRadar multistate discovery.

For states outside California there is no fixed institution list. Each run takes the
(state, sector) sweeps done longest ago and asks Claude with web search to find public
universities, community/technical colleges and K-12 districts in that state whose board
minutes, agendas or facilities master plans show housing plans. Results merge into the
same data file as the California scan.

Environment: ANTHROPIC_API_KEY, EDUNEST_MODEL, SWEEPS_PER_RUN (default 6), STATES (e.g. "OR,WA")
"""
import json
import os
import pathlib
import re
import sys
import time

import anthropic

from scan import MODEL, TODAY, load, merge, save, slug
from stakeholders import RULES

HERE = pathlib.Path(__file__).resolve().parent
STATES = json.loads((HERE / "states.json").read_text(encoding="utf-8"))
ONLY = {s.strip().upper() for s in os.environ.get("STATES", "").split(",") if s.strip()}
PER_RUN = int(os.environ.get("SWEEPS_PER_RUN", "6"))

SECTORS = {
    "PU": "public universities: student housing, residence halls, graduate/family housing, faculty and staff housing, public-private partnerships, ground leases",
    "CC": "public community and technical colleges: first student housing or residence halls, housing feasibility studies, employee housing, public-private partnerships",
    "K12": "public K-12 school districts: teacher or employee workforce housing, staff housing on district land, surplus land for housing, teacherages",
}

PROMPT = """You research public education real estate for Volz Company, a real estate advisory firm that advises public educational institutions on student housing, faculty and staff housing, employee workforce housing and related campus real estate.

State: {state_name}
Sector: {sector}
Governing bodies to check: {boards}
Today: {today}

Search the last 24 months of governing board minutes and agendas, facilities master plans and capital plans, and local news about board actions in this state and sector. Run many varied searches (for example "{state_name} school district teacher housing board", "{state_name} community college student housing feasibility", "{state_name} university housing public-private partnership board of regents", "workforce housing district land {state_name}"). Prefer primary documents.

Return up to 10 institutions showing real housing signals, earliest-stage (pre-RFP) opportunities first.

Rules:
- Every signal needs a source URL and a verbatim quote of 8-30 words from it.
- {rules}
- Every stakeholder must have an email or phone: own published contact; else an email matching a format confirmed by two or more published addresses on the same domain ("format"); else their office's published line ("office"); else the institution's main number ("main"). Never invent anything.

Reply with ONLY one JSON object in a ```json block:
{{"institutions":[{{"institution":"official name","system":"PU|CC|K12","county":"","city":"","lat":0,"lon":0,
"signals":[{{"project":"","housing":["Student"|"Faculty & staff"|"Workforce"|"Other campus real estate"],"stage":1-6,"headline":"","summary":"",
"evidence":[{{"quote":"","source":"","type":"","date":"","url":""}}],"advisors":[{{"name":"","role":""}}],
"contacts":[{{"stakeholder":"President|VP Student Services|VP Administrative Services","name":"","title":"","email":"","email_basis":"published|format|office|main","phone":"","contact_note":"","url":"","source":""}}],
"funding":{{"status":"Unfunded|Planned|Partial|Committed|Unknown","source":"","amount":""}},
"upcoming":[{{"date":"YYYY-MM-DD","label":"","url":""}}],"next_step":""}}]}}]}}

Stages: 1 board discussion; 2 feasibility study; 3 in a master or capital plan; 4 advisor hired; 5 developer RFP/RFQ or negotiation; 6 financing approved, under construction or open."""


def ask(client, prompt):
    for attempt in range(4):
        try:
            r = client.messages.create(model=MODEL, max_tokens=8000,
                                       tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 12}],
                                       messages=[{"role": "user", "content": prompt}])
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            m = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
            return json.loads(m[-1]) if m else None
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            print(f"  retry: {e}", file=sys.stderr)
            time.sleep(30 * (attempt + 1))
        except json.JSONDecodeError:
            return None
    return None


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY")
    client = anthropic.Anthropic()
    d = load()
    sweeps = d.setdefault("sweeps", {})
    pairs = [(s, k) for s in STATES if not ONLY or s in ONLY for k in SECTORS]
    pairs.sort(key=lambda p: sweeps.get(f"{p[0]}|{p[1]}", {}).get("date", ""))
    total = 0
    for state, sector in pairs[:PER_RUN]:
        print(f"Sweep {state} {sector}")
        res = ask(client, PROMPT.format(state_name=STATES[state]["name"], sector=SECTORS[sector], boards=STATES[state]["boards"],
                                        today=TODAY, rules=RULES.replace("\n", "\n  ")))
        found = 0
        for it in (res or {}).get("institutions", []):
            name = (it.get("institution") or "").strip()
            system = it.get("system") if it.get("system") in ("PU", "CC", "K12") else sector
            if not name:
                continue
            inst = {"key": f"{state}|{name}", "name": name, "system": system, "state": state, "county": it.get("county", "")}
            before = len(d["leads"])
            found += merge(d, inst, {"signals": it.get("signals", [])})
            for l in d["leads"]:
                if inst["key"] in l.get("keys", []):
                    l["state"] = state
                    if not l.get("loc") and isinstance(it.get("lat"), (int, float)) and it.get("lat"):
                        l["loc"] = {"lat": it["lat"], "lon": it["lon"], "city": it.get("city", "")}
        sweeps[f"{state}|{sector}"] = {"date": TODAY, "found": found}
        total += found
        save(d)
        time.sleep(3)
    print(f"Done. New opportunities: {total}")


if __name__ == "__main__":
    main()
