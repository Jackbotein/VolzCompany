"""Stakeholder rules shared by the scanner and contact enrichment.

EduNestRadar lists only three stakeholders per institution:
  President                       - president, chancellor of a district/campus, or K-12 superintendent
  VP Student Services             - VP/vice chancellor of student services, student affairs or student success
                                    (K-12: assistant superintendent of student/educational services)
  VP Administrative Services      - VP/vice chancellor of administrative, business or finance services, CFO,
                                    chief business officer (K-12: assistant superintendent of business services)
"""
import re

ROLES = ["President", "VP Student Services", "VP Administrative Services"]

RULES = """Stakeholders must be exactly these three roles (list each one you can identify, at most one person per role):
- "President": the institution's president; for a university campus its chancellor/president; for a multi-college district the district chancellor; for a K-12 district the superintendent.
- "VP Student Services": vice president or vice chancellor of student services / student affairs / student success; K-12 equivalent: assistant superintendent of student or educational services.
- "VP Administrative Services": vice president or vice chancellor of administrative services, business services, finance or business development, CFO or chief business officer; K-12 equivalent: assistant superintendent of business/administrative services.
Do not list trustees, directors, assistants, consultants or anyone else as stakeholders.
If you cannot identify the other roles, you must still return the President (superintendent for K-12) with the president's public email from the official president's or superintendent's office page; every institution publishes one."""


def classify(title):
    t = (title or "").lower()
    if not t:
        return None
    if re.search(r"executive assistant|assistant to |assistant vice|associate vice|\bdirector\b|controller|coordinator|specialist|board|trustee|office of the president|, csu$", t):
        return None
    if re.search(r"student (services|affairs|success|support)|educational services|student life", t) and re.search(r"vice|assistant superintendent|associate superintendent|dean of students|chief student", t):
        return "VP Student Services"
    if re.search(r"(vice president|vice chancellor|assistant superintendent|associate superintendent|chief).{0,60}(admin|business|financ|fiscal|operations|biz)|\bcfo\b|chief financial|chief business", t):
        if "director" in t and "vice" not in t and "chief" not in t:
            return None
        return "VP Administrative Services"
    if re.search(r"\b(vice|assistant|associate|deputy|executive assistant|chief of staff)\b", t):
        return None
    if re.search(r"\bpresident\b|\bchancellor\b|\bsuperintendent\b", t) and not re.search(r"board|trustee", t):
        return "President"
    return None


def filter_contacts(contacts):
    """Keep only the three stakeholder roles, one person per role, in role order."""
    best = {}
    for c in contacts or []:
        role = c.get("stakeholder") if c.get("stakeholder") in ROLES else classify(c.get("title"))
        if not role:
            continue
        c = dict(c, stakeholder=role, role=role)
        cur = best.get(role)
        if cur is None or (not (cur.get("email") or cur.get("phone")) and (c.get("email") or c.get("phone"))):
            best[role] = c
    return [best[r] for r in ROLES if r in best]
