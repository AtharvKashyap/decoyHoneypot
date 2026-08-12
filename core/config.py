"""Load and validate the fake-company definition (`company.yaml`).

The Decoy Generator produces `config/company.yaml`; every other component reads
it through this module so the "shape" of the fake org is defined in exactly one
place. Typed dataclasses give components autocomplete and fail loudly on a
malformed config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class WorkHours:
    start: str = "09:00"   # HH:MM local
    end: str = "17:00"
    tz: str = "UTC"
    days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon-Fri


@dataclass
class Persona:
    username: str
    full_name: str
    role: str
    home_ip: str                       # the "known-benign" source IP
    work_hours: WorkHours = field(default_factory=WorkHours)
    smb_share: str = "share"
    files_owned: list[str] = field(default_factory=list)
    # Relative weights for which activities this persona tends to perform.
    activity_weights: dict[str, float] = field(
        default_factory=lambda: {
            "open_file": 4, "edit_file": 2, "share_file": 1,
            "browse": 3, "send_mail": 2, "ssh": 1,
        }
    )


@dataclass
class Host:
    name: str
    ip: str
    services: list[str] = field(default_factory=list)
    is_trap: bool = False              # pure honeypot (any touch = attacker)


@dataclass
class Document:
    path: str
    owner: str
    doc_type: str = "note"
    canary: bool = False               # embeds a canary token if True


@dataclass
class Company:
    name: str
    domain: str
    subnet: str
    personas: list[Persona] = field(default_factory=list)
    hosts: list[Host] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)

    def persona_by_ip(self, ip: str) -> Persona | None:
        return next((p for p in self.personas if p.home_ip == ip), None)

    def persona_by_username(self, username: str) -> Persona | None:
        return next((p for p in self.personas if p.username == username), None)

    def trap_hosts(self) -> list[Host]:
        return [h for h in self.hosts if h.is_trap]


DEFAULT_CONFIG = "config/company.yaml"
EXAMPLE_CONFIG = "config/company.example.yaml"


def _persona(d: dict[str, Any]) -> Persona:
    wh = d.get("work_hours", {}) or {}
    return Persona(
        username=d["username"], full_name=d["full_name"], role=d["role"],
        home_ip=d["home_ip"],
        work_hours=WorkHours(**wh) if wh else WorkHours(),
        smb_share=d.get("smb_share", "share"),
        files_owned=list(d.get("files_owned", [])),
        activity_weights=dict(d.get("activity_weights", {})) or Persona.__dataclass_fields__[
            "activity_weights"].default_factory(),  # type: ignore[attr-defined]
    )


def load_company(path: str = DEFAULT_CONFIG) -> Company:
    """Parse a company.yaml into a typed Company. Falls back to the example
    config if the generated one is not present yet (keeps the lab runnable
    before the generator has been run)."""
    p = Path(path)
    if not p.exists() and Path(EXAMPLE_CONFIG).exists():
        p = Path(EXAMPLE_CONFIG)
    data = yaml.safe_load(p.read_text()) or {}
    c = data.get("company", data)  # allow either top-level or nested under 'company'
    return Company(
        name=c["name"], domain=c["domain"], subnet=c.get("subnet", "10.13.0.0/24"),
        personas=[_persona(x) for x in data.get("personas", [])],
        hosts=[Host(**x) for x in data.get("hosts", [])],
        documents=[Document(**x) for x in data.get("documents", [])],
    )
