"""Optional AI content source for the decoy generator.

Used only when `ANTHROPIC_API_KEY` is set. The model id and token ceiling come
from `config.model` — never hardcoded here — and every call is wrapped so that
any failure (missing key, network, malformed JSON, policy refusal) degrades
silently to the deterministic offline source. That keeps `make demo` and the
test suite fully offline-capable.

The AI path produces *only content strings*: the persona roster (as JSON) and
the document bodies. All schema construction, canary embedding, and file writing
lives in `generator.generate`, shared with the offline path.
"""

from __future__ import annotations

import json
import os
from typing import Any

from config.model import MAX_TOKENS, MODEL
from generator import templates as T
from generator.offline import OfflineContentSource

SYSTEM = (
    "You generate synthetic decoy content for an authorised defensive honeypot "
    "lab (an 'AI deception grid'). Everything you write is fake by design: "
    "invented companies, invented people, invented numbers, and nonsense "
    "credentials that authenticate to nothing. Never reproduce real "
    "organisations, real people, real credentials, or real personal data. "
    "Write in the plain, slightly dull register of genuine internal business "
    "documents. Output only the requested content, with no preamble, no "
    "commentary, and no markdown code fences."
)

ROSTER_PROMPT = """\
Invent {n} employees of a fictional mid-sized European logistics company called
"{company}" (domain {domain}). Return ONLY a JSON array. Each element must be an
object with exactly these keys:

  "username"   - short login name, lowercase, e.g. "jchen"
  "full_name"  - the person's full name
  "role"       - job title
  "smb_share"  - one lowercase word naming their department file share
  "work_hours" - object with "start" and "end" as "HH:MM" 24h strings

Vary the departments (finance, IT, HR, operations, sales, legal-style functions)
and stagger the start times between 07:30 and 09:45. All names must be invented.
"""

DOC_PROMPT = """\
Write the full contents of an internal file from {company} (a fictional
logistics company). Do not include any preamble.

  file path : {path}
  doc type  : {doc_type}
  owner     : {owner} ({role}, {share} share)

Formatting rules for this doc type:
{format_rule}

Make it look like a real, mundane internal working document: concrete invented
names, plausible invented figures in EUR, dates in 2026, and internal references
(ticket ids, invoice numbers, contract refs). It must be entirely synthetic. If
the file looks like it holds credentials, use obviously fabricated nonsense
passwords. Aim for 12-25 lines.
"""

FORMAT_RULES = {
    "csv": "Plain CSV: one header row of lowercase snake_case columns, then data rows. No prose.",
    "spreadsheet": (
        "A title line, a '[sheet: <name>]' line, a blank line, then CSV-style "
        "tabular text (header row plus data rows), then an optional short "
        "footer note or two."
    ),
    "note": (
        "An internal memo: 'INTERNAL MEMO', TO/FROM/DATE/SUBJECT lines, a "
        "divider, then the body as short paragraphs and/or a checklist."
    ),
    "presentation": (
        "A slide outline: title line, subtitle line, a divider, then "
        "'Slide N: <heading>' blocks each followed by two to four '  - ' bullets."
    ),
}


class AIContentSource:
    """Anthropic-backed content source with a per-call offline fallback.

    Exposes the same two methods as `OfflineContentSource`, so
    `generator.generate` never branches on which source it is holding.
    """

    name = "ai"

    def __init__(self, n_personas: int = 5, seed: int | None = None) -> None:
        import anthropic  # imported lazily so the offline path needs no SDK

        self.client = anthropic.Anthropic()
        self.model = MODEL
        self.max_tokens = MAX_TOKENS
        self.fallback = OfflineContentSource(n_personas=n_personas, seed=seed)
        self.n_personas = n_personas
        self.errors: list[str] = []

    # -- low-level call -----------------------------------------------------
    def _complete(self, prompt: str) -> str:
        """One non-streaming completion. Raises on refusal or empty output."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            # Server-side refusal fallback: if the model declines, the API
            # re-runs the request on the recommended fallback model.
            resp = self.client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **kwargs,
            )
        except Exception:  # beta/fallbacks unavailable for this model or key
            resp = self.client.messages.create(**kwargs)

        if resp.stop_reason == "refusal":
            raise RuntimeError("model declined the request")
        text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
        if not text:
            raise RuntimeError("empty completion")
        return text

    # -- company spec -------------------------------------------------------
    def company_spec(self) -> dict:
        """AI-generated persona roster grafted onto the fixed lab topology.

        Hosts and the document list stay under our control: the traps, subnet,
        and canary layout are part of the lab contract, not creative content.
        """
        base = self.fallback.company_spec()
        try:
            raw = self._complete(
                ROSTER_PROMPT.format(
                    n=self.n_personas,
                    company=T.COMPANY["name"],
                    domain=T.COMPANY["domain"],
                )
            )
            roster = json.loads(_strip_fences(raw))
            if not isinstance(roster, list) or len(roster) < 4:
                raise ValueError("roster must be a JSON array of >=4 personas")
        except Exception as exc:  # noqa: BLE001 - any failure -> offline roster
            self.errors.append(f"roster: {exc}")
            return base

        personas = base["personas"]
        documents = base["documents"]
        for i, entry in enumerate(roster[: len(personas)]):
            p = personas[i]
            old_user = p["username"]
            try:
                p["username"] = str(entry["username"]).strip().lower()
                p["full_name"] = str(entry["full_name"]).strip()
                p["role"] = str(entry["role"]).strip()
                wh = entry.get("work_hours") or {}
                p["work_hours"]["start"] = str(wh.get("start", p["work_hours"]["start"]))
                p["work_hours"]["end"] = str(wh.get("end", p["work_hours"]["end"]))
            except Exception as exc:  # noqa: BLE001 - keep the offline persona
                self.errors.append(f"persona {i}: {exc}")
                continue
            for d in documents:
                if d["owner"] == old_user:
                    d["owner"] = p["username"]
        return base

    # -- document bodies ----------------------------------------------------
    def document_body(self, doc: dict, spec: dict) -> str:
        owner = next(
            (p for p in spec["personas"] if p["username"] == doc["owner"]), None
        )
        doc_type = doc.get("doc_type", "note")
        try:
            body = self._complete(
                DOC_PROMPT.format(
                    company=spec["company"]["name"],
                    path=doc["path"],
                    doc_type=doc_type,
                    owner=doc["owner"],
                    role=owner["role"] if owner else "employee",
                    share=owner["smb_share"] if owner else "share",
                    format_rule=FORMAT_RULES.get(doc_type, FORMAT_RULES["note"]),
                )
            )
            return _strip_fences(body)
        except Exception as exc:  # noqa: BLE001 - fall back per document
            self.errors.append(f"{doc['path']}: {exc}")
            return self.fallback.document_body(doc, spec)


def _strip_fences(text: str) -> str:
    """Remove a wrapping markdown code fence, if the model added one."""
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def available() -> bool:
    """True when an AI run is possible: a key is set and the SDK imports."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True
