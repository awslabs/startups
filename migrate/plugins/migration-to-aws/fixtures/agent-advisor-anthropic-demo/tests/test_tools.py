import pytest

from support_agent.tools import execute_tool, lookup_order, search_help_center


def test_lookup_order():
    assert lookup_order("A-100") == {
        "status": "shipped",
        "carrier": "Parcel Express",
    }


def test_search_help_center():
    assert search_help_center("refund")["matches"][0]["topic"] == "refund"


def test_unknown_tool_is_rejected():
    with pytest.raises(ValueError, match="unsupported tool"):
        execute_tool("delete_order", {})
