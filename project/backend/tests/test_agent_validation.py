"""Validation tests for the search agent described in design.md."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import agent  # noqa: E402
from simulator import goal_satisfied, simulate  # noqa: E402


def _scenario(
    *,
    start: str = "A",
    battery: int = 20,
    corridors: list[dict[str, Any]] | None = None,
    stations: list[dict[str, Any]] | None = None,
    goal: list[str] | None = None,
) -> dict[str, Any]:
    zone_ids = sorted(
        {start}
        | {c["from"] for c in corridors or []}
        | {c["to"] for c in corridors or []}
        | {s["zone"] for s in stations or []}
    )
    return {
        "robot": {
            "start": start,
            "battery_max": battery,
            "battery_start": battery,
            "cargo_capacity": 3,
        },
        "zones": [{"id": zone, "name": zone, "recharge": False} for zone in zone_ids],
        "corridors": corridors or [],
        "doors": [],
        "keys": [],
        "tools": [],
        "materials": [],
        "panels": [],
        "stations": stations or [],
        "chargers": [],
        "goal": {"stations_online": goal or []},
        "action_costs": {
            "pickup": 1,
            "drop": 1,
            "interact": 2,
            "recharge": 3,
        },
    }


def _station(station_id: str, zone: str) -> dict[str, Any]:
    return {
        "id": station_id,
        "kind": "test",
        "zone": zone,
        "state": "OFFLINE",
        "requires": {},
    }


def test_equivalent_states_from_different_histories_are_equal() -> None:
    # Caso 1: Estados equivalentes.
    # El robot puede llegar a D por A-B-D o por A-C-D. Como ambas rutas tienen
    # el mismo costo, la misma bateria restante y no cambian el mundo, el estado
    # logico final debe ser exactamente el mismo.
    scenario = _scenario(
        corridors=[
            {"from": "A", "to": "B", "cost": 1, "door": None},
            {"from": "B", "to": "D", "cost": 1, "door": None},
            {"from": "A", "to": "C", "cost": 1, "door": None},
            {"from": "C", "to": "D", "cost": 1, "door": None},
        ],
    )
    start = agent.initial_state(scenario)

    via_b, _ = agent._successor(start, {"kind": "MOVE", "to": "B", "cost": 1}, scenario)
    via_b, _ = agent._successor(via_b, {"kind": "MOVE", "to": "D", "cost": 1}, scenario)

    via_c, _ = agent._successor(start, {"kind": "MOVE", "to": "C", "cost": 1}, scenario)
    via_c, _ = agent._successor(via_c, {"kind": "MOVE", "to": "D", "cost": 1}, scenario)

    assert via_b == via_c
    assert hash(via_b) == hash(via_c)


def test_relevant_information_keeps_states_different() -> None:
    # Caso 2: Informacion relevante.
    # Dos estados en la misma zona y con el mismo mundo, pero con distinta
    # bateria, no son equivalentes: uno puede moverse a B y el otro no.
    scenario = _scenario(
        battery=2,
        corridors=[{"from": "A", "to": "B", "cost": 2, "door": None}],
    )
    enough_battery = agent.initial_state(scenario)
    low_battery = agent.State(
        zone=enough_battery.zone,
        battery=1,
        payload=enough_battery.payload,
        ground_keys=enough_battery.ground_keys,
        ground_tools=enough_battery.ground_tools,
        ground_materials=enough_battery.ground_materials,
        doors=enough_battery.doors,
        panels=enough_battery.panels,
        stations=enough_battery.stations,
    )

    assert enough_battery != low_battery
    assert any(action["kind"] == "MOVE" for action, _, _ in agent.successors(enough_battery, scenario))
    assert not any(action["kind"] == "MOVE" for action, _, _ in agent.successors(low_battery, scenario))


def test_ucs_prefers_lower_cost_over_fewer_actions() -> None:
    # Caso 3: Costos diferentes.
    # Hay una ruta directa A-G con una sola accion de movimiento, pero cuesta 10.
    # La ruta A-B-G usa dos movimientos, pero cuesta 2. Como UCS minimiza costo
    # total y no cantidad de pasos, debe elegir A-B-G y luego activar la estacion.
    scenario = _scenario(
        battery=20,
        corridors=[
            {"from": "A", "to": "G", "cost": 10, "door": None},
            {"from": "A", "to": "B", "cost": 1, "door": None},
            {"from": "B", "to": "G", "cost": 1, "door": None},
        ],
        stations=[_station("GOAL", "G")],
        goal=["GOAL"],
    )

    plan = agent.solve(scenario)

    assert plan["solution_found"] is True
    assert plan["total_cost"] == 4
    assert [step["op"] for step in plan["steps"]] == ["MOVE", "MOVE", "INTERACT"]
    final = simulate(scenario, plan["steps"])
    assert goal_satisfied(scenario, final)


def test_unsolvable_mission_returns_failure() -> None:
    # Caso 4: Sin solucion.
    # La meta esta en B, pero no hay corredores. El agente debe terminar y
    # devolver FAILURE en vez de quedarse explorando indefinidamente.
    scenario = _scenario(
        battery=20,
        corridors=[],
        stations=[_station("GOAL", "B")],
        goal=["GOAL"],
    )

    plan = agent.solve(scenario)

    assert plan["solution_found"] is False
    assert plan["steps"] == []
    assert plan["message"] == "FAILURE"


def test_alternative_routes_keep_the_lowest_cost_path() -> None:
    # Caso 5: Rutas alternativas.
    # Las rutas A-B-G y A-C-G llegan a las mismas condiciones del mundo, pero
    # tienen costos distintos. UCS debe conservar la alternativa mas barata.
    scenario = _scenario(
        battery=20,
        corridors=[
            {"from": "A", "to": "B", "cost": 4, "door": None},
            {"from": "B", "to": "G", "cost": 4, "door": None},
            {"from": "A", "to": "C", "cost": 1, "door": None},
            {"from": "C", "to": "G", "cost": 1, "door": None},
        ],
        stations=[_station("GOAL", "G")],
        goal=["GOAL"],
    )

    plan = agent.solve(scenario)

    assert plan["solution_found"] is True
    assert plan["total_cost"] == 4
    assert [step["to"] for step in plan["steps"] if step["op"] == "MOVE"] == ["C", "G"]
    final = simulate(scenario, plan["steps"])
    assert goal_satisfied(scenario, final)


if __name__ == "__main__":
    test_equivalent_states_from_different_histories_are_equal()
    test_relevant_information_keeps_states_different()
    test_ucs_prefers_lower_cost_over_fewer_actions()
    test_unsolvable_mission_returns_failure()
    test_alternative_routes_keep_the_lowest_cost_path()
    print("All agent validation tests passed.")
