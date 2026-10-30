"""Unit tests for the NOC agent tools. These do not call the Claude API."""

import json

import anyio
import pytest

import noc_agent


@pytest.fixture(autouse=True)
def kpi_store():
    noc_agent.NODE_KPI.clear()
    noc_agent.NODE_KPI.update(noc_agent.load_kpis(noc_agent.DEFAULT_DATA_FILE))
    yield
    noc_agent.NODE_KPI.clear()


def call(tool, args):
    return anyio.run(tool.handler, args)


def test_get_node_kpi_returns_data():
    result = call(noc_agent.get_node_kpi, {"node_id": "PGW-02"})
    assert "is_error" not in result
    payload = json.loads(result["content"][0]["text"])
    assert payload["node_id"] == "PGW-02"
    assert payload["gtp_echo_timeouts"] == 27


def test_get_node_kpi_normalizes_node_id():
    result = call(noc_agent.get_node_kpi, {"node_id": "  pgw-02 "})
    assert "is_error" not in result


def test_get_node_kpi_unknown_node():
    result = call(noc_agent.get_node_kpi, {"node_id": "XYZ-99"})
    assert result["is_error"] is True
    assert "not found" in result["content"][0]["text"]


@pytest.mark.parametrize("bad", ["", "   ", None, 42])
def test_get_node_kpi_invalid_input(bad):
    result = call(noc_agent.get_node_kpi, {"node_id": bad})
    assert result["is_error"] is True


def test_list_nodes():
    result = call(noc_agent.list_nodes, {})
    nodes = json.loads(result["content"][0]["text"])
    assert nodes["MME-01"] == "MME"
    assert set(nodes) == {"MME-01", "SGW-01", "PGW-02", "HSS-01"}


def test_load_kpis_rejects_bad_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"foo": 1}', encoding="utf-8")
    with pytest.raises(ValueError):
        noc_agent.load_kpis(bad)
