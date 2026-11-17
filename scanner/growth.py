#!/usr/bin/env python3
"""EduNestRadar high-growth detection.

Finds institutions with a sudden injection of capital in the last 36 months:
record capital campaigns (largest in the institution's history), record single gifts,
and record bond measures or state appropriations. Attaches a "growth" record to every
opportunity at that institution and, where no housing signal exists yet, adds a
"Growth signal" opportunity so the institution is on the radar early.

Environment: ANTHROPIC_API_KEY, EDUNEST_MODEL, GROWTH_STATES_PER_RUN (default 2), STEP_MINUTES (default 25)
"""
import json
import os
import re
import sys
import time

import anthropic

from scan import MODEL, TODAY, load, save, slug
from clients import is_primary, tag
from discover import STATES

ALL = ["CA"] + list(STATES)
NAMES = {"CA": "California", **{k: v["name"] for k, v in STATES.items()}}
PER_RUN = int(os.environ.get("GROWTH_STATES_PER_RUN", "2"))
DEADLINE = time.time() + 60 * int(os.environ.get("STEP_MINUTES", "25"))

PROMPT = """Find community college districts and K-12 school districts in {state} that received a large funding boost in the last 24 months (today is {today}), measured RELATIVE to their size:
- a local bond measure that passed (general obligation bond, parcel tax), especially the largest in the district's history
- a state grant or appropriation for facilities or housing
- a federal grant or appropriation

For each, find the district's annual operating budget (general fund) from its adopted budget so the boost can be expressed as a percent of the budget. Prioritize the largest boosts as a percent of budget, not the largest dollar amounts. Also include public universities only if the boost exceeds 25% of their annual budget.

Cite ONLY primary sources: the district's board resolution, board minutes or agenda calling or certifying the measure, county election results, the state or federal award list, or the district's adopted budget. Never cite news. Every item needs a URL and a verbatim quote (8-30 words). Never invent anything.

Reply with ONLY a JSON object in a ```json block:
{{"items":[{{"institution":"official name","system":"CC|K12|PU","city":"","county":"","lat":0,"lon":0,"type":"Bond|State grant|Federal grant|Appropriation",
"amount_usd":0,"annual_budget_usd":0,"label":"e.g. $450M Measure X bond, largest in district history","date":"YYYY-MM-DD","quote":"","source":"","url":""}}]}}"""


def ask(client, prompt):
    for attempt in range(4):
        try:
            r = client.messages.create(model=MODEL, max_tokens=6000,
                                       tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10}],
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


def apply_growth(d, state, it):
    name = (it.get("institution") or "").strip()
    if not name or not str(it.get("url", "")).startswith("http") or not is_primary(it):
        return 0
    g = {k: it.get(k) for k in ("type", "label", "date", "quote", "source", "url")}
    g["amount"] = float(it.get("amount_usd") or 0)
    budget = float(it.get("annual_budget_usd") or 0)
    g["budget"] = budget
    g["pct"] = round(100 * g["amount"] / budget, 1) if budget else 0
    hits = [l for l in d["leads"] if (l.get("state", "CA") == state) and (l["inst"].lower() == name.lower() or f"{state}|{name}" in l.get("keys", []))]
    for l in hits:
        if (g["pct"], g["amount"]) >= ((l.get("growth") or {}).get("pct", 0), (l.get("growth") or {}).get("amount", 0)):
            l["growth"] = g
    if hits:
        return 0
    system = it.get("system") if it.get("system") in ("PU", "CC", "K12") else "PU"
    if state == "CA" and system in ("PU",):
        system = "UC" if name.startswith("UC") else system
    d["leads"].append({
        "id": slug(f"{state}-{name}-growth"), "inst": name, "keys": [f"{state}|{name}" if state != "CA" else f"{'K12' if system == 'K12' else system}|{name}"],
        "state": state, "system": system, "county": it.get("county", ""), "housing": ["Other campus real estate"], "stage": 1,
        "growthOnly": True, "growth": g,
        "headline": f"Funding boost: {g['label']}" + (f" ({g['pct']:.0f}% of annual budget)" if g.get("pct") else "") + ". Housing plans not yet confirmed.",
        "summary": "A record injection of capital usually precedes new facilities. Check the campaign's facilities priorities and the next capital plan for housing.",
        "evidence": [{"quote": g["quote"], "source": g["source"], "type": g["type"] or "Official record", "date": g["date"], "url": g["url"], "primary": True}],
        "advisors": [], "contacts": [], "nextStep": "Ask the VP of administrative services whether housing is among the facilities the new money will fund.",
        "funding": {"status": "Partial", "source": g["label"]}, "status": "New", "notes": "", "firstSeen": TODAY, "updated": TODAY,
        "latestEvidence": g["date"] or TODAY, "origin": "Growth scan",
        **({"loc": {"lat": it["lat"], "lon": it["lon"], "city": it.get("city", "")}} if isinstance(it.get("lat"), (int, float)) and it.get("lat") else {}),
    })
    tag(d["leads"][-1])
    return 1


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY")
    client = anthropic.Anthropic()
    d = load()
    gs = d.setdefault("growthSweeps", {})
    for state in sorted(ALL, key=lambda s: gs.get(s, ""))[:PER_RUN]:
        if time.time() > DEADLINE:
            break
        print(f"Growth sweep {state}")
        res = ask(client, PROMPT.format(state=NAMES[state], today=TODAY)) or {}
        added = sum(apply_growth(d, state, it) for it in res.get("items", []))
        gs[state] = TODAY
        save(d)
        print(f"  {len(res.get('items', []))} growth signals, {added} new opportunities")


if __name__ == "__main__":
    main()
