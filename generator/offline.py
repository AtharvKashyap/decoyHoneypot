"""Deterministic, offline content source for the decoy generator.

No network, no API key, no randomness that varies between runs: `random` is
seeded from a fixed constant (and per-document from a stable hash of the
document path), so two runs produce byte-identical output. That keeps the lab
reproducible and the tests stable.

Every string produced here is synthetic filler. The "credentials" are nonsense
words that authenticate to nothing — they are lures, not secrets.
"""

from __future__ import annotations

import random
import zlib
from pathlib import PurePosixPath

from generator import templates as T


def _rng(*parts: object) -> random.Random:
    """A Random seeded from the fixed SEED plus a stable hash of `parts`."""
    key = "|".join(str(p) for p in parts).encode()
    return random.Random(T.SEED ^ zlib.crc32(key))


def _money(rng: random.Random, low: int, high: int, step: int = 50) -> str:
    # No thousands separators: these land in comma-separated cells.
    return str(rng.randrange(low, high, step))


def _sample(rng: random.Random, pool: list, k: int) -> list:
    return rng.sample(pool, min(k, len(pool)))


def _cell(value: object) -> str:
    """Stringify a cell, keeping it comma-free so rows stay parseable."""
    return str(value).replace(",", " ")


def _csv(headers: list[str], rows: list[list[object]]) -> str:
    lines = [",".join(headers)]
    lines += [",".join(_cell(c) for c in row) for row in rows]
    return "\n".join(lines)


def _sheet(title: str, sheet: str, headers: list[str], rows: list[list[object]],
           footer: list[str] | None = None) -> str:
    """A spreadsheet rendered as CSV-like tabular text with a small banner."""
    out = [f"{title}", f"[sheet: {sheet}]", "", _csv(headers, rows)]
    if footer:
        out += [""] + footer
    return "\n".join(out)


def _memo(to: str, frm: str, date: str, subject: str, body: list[str]) -> str:
    head = [
        "INTERNAL MEMO -- Meridian Logistics",
        f"TO:      {to}",
        f"FROM:    {frm}",
        f"DATE:    {date}",
        f"SUBJECT: {subject}",
        "-" * 62,
        "",
    ]
    return "\n".join(head + body)


def _deck(title: str, subtitle: str, slides: list[tuple[str, list[str]]]) -> str:
    out = [f"{title}", f"{subtitle}", "=" * 62, ""]
    for i, (heading, bullets) in enumerate(slides, start=1):
        out.append(f"Slide {i}: {heading}")
        out += [f"  - {b}" for b in bullets]
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Per-document builders, keyed by the document's file stem.
# ---------------------------------------------------------------------------

def _q3_forecast(doc: dict, spec: dict, rng: random.Random) -> str:
    lanes = _sample(rng, T.CITIES, 6)
    rows = []
    for lane in lanes:
        rows.append([
            f"{lane} -> Meridian DC1",
            _money(rng, 180_000, 640_000, 500),
            _money(rng, 190_000, 660_000, 500),
            f"{rng.randrange(2, 14)}.{rng.randrange(0, 9)}%",
            f"{rng.randrange(72, 97)}%",
        ])
    return _sheet(
        "FY2026 Q3 REVENUE FORECAST (DRAFT 3 - not for distribution)",
        "Q3_by_lane",
        ["lane", "q2_actual_eur", "q3_forecast_eur", "yoy_growth", "capacity_util"],
        rows,
        footer=[
            "Assumptions: diesel at 1.62 EUR/l flat, no new depot openings,",
            "Aldergate contract renewal lands 15 Aug at current volumes.",
            "Owner: Finance. Review with Ops before board pack is cut.",
        ],
    )


def _vendor_payments(doc: dict, spec: dict, rng: random.Random) -> str:
    rows = []
    for i, vendor in enumerate(_sample(rng, T.VENDORS, 8)):
        rows.append([
            f"INV-2026-{4100 + i * 7}",
            vendor,
            f"2026-0{rng.randrange(4, 8)}-{rng.randrange(10, 28)}",
            _money(rng, 4_000, 96_000),
            rng.choice(["approved", "approved", "pending review", "on hold"]),
            f"NL{rng.randrange(10, 99)}MERI{rng.randrange(1000, 9999)}{rng.randrange(1000, 9999)}",
        ])
    return _sheet(
        "ACCOUNTS PAYABLE - OPEN ITEMS (CONFIDENTIAL)",
        "AP_open",
        ["invoice_no", "vendor", "due_date", "amount_eur", "status", "remit_iban"],
        rows,
        footer=[
            "Dual approval required above 25,000 EUR (policy FIN-04).",
            "Bank detail changes must be confirmed by phone callback.",
        ],
    )


def _close_checklist(doc: dict, spec: dict, rng: random.Random) -> str:
    return _memo(
        to="Finance team",
        frm="Jia Chen, Finance Analyst",
        date="2026-07-02",
        subject="Month-end close checklist (July run)",
        body=[
            "Same order as last month, with two changes flagged below.",
            "",
            " 1. Lock the freight accrual sheet by 17:00 on the last working day.",
            " 2. Pull carrier self-bill differences from the WMS export (ops share).",
            " 3. Reconcile fuel card statements - Ridgeway is still sending PDFs.",
            " 4. NEW: post the depot 2 racking capitalisation before depreciation runs.",
            " 5. Intercompany balances with the Porto entity: confirm with Miriam.",
            " 6. NEW: reviewer sign-off now goes in the intranet workflow, not email.",
            " 7. Draft variance commentary; anything over 5% needs a written reason.",
            "",
            "Open item: vendor_payments.xlsx still holds three invoices on hold",
            "pending a bank-detail callback. Do not release them until that is done.",
        ],
    )


def _server_inventory(doc: dict, spec: dict, rng: random.Random) -> str:
    rows = []
    roles = _sample(rng, T.SERVER_ROLES, 10)
    for i, role in enumerate(roles):
        rows.append([
            f"MERI-{'DC' if i < 3 else 'APP'}{i + 1:02d}",
            f"10.13.0.{40 + i}",
            role,
            rng.choice(T.OS_BUILDS),
            rng.choice(["depot1-rack-a", "depot1-rack-b", "depot2-comms", "esxi-cluster1"]),
            f"2026-0{rng.randrange(1, 8)}-{rng.randrange(10, 28)}",
            rng.choice(["yes", "yes", "no"]),
        ])
    return _csv(
        ["hostname", "ip", "role", "os", "location", "last_patched", "backed_up"],
        rows,
    )


def _passwords(doc: dict, spec: dict, rng: random.Random) -> str:
    domain = spec["company"]["domain"]
    rows = []
    for label, host, user in T.SYSTEMS:
        secret = (
            f"{rng.choice(T.FAKE_SECRET_WORDS)}-"
            f"{rng.choice(T.FAKE_SECRET_WORDS).lower()}-{rng.randrange(10, 99)}"
        )
        rows.append([
            label,
            host.format(domain=domain),
            user.format(domain=domain),
            secret,
            rng.choice(["rotate quarterly", "rotate annually", "shared - do not change"]),
        ])
    return _sheet(
        "IT SHARED CREDENTIALS - RESTRICTED (IT staff only)",
        "shared_accounts",
        ["system", "host", "username", "password", "notes"],
        rows,
        footer=[
            "Reminder: this sheet is a stop-gap until the password manager rollout",
            "completes. Do not copy off the IT share. Ticket IT-2291 tracks migration.",
        ],
    )


def _vpn_notes(doc: dict, spec: dict, rng: random.Random) -> str:
    return _memo(
        to="IT / Ops leads",
        frm="Rohan Patel, DevOps Engineer",
        date="2026-06-18",
        subject="VPN concentrator migration - runbook notes",
        body=[
            "Cutover window: Saturday 04:00-07:00 UTC. Depot 2 is the pilot site.",
            "",
            "Pre-checks",
            "  - Confirm split-tunnel profile pushed to all 41 laptops.",
            "  - Snapshot the old concentrator config; keep it 30 days.",
            "  - Freeze firewall changes 24h before the window.",
            "",
            "Cutover",
            "  - Move the jumphost route first; validate SSH from a depot laptop.",
            "  - Re-point the WMS app server health check at the new gateway.",
            "  - Watch the monitoring dashboard for auth failures over 2%.",
            "",
            "Rollback",
            "  - Re-enable the old listener and revert DNS; 15 minutes end to end.",
            "",
            "Known gaps: shared credentials still live in the IT share spreadsheet;",
            "password-manager rollout (IT-2291) should close that out next quarter.",
        ],
    )


def _salaries(doc: dict, spec: dict, rng: random.Random) -> str:
    rows = []
    for name in _sample(rng, T.STAFF_NAMES, 12):
        rows.append([
            f"E{rng.randrange(1000, 9999)}",
            name,
            rng.choice(T.DEPARTMENTS),
            rng.choice(T.JOB_TITLES),
            rng.choice(["B2", "B3", "C1", "C2", "D1"]),
            _money(rng, 32_000, 96_000, 250),
            f"{rng.randrange(0, 12)}%",
            f"2026-0{rng.randrange(1, 8)}-01",
        ])
    return _sheet(
        "SALARY REVIEW 2026 - HR CONFIDENTIAL",
        "review_2026",
        ["emp_id", "name", "department", "title", "grade",
         "base_salary_eur", "bonus_target", "effective_date"],
        rows,
        footer=[
            "Distribution: HR Manager and Managing Director only.",
            "Grade bands under review with the works council (see hr/onboarding notes).",
        ],
    )


def _org_chart(doc: dict, spec: dict, rng: random.Random) -> str:
    personas = spec["personas"]
    leads = [f"{p['full_name']} - {p['role']}" for p in personas]
    return _deck(
        "Meridian Logistics - Organisation Overview",
        "HR briefing pack, updated July 2026",
        [
            ("Purpose", [
                "Show reporting lines after the depot 2 expansion",
                "Flag three open roles ahead of the Q4 hiring freeze",
            ]),
            ("Leadership", ["Managing Director: Helena Aldritch"] + leads[:3]),
            ("Function leads", leads[3:] + [
                f"Headcount: {rng.randrange(180, 240)} across {rng.randrange(3, 6)} sites",
            ]),
            ("Open roles", [
                rng.choice(T.JOB_TITLES) + " (depot 2, backfill)",
                rng.choice(T.JOB_TITLES) + " (new, approved)",
                "Systems Administrator (new, pending budget)",
            ]),
            ("Next steps", [
                "Confirm grade bands with the works council",
                "Publish updated chart on the intranet",
                "Manager briefings week of the 20th",
            ]),
        ],
    )


def _onboarding(doc: dict, spec: dict, rng: random.Random) -> str:
    return _memo(
        to="Hiring managers",
        frm="Sophie Lee, HR Manager",
        date="2026-05-29",
        subject="New starter checklist (revision 4)",
        body=[
            "Please complete every item before day one. IT needs 5 working days.",
            "",
            " [ ] Signed contract and right-to-work check filed",
            " [ ] Payroll record created (grade and start date confirmed)",
            " [ ] IT ticket raised: laptop, SMB share access, mail account",
            " [ ] Building access card for the correct depot",
            " [ ] Buddy assigned and first-week calendar blocked",
            " [ ] Security induction booked (phishing and clear-desk modules)",
            " [ ] Fleet drivers only: licence check and tacho card",
            "",
            "Access requests go through the intranet form. Managers must not share",
            "their own credentials with new starters, even for the first day.",
        ],
    )


def _fleet(doc: dict, spec: dict, rng: random.Random) -> str:
    rows = []
    for i in range(10):
        rows.append([
            f"MER-{rng.randrange(100, 999)}-{rng.choice('ABCDEFGH')}",
            rng.choice(T.VEHICLES),
            str(rng.randrange(120, 640)),
            f"2026-0{rng.randrange(1, 8)}-{rng.randrange(10, 28)}",
            rng.choice(["service A", "service B", "brake overhaul",
                        "tyre replacement", "tacho calibration"]),
            _money(rng, 300, 4_800, 10),
            rng.choice(["depot1", "depot1", "depot2", "third-party garage"]),
        ])
    return _csv(
        ["plate", "vehicle", "odometer_k_km", "last_service",
         "work_performed", "cost_eur", "site"],
        rows,
    )


def _carrier_rates(doc: dict, spec: dict, rng: random.Random) -> str:
    rows = []
    for origin in _sample(rng, T.CITIES, 8):
        rows.append([
            f"{origin} -> Rotterdam",
            rng.choice(T.VENDORS),
            _money(rng, 400, 2_400, 10),
            f"{rng.randrange(3, 18)}%",
            f"2026-{rng.randrange(9, 12)}-30",
            rng.choice(["fixed", "fuel-indexed", "fuel-indexed"]),
        ])
    return _sheet(
        "CARRIER RATE CARD 2026 - COMMERCIALLY SENSITIVE",
        "rates_2026",
        ["lane", "carrier", "base_rate_eur", "negotiated_discount",
         "valid_until", "fuel_clause"],
        rows,
        footer=[
            "Do not share outside Ops and Finance: discounts are carrier-specific",
            "and several are below the published tariff.",
        ],
    )


def _depot_review(doc: dict, spec: dict, rng: random.Random) -> str:
    return _deck(
        "Depot Capacity Review - H2 2026",
        "Operations steering committee",
        [
            ("Where we are", [
                f"Depot 1 running at {rng.randrange(84, 97)}% pallet occupancy",
                f"Depot 2 at {rng.randrange(48, 70)}% after the racking install",
                f"Peak-week overflow cost {_money(rng, 40_000, 120_000)} EUR in H1",
            ]),
            ("Constraints", [
                "Inbound dock hours capped by the depot 1 lease",
                "Two of six reach trucks are past their service interval",
                "WMS slotting rules still assume the old layout",
            ]),
            ("Options", [
                "A: re-slot depot 1 fast movers, no capex",
                "B: shift 20% of Aldergate volume to depot 2",
                "C: short-term third-party overflow for weeks 46-52",
            ]),
            ("Recommendation", [
                "Option A now, option B from week 40, hold C as contingency",
                f"Estimated saving {_money(rng, 60_000, 180_000)} EUR versus H1 run rate",
            ]),
            ("Asks", [
                "Finance to confirm the racking capitalisation treatment",
                "IT to update WMS slotting rules before week 40",
            ]),
        ],
    )


def _pipeline(doc: dict, spec: dict, rng: random.Random) -> str:
    rows = []
    for i, customer in enumerate(_sample(rng, T.CUSTOMERS, 8)):
        rows.append([
            f"OPP-{2600 + i * 3}",
            customer,
            rng.choice(["qualify", "proposal", "negotiation", "verbal", "closed won"]),
            _money(rng, 25_000, 900_000, 500),
            f"{rng.randrange(10, 95, 5)}%",
            f"2026-{rng.randrange(8, 12)}-{rng.randrange(10, 28)}",
            "dvargas",
        ])
    return _csv(
        ["opp_id", "customer", "stage", "value_eur", "probability",
         "expected_close", "owner"],
        rows,
    )


def _account_terms(doc: dict, spec: dict, rng: random.Random) -> str:
    rows = []
    for customer in _sample(rng, T.CUSTOMERS, 6):
        rows.append([
            customer,
            f"MSA-2026-{rng.randrange(100, 999)}",
            f"{rng.randrange(15, 90)} days",
            f"{rng.randrange(2, 15)}%",
            _money(rng, 5_000, 60_000),
            f"2027-0{rng.randrange(1, 9)}-01",
            rng.choice(["auto-renew", "auto-renew", "renegotiate"]),
        ])
    return _sheet(
        "KEY ACCOUNT COMMERCIAL TERMS - RESTRICTED",
        "terms",
        ["customer", "contract_ref", "payment_terms", "volume_rebate",
         "penalty_cap_eur", "renewal_date", "renewal_status"],
        rows,
        footer=[
            "Rebate levels are not disclosed between accounts. Any variation needs",
            "Finance sign-off before it goes into a proposal.",
        ],
    )


def _audit_findings(doc: dict, spec: dict, rng: random.Random) -> str:
    return _memo(
        to="Managing Director; IT; Operations",
        frm="Anna Kowalski, Compliance Officer",
        date="2026-04-11",
        subject="Internal audit findings - Q1 2026 (draft)",
        body=[
            f"{rng.randrange(4, 9)} findings, 2 rated high. Management response due in 3 weeks.",
            "",
            "HIGH  1. Shared administrative credentials are stored in a spreadsheet",
            "         on the IT share rather than a password manager (IT-2291).",
            "HIGH  2. Leavers retained SMB share access for an average of 11 days",
            "         after their final working day.",
            "MED   3. Customs exception approvals are recorded inconsistently;",
            "         three shipments lacked a documented reason code.",
            "MED   4. Vendor bank-detail changes were accepted by email in two cases",
            "         without the required phone callback.",
            "LOW   5. Depot 2 visitor log has gaps on weekend shifts.",
            "",
            "Positive: month-end close controls were operating as designed in all",
            "three months sampled.",
        ],
    )


def _customs_exceptions(doc: dict, spec: dict, rng: random.Random) -> str:
    rows = []
    for i in range(8):
        rows.append([
            f"SHP-2026-{rng.randrange(10000, 99999)}",
            rng.choice(T.CUSTOMERS),
            rng.choice(T.CITIES),
            rng.choice(["tariff reclass", "late entry", "missing cert",
                        "valuation query", "duty deferment"]),
            _money(rng, 200, 24_000, 10),
            rng.choice(T.STAFF_NAMES),
            rng.choice(["closed", "closed", "open", "escalated"]),
        ])
    return _sheet(
        "CUSTOMS EXCEPTION LOG 2026 - COMPLIANCE CONFIDENTIAL",
        "exceptions",
        ["shipment_ref", "customer", "port", "exception_type",
         "duty_at_risk_eur", "approver", "status"],
        rows,
        footer=[
            "Every exception needs a reason code and a named approver (finding 3 of",
            "the Q1 internal audit). Escalated items go to the customs broker.",
        ],
    )


BUILDERS = {
    "Q3_forecast": _q3_forecast,
    "vendor_payments": _vendor_payments,
    "close_checklist": _close_checklist,
    "server_inventory": _server_inventory,
    "passwords": _passwords,
    "vpn_migration_notes": _vpn_notes,
    "salaries_2026": _salaries,
    "org_chart": _org_chart,
    "onboarding_checklist": _onboarding,
    "fleet_maintenance": _fleet,
    "carrier_rates_2026": _carrier_rates,
    "depot_capacity_review": _depot_review,
    "pipeline_q3": _pipeline,
    "key_account_terms": _account_terms,
    "audit_findings_2026": _audit_findings,
    "customs_exceptions": _customs_exceptions,
}


# ---------------------------------------------------------------------------
# Generic per-doc_type fallbacks (used for any path without a named builder).
# ---------------------------------------------------------------------------

def _generic(doc: dict, spec: dict, rng: random.Random) -> str:
    stem = PurePosixPath(doc["path"]).stem.replace("_", " ").title()
    dtype = doc.get("doc_type", "note")
    if dtype in ("spreadsheet", "csv"):
        rows = [
            [f"2026-0{rng.randrange(1, 8)}-{rng.randrange(10, 28)}",
             rng.choice(T.DEPARTMENTS), rng.choice(T.CITIES),
             _money(rng, 1_000, 90_000), rng.choice(["open", "closed", "review"])]
            for _ in range(8)
        ]
        headers = ["date", "department", "site", "amount_eur", "status"]
        if dtype == "csv":
            return _csv(headers, rows)
        return _sheet(f"{stem.upper()} - INTERNAL", stem[:24], headers, rows)
    if dtype == "presentation":
        return _deck(f"{stem}", "Meridian Logistics internal deck", [
            ("Context", ["Prepared for the monthly management review"]),
            ("Findings", [f"{rng.randrange(3, 9)} items tracked this period"]),
            ("Next steps", ["Owners confirmed", "Review at the next meeting"]),
        ])
    return _memo(
        to=rng.choice(T.DEPARTMENTS) + " team",
        frm=f"{doc.get('owner', 'unknown')} (Meridian Logistics)",
        date="2026-06-05",
        subject=stem,
        body=["Notes captured for internal reference.", "",
              " - Actions assigned at the last review are on track.",
              " - Two items need a decision before month end.",
              " - Follow up with the site leads on depot 2 coverage."],
    )


class OfflineContentSource:
    """Deterministic content source: templates + a fixed-seed RNG."""

    name = "offline"

    def __init__(self, n_personas: int = 5, seed: int | None = None) -> None:
        if not 4 <= n_personas <= 6:
            raise ValueError("n_personas must be between 4 and 6")
        self.n_personas = n_personas
        self.seed = T.SEED if seed is None else seed

    # -- company spec -------------------------------------------------------
    def company_spec(self) -> dict:
        """Build the full company definition (the thing written to YAML)."""
        personas: list[dict] = []
        documents: list[dict] = []
        for i, entry in enumerate(T.PERSONA_POOL[: self.n_personas]):
            docs = [dict(d) for d in entry["documents"]]
            personas.append({
                "username": entry["username"],
                "full_name": entry["full_name"],
                "role": entry["role"],
                "home_ip": f"{T.PERSONA_IP_PREFIX}{T.PERSONA_IP_BASE + i}",
                "work_hours": dict(entry["work_hours"]),
                "smb_share": entry["smb_share"],
                "files_owned": [d["path"] for d in docs],
                "activity_weights": dict(entry["activity_weights"]),
            })
            for d in docs:
                documents.append({
                    "path": d["path"],
                    "owner": entry["username"],
                    "doc_type": d["doc_type"],
                    "canary": bool(d["canary"]),
                })
        return {
            "company": dict(T.COMPANY),
            "personas": personas,
            "hosts": [dict(h) for h in T.HOSTS],
            "documents": documents,
        }

    # -- document bodies ----------------------------------------------------
    def document_body(self, doc: dict, spec: dict) -> str:
        rng = _rng(self.seed, doc["path"])
        builder = BUILDERS.get(PurePosixPath(doc["path"]).stem, _generic)
        return builder(doc, spec, rng)
