from mcp_drone_os.drone_agent import unit_name


def test_unit_names_are_safe_and_bounded():
    value = unit_name("bad task/id" * 100)
    assert value.startswith("mcp-drone-task-")
    assert len(value) <= 196
    assert "/" not in value
