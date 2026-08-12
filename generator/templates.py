"""Built-in templates for the offline (no-API-key) decoy generator.

Everything here is 100% synthetic: invented company, invented people, invented
numbers. Nothing in this file corresponds to a real organisation, person, or
credential — it exists purely to make a honeypot filesystem look lived-in.

The roster below is intentionally *data*, not code: both the offline generator
and the AI generator emit the same shape, so the output-writing code in
`generator.generate` never has to care which produced it.
"""

from __future__ import annotations

# Fixed seed => byte-identical output on every offline run (tests rely on this).
SEED = 20260812

CANARY_PREFIX = "CANARY-TOKEN:"

COMPANY = {
    "name": "Meridian Logistics",
    "domain": "meridian-logistics.local",
    "subnet": "10.13.0.0/24",
}

# Same decoy + trap hosts as config/company.example.yaml. The two `is_trap`
# hosts are pure honeypots: no persona ever touches them, so any hit is an alert.
HOSTS = [
    {"name": "fileserver", "ip": "10.13.0.10", "services": ["smb"], "is_trap": False},
    {"name": "intranet", "ip": "10.13.0.11", "services": ["http"], "is_trap": False},
    {"name": "jumphost", "ip": "10.13.0.12", "services": ["ssh"], "is_trap": False},
    {"name": "mail", "ip": "10.13.0.13", "services": ["smtp"], "is_trap": False},
    {"name": "cowrie-ssh", "ip": "10.13.0.30", "services": ["ssh", "telnet"], "is_trap": True},
    {
        "name": "canary-multi",
        "ip": "10.13.0.31",
        "services": ["ftp", "http", "mysql", "smb"],
        "is_trap": True,
    },
]

# First persona gets 10.13.0.21, next 10.13.0.22, ... (see PERSONA_IP_BASE).
PERSONA_IP_PREFIX = "10.13.0."
PERSONA_IP_BASE = 21

# 6 candidates; the generator takes the first `n_personas` (default 5).
PERSONA_POOL: list[dict] = [
    {
        "username": "jchen",
        "full_name": "Jia Chen",
        "role": "Finance Analyst",
        "work_hours": {"start": "08:45", "end": "17:15", "tz": "UTC", "days": [0, 1, 2, 3, 4]},
        "smb_share": "finance",
        "activity_weights": {
            "open_file": 5, "edit_file": 3, "share_file": 1,
            "browse": 2, "send_mail": 2, "ssh": 0,
        },
        "documents": [
            {"path": "finance/Q3_forecast.xlsx", "doc_type": "spreadsheet", "canary": False},
            {"path": "finance/vendor_payments.xlsx", "doc_type": "spreadsheet", "canary": True},
            {"path": "finance/close_checklist.txt", "doc_type": "note", "canary": False},
        ],
    },
    {
        "username": "rpatel",
        "full_name": "Rohan Patel",
        "role": "DevOps Engineer",
        "work_hours": {"start": "09:30", "end": "18:00", "tz": "UTC", "days": [0, 1, 2, 3, 4]},
        "smb_share": "it",
        "activity_weights": {
            "open_file": 3, "edit_file": 2, "share_file": 1,
            "browse": 3, "send_mail": 1, "ssh": 4,
        },
        "documents": [
            {"path": "it/server_inventory.csv", "doc_type": "csv", "canary": False},
            # The classic lure: looks like the crown jewels, is actually a tripwire.
            {"path": "it/passwords.xlsx", "doc_type": "spreadsheet", "canary": True},
            {"path": "it/vpn_migration_notes.txt", "doc_type": "note", "canary": False},
        ],
    },
    {
        "username": "slee",
        "full_name": "Sophie Lee",
        "role": "HR Manager",
        "work_hours": {"start": "09:00", "end": "17:00", "tz": "UTC", "days": [0, 1, 2, 3, 4]},
        "smb_share": "hr",
        "activity_weights": {
            "open_file": 4, "edit_file": 2, "share_file": 2,
            "browse": 3, "send_mail": 3, "ssh": 0,
        },
        "documents": [
            {"path": "hr/salaries_2026.xlsx", "doc_type": "spreadsheet", "canary": True},
            {"path": "hr/org_chart.pptx", "doc_type": "presentation", "canary": False},
            {"path": "hr/onboarding_checklist.txt", "doc_type": "note", "canary": False},
        ],
    },
    {
        "username": "mokafor",
        "full_name": "Miriam Okafor",
        "role": "Operations Director",
        "work_hours": {"start": "07:30", "end": "16:00", "tz": "UTC", "days": [0, 1, 2, 3, 4]},
        "smb_share": "ops",
        "activity_weights": {
            "open_file": 4, "edit_file": 3, "share_file": 2,
            "browse": 2, "send_mail": 4, "ssh": 0,
        },
        "documents": [
            {"path": "ops/fleet_maintenance.csv", "doc_type": "csv", "canary": False},
            {"path": "ops/carrier_rates_2026.xlsx", "doc_type": "spreadsheet", "canary": True},
            {"path": "ops/depot_capacity_review.pptx", "doc_type": "presentation", "canary": False},
        ],
    },
    {
        "username": "dvargas",
        "full_name": "Diego Vargas",
        "role": "Enterprise Account Manager",
        "work_hours": {"start": "09:15", "end": "18:15", "tz": "UTC", "days": [0, 1, 2, 3, 4]},
        "smb_share": "sales",
        "activity_weights": {
            "open_file": 3, "edit_file": 2, "share_file": 3,
            "browse": 4, "send_mail": 4, "ssh": 0,
        },
        "documents": [
            {"path": "sales/pipeline_q3.csv", "doc_type": "csv", "canary": False},
            {"path": "sales/key_account_terms.xlsx", "doc_type": "spreadsheet", "canary": True},
        ],
    },
    {
        "username": "akowal",
        "full_name": "Anna Kowalski",
        "role": "Compliance Officer",
        "work_hours": {"start": "08:30", "end": "16:30", "tz": "UTC", "days": [0, 1, 2, 3]},
        "smb_share": "legal",
        "activity_weights": {
            "open_file": 5, "edit_file": 2, "share_file": 1,
            "browse": 3, "send_mail": 2, "ssh": 0,
        },
        "documents": [
            {"path": "legal/audit_findings_2026.txt", "doc_type": "note", "canary": False},
            {"path": "legal/customs_exceptions.xlsx", "doc_type": "spreadsheet", "canary": True},
        ],
    },
]

# ---------------------------------------------------------------------------
# Content pools used to fill tables/memos with plausible-looking filler.
# ---------------------------------------------------------------------------

STAFF_NAMES = [
    "Amara Boateng", "Ben Halvorsen", "Carla Espinoza", "Dmitri Volkov",
    "Elena Marchetti", "Farid Haddad", "Grace Nakamura", "Hugo Lindqvist",
    "Imani Sorenson", "Jonas Ferreira", "Keiko Tanaka", "Leon Mbeki",
    "Maya Rasmussen", "Nikhil Rao", "Oksana Petrenko", "Priya Deshmukh",
    "Quentin Aubert", "Rosa Delgado", "Samir El-Amin", "Tomas Novak",
]

DEPARTMENTS = [
    "Finance", "Operations", "Human Resources", "IT", "Sales",
    "Warehouse", "Customer Care", "Compliance",
]

JOB_TITLES = [
    "Logistics Coordinator", "Warehouse Supervisor", "Freight Analyst",
    "Payroll Specialist", "Systems Administrator", "Account Executive",
    "Customs Broker", "Fleet Technician", "Dispatch Planner",
    "Procurement Officer",
]

VENDORS = [
    "Northwind Freight Ltd", "Halcyon Packaging", "Ridgeway Fuel Services",
    "Sentinel Facilities", "Brightlane Software", "Corvus Customs Agency",
    "Ironvale Steel Racking", "Aurora Telecom", "Meadowbrook Cleaning",
    "Stanton Legal Advisory",
]

CUSTOMERS = [
    "Aldergate Retail Group", "Bluewater Grocers", "Cinder & Co Manufacturing",
    "Delphi Pharma Nordics", "Everline Apparel", "Foxglove Home Goods",
    "Granite Bay Beverages", "Harborline Electronics",
]

CITIES = [
    "Rotterdam", "Hamburg", "Gdansk", "Lyon", "Bilbao",
    "Antwerp", "Bristol", "Trieste", "Aarhus", "Porto",
]

SERVER_ROLES = [
    "file server", "domain controller", "print server", "WMS app server",
    "WMS database", "backup target", "monitoring", "reverse proxy",
    "mail relay", "build agent",
]

OS_BUILDS = [
    "Windows Server 2019", "Windows Server 2022", "Ubuntu 22.04 LTS",
    "Ubuntu 24.04 LTS", "Debian 12", "RHEL 9",
]

VEHICLES = [
    "MAN TGX 18.510", "Volvo FH16", "Scania R450", "DAF XF 480",
    "Mercedes Actros 1845", "Iveco S-Way 490",
]

# Obviously-fake credential filler for the honeypot "passwords" lure. These are
# nonsense strings that authenticate to nothing; they exist to be stolen.
FAKE_SECRET_WORDS = [
    "Harbour", "Lantern", "Quartz", "Meridian", "Palisade", "Tundra",
    "Verdant", "Zephyr", "Cobalt", "Kestrel",
]

SYSTEMS = [
    ("WMS admin console", "wms.{domain}", "svc_wms"),
    ("Freight portal (carrier)", "portal.northwind-freight.example", "meridian_ops"),
    ("Backup appliance", "backup01.{domain}", "backupadmin"),
    ("Payroll SaaS", "payroll.example", "s.lee@{domain}"),
    ("Core switch stack", "10.13.0.1", "netadmin"),
    ("MySQL reporting replica", "10.13.0.31", "report_ro"),
    ("VPN concentrator", "vpn.{domain}", "vpnadmin"),
    ("CCTV NVR (depot 2)", "10.13.0.44", "operator"),
]
