from mcp_drone_os.mcp_stdio import dispatch
from mcp_drone_os.coordinator import Coordinator
from mcp_drone_os.state import State


def test_batch_submission_through_mcp_contract():
    coordinator = Coordinator(State())
    response = dispatch(coordinator, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": "register_drone", "arguments": {
                                          "drone_id": "d1", "hostname": "d1", "address": "10.0.0.2", "capabilities": [], "slots": 12}}})
    assert response["result"]["structuredContent"]["drone_id"] == "d1"
    response = dispatch(coordinator, {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": "run_jobs", "arguments": {
                                          "agent_id": "alpha", "jobs": [{"name": str(i)} for i in range(12)], "drone_id": "d1", "dispatch": False}}})
    assert len(response["result"]["structuredContent"]) == 12
