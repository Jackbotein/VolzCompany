#!/usr/bin/env python3
"""EduNestRadar stakeholder enrichment.

Every opportunity lists up to three stakeholders, and nobody else:
  President | VP Student Services | VP Administrative Services
(K-12: superintendent | assistant superintendent of student services | assistant superintendent of business).

Each stakeholder gets a way to reach them, in this order: own published email or direct
phone; email matching a confirmed address format (80%+); their office's published line;
the institution's main number.

California K-12 districts are first filled from the CDE School Directory (superintendent,
phone, email, chief business official) at no API cost.

Environment: ANTHROPIC_API_KEY, EDUNEST_MODEL, ENRICH_LIMIT (default 60 API calls per run)
"""
import json
import os
import re
import sys
import time
import urllib.request

import anthropic

from scan import INST, MODEL, TODAY, load, save
from stakeholders import ROLES, RULES, filter_contacts

LIMIT = int(os.environ.get("ENRICH_LIMIT", "60"))
BY_KEY = {i["key"]: i for i in INST}
CDE_URL = "https://www.cde.ca.gov/SchoolDirectory/details?cdscode={}"

PROMPT = """Identify the stakeholders of this public education institution and how to reach each one, for business outreach by a real estate advisory firm.

Institution: {inst} ({where})
Roles needed: {roles}
Already known (fill in missing contact details for them if needed): {known}

{rules}

For each person give contact details in this order of preference:
1. their own published email and/or direct phone ("basis": "published")
2. an email matching the institution's address format, only if two or more published staff addresses on the same domain confirm it ("basis": "format")
3. the published phone or email of their office, e.g. Office of the President, Student Services, Business Services ("basis": "office")
4. the institution's main published phone number ("basis": "main")
Every person you list must have an email or a phone. Never invent a name, number or address; use the official website and staff directory.

Reply with ONLY a JSON object in a ```json block:
{{"stakeholders":[{{"stakeholder":"President|VP Student Services|VP Administrative Services","name":"","title":"","email":"","phone":"","basis":"published|format|office|main","label":"office name for office/main lines","url":"source page"}}]}}"""


def ask(client, prompt):
    for attempt in range(4):
        try:
            r = client.messages.create(model=MODEL, max_tokens=2000,
                                       tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
                                       messages=[{"role": "user", "content": prompt}])
            text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
            m = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
            return json.loads(m[-1]) if m else None
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            print(f"  retry: {e}", file=sys.stderr)
            time.sleep(20 * (attempt + 1))
        except json.JSONDecodeError:
            return None
    return None


def to_contact(s, inst):
    if not s.get("name") or s.get("stakeholder") not in ROLES:
        return None
    c = {"stakeholder": s["stakeholder"], "role": s["stakeholder"], "name": s["name"].strip(),
         "title": s.get("title") or f"{s['stakeholder']}, {inst}", "source": "Web lookup"}
    basis = s.get("basis", "")
    if s.get("email") and basis in ("published", "format", "office"):
        c["email"] = s["email"].strip()
    if s.get("phone"):
        c["phone"] = s["phone"].strip()
    if basis == "format":
        c["verify"] = "Address matches the institution’s published email format"
    if basis in ("office", "main"):
        c["contactNote"] = s.get("label") or ("Office line" if basis == "office" else "Main line")
    if s.get("url"):
        c["url"] = s["url"]
    return c if (c.get("email") or c.get("phone")) else None


def cde_lookup(cds):
    if not cds:
        return None
    try:
        req = urllib.request.Request(CDE_URL.format(cds), headers={"User-Agent": "EduNestRadar/1.0"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  CDE lookup failed: {e}", file=sys.stderr)
        return None
    lines = [l.strip() for l in re.sub(r"[ \t\r]+", " ", re.sub(r"<[^>]+>", "\n", html)).split("\n") if l.strip()]

    def after(label):
        for i, l in enumerate(lines):
            if l.lower().startswith(label.lower()):
                rest = l[len(label):].strip(" :")
                return rest or (lines[i + 1] if i + 1 < len(lines) else "")
        return ""

    out = {"url": CDE_URL.format(cds), "phone": after("Phone Number"), "cbo": after("Chief Business Official")}
    for i, l in enumerate(lines):
        if re.match(r"^(Mr\.|Mrs\.|Ms\.|Dr\.)?\s*[A-Z][\w'.-]+(\s[A-Z][\w'.-]+)+$", l) and i + 1 < len(lines) and "Superintendent" in lines[i + 1]:
            blk = " ".join(lines[i + 2:i + 6])
            pm = re.search(r"\(\d{3}\)\s*\d{3}-\d{4}", blk)
            em = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", blk)
            out.update(supt=re.sub(r"^(Mr\.|Mrs\.|Ms\.|Dr\.)\s*", "", l), supt_phone=pm.group(0) if pm else out["phone"],
                       supt_email=em.group(0) if em else "")
            break
    return out


def main():
    d = load()
    client = anthropic.Anthropic() if os.environ.get("ANTHROPIC_API_KEY") else None
    calls = 0
    leads = sorted(d["leads"], key=lambda l: (l.get("relationship") == "client", l.get("stage", 9) > 3, l.get("stage", 9)))
    for l in leads:
        l["contacts"] = filter_contacts(l.get("contacts"))

    # 1. California K-12 from the CDE directory (free)
    for l in leads:
        if l.get("system") != "K12" or l.get("state", "CA") != "CA":
            continue
        have = {c["stakeholder"] for c in l["contacts"]}
        if {"President", "VP Administrative Services"} <= have:
            continue
        info = cde_lookup(BY_KEY.get((l.get("keys") or [""])[0], {}).get("cds"))
        if not info:
            continue
        add = []
        if "President" not in have and info.get("supt"):
            add.append({"stakeholder": "President", "name": info["supt"], "title": f"Superintendent, {l['inst']}",
                        "email": info.get("supt_email", ""), "phone": info.get("supt_phone", ""), "url": info["url"], "source": "CDE School Directory"})
        if "VP Administrative Services" not in have and info.get("cbo"):
            name, _, title = info["cbo"].partition(",")
            add.append({"stakeholder": "VP Administrative Services", "name": name.strip(),
                        "title": f"{title.strip() or 'Chief Business Official'}, {l['inst']}", "phone": info.get("phone", ""),
                        "contactNote": "District office main line", "url": info["url"], "source": "CDE School Directory"})
        if add:
            l["contacts"] = filter_contacts(l["contacts"] + [{k: v for k, v in c.items() if v} for c in add])
            l["updated"] = TODAY
            print(f"CDE: {l['inst']}")
    save(d)

    if not client:
        print("No ANTHROPIC_API_KEY; skipped web lookups")
        return

    # 2. One lookup per opportunity for missing roles or missing contact details
    seen = {}
    for l in leads:
        have = {c["stakeholder"]: c for c in l["contacts"]}
        missing = [r for r in ROLES if r not in have]
        unreachable = [c for c in l["contacts"] if not (c.get("email") or c.get("phone"))]
        if not missing and not unreachable:
            continue
        inst_key = (l["inst"], l.get("state", "CA"))
        if inst_key in seen:  # same institution on another opportunity: reuse
            res = seen[inst_key]
        else:
            if calls >= LIMIT:
                break
            known = "; ".join(f"{c['stakeholder']}: {c['name']} ({c.get('title', '')})" for c in l["contacts"]) or "none"
            where = f"{l.get('county', '')} County, {l.get('state', 'CA')}".strip(", ")
            res = ask(client, PROMPT.format(inst=l["inst"], where=where, roles=", ".join(ROLES), known=known, rules=RULES))
            calls += 1
            seen[inst_key] = res
            time.sleep(2)
        if not res:
            continue
        found = [c for c in (to_contact(s, l["inst"]) for s in res.get("stakeholders", [])) if c]
        if found:
            merged = {c["stakeholder"]: c for c in l["contacts"]}
            for c in found:
                cur = merged.get(c["stakeholder"])
                if cur is None or not (cur.get("email") or cur.get("phone")) or cur["name"] == c["name"]:
                    merged[c["stakeholder"]] = {**(cur or {}), **c} if cur and cur["name"] == c["name"] else c
            l["contacts"] = filter_contacts(list(merged.values()))
            l["updated"] = TODAY
            print(f"Stakeholders: {l['inst']} -> {', '.join(c['stakeholder'] for c in l['contacts'])}")
            save(d)
    save(d)
    print(f"Done. API lookups used: {calls}")


if __name__ == "__main__":
    main()
