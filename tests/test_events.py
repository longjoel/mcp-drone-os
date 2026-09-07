from mcp_drone_os.events import append_event, make_event, read_events


def test_events_are_append_only_and_filterable(tmp_path):
    path = tmp_path / "events.jsonl"
    append_event(path, make_event("alpha", "user", "task.created", {"task_id": "t1"}))
    append_event(path, make_event("beta", "user", "task.created"))
    assert len(read_events(path, "alpha")) == 1
    assert read_events(path, "alpha")[0]["payload"]["task_id"] == "t1"
