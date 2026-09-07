import pytest

from mcp_drone_os.shares import render_shares, share_block


def test_share_is_scoped_to_agent_root():
    block = share_block("alpha", "/srv/mcp-drone/agents")
    assert "path = /srv/mcp-drone/agents/alpha" in block
    assert "valid users = drone-alpha" in block


def test_share_rejects_traversal_and_duplicates():
    with pytest.raises(ValueError):
        share_block("../alpha")
    with pytest.raises(ValueError):
        render_shares(["alpha", "alpha"])
