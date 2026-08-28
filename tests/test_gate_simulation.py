import asyncio
from app.services.gates import SimulatedGateController


def test_gate_simulation():
    gate = type("Gate", (), {"name": "1#"})()
    result = asyncio.run(SimulatedGateController().open(gate, [], "test"))
    assert result.ok and result.simulated
