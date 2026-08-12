"""Tests for the Decoy Generator.

Everything runs through the offline (no-API-key) path and writes into tmp_path,
so the suite never needs a network, a key, or the repo's real output files.
"""

from __future__ import annotations

import json
import re

import pytest

from core.config import load_company
from generator import templates as T
from generator.generate import generate

CANARY_RE = re.compile(r"CANARY-TOKEN:[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    """One offline generation run, reused across the read-only assertions."""
    out = tmp_path_factory.mktemp("gen")
    return generate(
        config_path=out / "config" / "company.yaml",
        seed_dir=out / "seed" / "generated",
        use_ai=False,
    )


def test_offline_mode_is_used(run):
    assert run.mode == "offline"
    assert run.warnings == []


def test_company_yaml_parses_into_valid_company(run):
    company = load_company(str(run.config_path))

    assert company.name and company.domain and company.subnet
    assert len(company.personas) >= 4

    seen_users, seen_ips = set(), set()
    for p in company.personas:
        assert p.username and p.username == p.username.lower()
        assert p.full_name and p.role and p.smb_share
        assert p.home_ip.startswith("10.13.0.2"), p.home_ip
        assert re.fullmatch(r"\d{2}:\d{2}", p.work_hours.start)
        assert re.fullmatch(r"\d{2}:\d{2}", p.work_hours.end)
        assert p.work_hours.days and all(0 <= d <= 6 for d in p.work_hours.days)
        assert p.files_owned
        assert sum(p.activity_weights.values()) > 0
        # cross-referencing helpers used by the rest of the lab must resolve
        assert company.persona_by_username(p.username) is p
        assert company.persona_by_ip(p.home_ip) is p
        seen_users.add(p.username)
        seen_ips.add(p.home_ip)
    assert len(seen_users) == len(company.personas)
    assert len(seen_ips) == len(company.personas)


def test_hosts_include_the_same_traps_as_the_example(run):
    company = load_company(str(run.config_path))
    names = {h.name for h in company.hosts}
    assert {"fileserver", "intranet", "jumphost", "mail"} <= names
    assert {h.name for h in company.trap_hosts()} == {"cowrie-ssh", "canary-multi"}
    for h in company.hosts:
        assert h.services


def test_every_document_is_owned_and_written(run):
    company = load_company(str(run.config_path))
    assert company.documents
    for doc in company.documents:
        assert company.persona_by_username(doc.owner) is not None
        path = run.seed_dir / doc.path
        assert path.is_file(), f"missing decoy file: {doc.path}"
        assert len(path.read_text().strip()) > 100, doc.path
        assert doc.path in company.persona_by_username(doc.owner).files_owned


def test_canary_documents_carry_a_marker_and_match_the_manifest(run):
    company = load_company(str(run.config_path))
    canary_docs = [d for d in company.documents if d.canary]
    assert len(canary_docs) >= 2

    assert run.manifest_path.is_file()
    manifest = json.loads(run.manifest_path.read_text())
    tokens = manifest["tokens"]

    assert set(tokens.values()) == {d.path for d in canary_docs}
    assert len(set(tokens)) == len(canary_docs)      # one unique token per doc
    assert tokens == run.canaries

    for token, doc_path in tokens.items():
        assert CANARY_RE.fullmatch(token), token
        body = (run.seed_dir / doc_path).read_text()
        assert token in body
        assert body.count(T.CANARY_PREFIX) == 1


def test_non_canary_documents_contain_no_marker(run):
    company = load_company(str(run.config_path))
    plain = [d for d in company.documents if not d.canary]
    assert plain
    for doc in plain:
        body = (run.seed_dir / doc.path).read_text()
        assert T.CANARY_PREFIX not in body, doc.path


def test_documents_look_like_their_doc_type(run):
    company = load_company(str(run.config_path))
    for doc in company.documents:
        body = (run.seed_dir / doc.path).read_text()
        if doc.doc_type == "csv":
            lines = [ln for ln in body.splitlines() if ln and not ln.startswith("#")]
            assert len(lines) >= 3
            width = len(lines[0].split(","))
            assert width >= 3
            assert all(len(ln.split(",")) == width for ln in lines[1:]), doc.path
        elif doc.doc_type == "spreadsheet":
            assert "[sheet:" in body and "," in body, doc.path
        elif doc.doc_type == "note":
            assert "INTERNAL MEMO" in body and "SUBJECT:" in body, doc.path
        elif doc.doc_type == "presentation":
            assert "Slide 1:" in body and "  - " in body, doc.path


def test_offline_output_is_deterministic(tmp_path):
    a = generate(config_path=tmp_path / "a.yaml", seed_dir=tmp_path / "a", use_ai=False)
    b = generate(config_path=tmp_path / "b.yaml", seed_dir=tmp_path / "b", use_ai=False)

    assert a.config_path.read_bytes() == b.config_path.read_bytes()
    assert a.canaries == b.canaries
    assert a.manifest_path.read_bytes() == b.manifest_path.read_bytes()
    for doc_a in a.documents:
        doc_b = b.seed_dir / doc_a.relative_to(a.seed_dir)
        assert doc_a.read_bytes() == doc_b.read_bytes()


@pytest.mark.parametrize("n", [4, 5, 6])
def test_persona_count_is_configurable(tmp_path, n):
    res = generate(
        config_path=tmp_path / f"{n}.yaml", seed_dir=tmp_path / str(n),
        use_ai=False, n_personas=n,
    )
    company = load_company(str(res.config_path))
    assert len(company.personas) == n
    assert [p.home_ip for p in company.personas] == [
        f"10.13.0.{21 + i}" for i in range(n)
    ]


def test_generator_does_not_need_an_api_key(monkeypatch, tmp_path):
    """With no key, the default (use_ai=None) path must pick the offline source."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = generate(config_path=tmp_path / "c.yaml", seed_dir=tmp_path / "d")
    assert res.mode == "offline"
    assert res.canaries
