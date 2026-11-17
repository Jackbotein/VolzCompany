"""Tag existing Volz Company relationships (see clients.json)."""
import json
import pathlib
import re

CLIENTS = json.loads((pathlib.Path(__file__).resolve().parent / "clients.json").read_text(encoding="utf-8"))
SECONDARY = re.compile(r"news|trade press|recap|conference|case study|newsletter|magazine|voter guide|opinion|blog|press release", re.I)


def tag(lead):
    for c in CLIENTS:
        if c.get("state") and lead.get("state", "CA") != c["state"]:
            continue
        if any(m.lower() in lead.get("inst", "").lower() for m in c["match"]):
            lead["relationship"] = "client"
            lead["relationshipNote"] = c["note"]
            return


def is_primary(e):
    """Board minutes, agendas, staff reports, master plans, capital plans, CEQA filings, official pages."""
    return not SECONDARY.search(f"{e.get('type', '')} {e.get('source', '')}")
