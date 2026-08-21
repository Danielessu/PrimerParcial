"""Agente de búsqueda para la misión Emergency Control.

La organización sigue el diseño del agente en design.md: estado canónico,
transiciones deterministas, prueba de meta, dominancia de costo/batería y
búsqueda de costo uniforme sobre el grafo de estados. El escenario siempre es
la fuente de los datos; este archivo no contiene posiciones, costos ni objetos
fijos.
"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import itertools
from typing import Any, Iterable


Token = tuple[str, str]


# --- 1. ESTADO DEL MUNDO ---
#
# Esta clase es la fotografía física del robot y de la instalación. El costo
# acumulado y la historia de búsqueda viven en Node, no en State.
@dataclass(frozen=True)
class State:
	zone: str
	battery: int
	payload: tuple[Token, ...]
	ground_keys: tuple[tuple[str, str], ...]
	ground_tools: tuple[tuple[str, str], ...]
	ground_materials: tuple[tuple[str, str, int], ...]
	doors: tuple[tuple[str, str], ...]
	panels: tuple[tuple[str, str], ...]
	stations: tuple[tuple[str, str], ...]


@dataclass
class Node:
	"""Nodo de búsqueda: estado físico, costo acumulado y acciones del camino."""

	state: State
	cost: int
	actions: tuple[dict[str, Any], ...]


def _sorted_pairs(values: dict[str, str]) -> tuple[tuple[str, str], ...]:
	return tuple(sorted(values.items()))


def _sorted_materials(
	values: dict[tuple[str, str], int],
) -> tuple[tuple[str, str, int], ...]:
	return tuple(
		sorted((kind, zone, count) for (kind, zone), count in values.items() if count > 0)
	)


def _maps(
	state: State,
) -> tuple[dict[str, str], dict[str, str], dict[tuple[str, str], int]]:
	return (
		dict(state.ground_keys),
		dict(state.ground_tools),
		{(kind, zone): count for kind, zone, count in state.ground_materials if count > 0},
	)


def _state_with(
	state: State,
	*,
	zone: str | None = None,
	battery: int | None = None,
	payload: Iterable[Token] | None = None,
	ground_keys: dict[str, str] | None = None,
	ground_tools: dict[str, str] | None = None,
	ground_materials: dict[tuple[str, str], int] | None = None,
	doors: dict[str, str] | None = None,
	panels: dict[str, str] | None = None,
	stations: dict[str, str] | None = None,
) -> State:
	current_keys, current_tools, current_materials = _maps(state)
	return State(
		zone=state.zone if zone is None else zone,
		battery=state.battery if battery is None else battery,
		payload=state.payload if payload is None else tuple(sorted(payload)),
		ground_keys=_sorted_pairs(current_keys if ground_keys is None else ground_keys),
		ground_tools=_sorted_pairs(current_tools if ground_tools is None else ground_tools),
		ground_materials=_sorted_materials(
			current_materials if ground_materials is None else ground_materials
		),
		doors=state.doors if doors is None else _sorted_pairs(doors),
		panels=state.panels if panels is None else _sorted_pairs(panels),
		stations=state.stations if stations is None else _sorted_pairs(stations),
	)


def _costs(scenario: dict[str, Any]) -> dict[str, int]:
	return {key: int(value) for key, value in scenario.get("action_costs", {}).items()}


def _payload_weight(state: State, scenario: dict[str, Any]) -> int:
	"""Calcula el peso de la carga; no lo almacena como otra variable."""
	keys = {item["id"]: item for item in scenario.get("keys", [])}
	tools = {item["id"]: item for item in scenario.get("tools", [])}
	materials = {item["type"]: item for item in scenario.get("materials", [])}
	total = 0
	for kind, name in state.payload:
		if kind == "key":
			total += int(keys.get(name, {}).get("weight", 1))
		elif kind == "tool":
			total += int(tools.get(name, {}).get("weight", 1))
		else:
			total += int(materials.get(name, {}).get("weight", 1))
	return total


def _token_weight(token: Token, scenario: dict[str, Any]) -> int:
	kind, name = token
	if kind == "key":
		col = {item["id"]: item for item in scenario.get("keys", [])}
	elif kind == "tool":
		col = {item["id"]: item for item in scenario.get("tools", [])}
	else:
		col = {item["type"]: item for item in scenario.get("materials", [])}
	return int(col.get(name, {}).get("weight", 1))


def _is_dead(token: Token, state: State, scenario: dict[str, Any]) -> bool:
	"""Determina si un objeto ya no puede habilitar ninguna acción futura."""
	kind, name = token
	if kind == "key":
		for door in scenario.get("doors", []):
			if door["key"] == name and dict(state.doors).get(door["id"]) != "OPEN":
				return False
		return True
	if kind == "tool":
		return not any(
			dict(state.panels).get(panel["id"]) == "DAMAGED"
			and panel["requires"]["tool"] == name
			for panel in scenario.get("panels", [])
		)
	return not any(
		dict(state.panels).get(panel["id"]) == "DAMAGED"
		and panel["requires"]["material"] == name
		for panel in scenario.get("panels", [])
	)


def _goal_station_ids(scenario: dict[str, Any]) -> set[str]:
	"""Estaciones que importan para la meta, incluyendo dependencias."""
	needed = set(scenario.get("goal", {}).get("stations_online", []))
	changed = True
	while changed:
		changed = False
		for station in scenario.get("stations", []):
			if station["id"] in needed:
				for required in station.get("requires", {}).get("stations_online", []):
					if required not in needed:
						needed.add(required)
						changed = True
	return needed


def _active_panels(state: State, scenario: dict[str, Any]) -> set[str]:
	"""Paneles que ya pueden acercar una estación relevante a ONLINE."""
	stations = dict(state.stations)
	active: set[str] = set()
	for station in scenario.get("stations", []):
		if station["id"] not in _goal_station_ids(scenario):
			continue
		if stations.get(station["id"]) == "ONLINE":
			continue
		required_stations = station.get("requires", {}).get("stations_online", [])
		if any(stations.get(station_id) != "ONLINE" for station_id in required_stations):
			continue
		active.update(station.get("requires", {}).get("panels_ok", []))
	return active


def _needed_ground_tokens(state: State, scenario: dict[str, Any]) -> set[Token]:
	"""Encuentra llaves, herramientas y materiales requeridos que no están en la carga."""
	doors = dict(state.doors)
	panels = dict(state.panels)
	active_panels = _active_panels(state, scenario)
	needed: set[Token] = set()

	for door in scenario.get("doors", []):
		if doors.get(door["id"]) == "CLOSED":
			k_token = ("key", door["key"])
			if k_token not in state.payload:
				needed.add(k_token)

	for panel in scenario.get("panels", []):
		if panel["id"] in active_panels and panels.get(panel["id"]) == "DAMAGED":
			t_token = ("tool", panel["requires"]["tool"])
			if t_token not in state.payload:
				needed.add(t_token)

	mat_needed: dict[str, int] = {}
	for panel in scenario.get("panels", []):
		if panel["id"] in active_panels and panels.get(panel["id"]) == "DAMAGED":
			m = panel["requires"]["material"]
			mat_needed[m] = mat_needed.get(m, 0) + 1
	for kind, name in state.payload:
		if kind == "material" and name in mat_needed:
			mat_needed[name] -= 1

	for m, count in mat_needed.items():
		if count > 0:
			needed.add(("material", m))

	return needed


def _canonicalize(state: State, scenario: dict[str, Any]) -> State:
	"""Ignora objetos muertos en el suelo para evitar permutaciones inútiles."""
	keys, tools, materials = _maps(state)
	keys = {
		name: zone for name, zone in keys.items()
		if not _is_dead(("key", name), state, scenario)
	}
	tools = {
		name: zone for name, zone in tools.items()
		if not _is_dead(("tool", name), state, scenario)
	}
	materials = {
		(kind, zone): count for (kind, zone), count in materials.items()
		if not _is_dead(("material", kind), state, scenario)
	}
	return _state_with(
		state,
		ground_keys=keys,
		ground_tools=tools,
		ground_materials=materials,
	)


def initial_state(scenario: dict[str, Any]) -> State:
	"""Construye el estado inicial usando únicamente el escenario recibido."""
	ground_keys = {item["id"]: item["zone"] for item in scenario.get("keys", [])}
	ground_tools = {item["id"]: item["zone"] for item in scenario.get("tools", [])}
	ground_materials: dict[tuple[str, str], int] = {}
	for item in scenario.get("materials", []):
		count = int(item.get("count", 0))
		if count > 0:
			key = (item["type"], item["zone"])
			ground_materials[key] = ground_materials.get(key, 0) + count

	state = State(
		zone=scenario["robot"]["start"],
		battery=int(scenario["robot"]["battery_start"]),
		payload=(),
		ground_keys=_sorted_pairs(ground_keys),
		ground_tools=_sorted_pairs(ground_tools),
		ground_materials=_sorted_materials(ground_materials),
		doors=_sorted_pairs({item["id"]: item["state"] for item in scenario.get("doors", [])}),
		panels=_sorted_pairs({item["id"]: item["state"] for item in scenario.get("panels", [])}),
		stations=_sorted_pairs({item["id"]: item["state"] for item in scenario.get("stations", [])}),
	)
	return _canonicalize(state, scenario)


def _ground_items(state: State) -> list[tuple[Token, str]]:
	keys = [(('key', name), zone) for name, zone in state.ground_keys]
	tools = [(('tool', name), zone) for name, zone in state.ground_tools]
	materials = [
		(('material', kind), zone)
		for kind, zone, count in state.ground_materials
		if count > 0
	]
	return keys + tools + materials


def _drop_is_relevant(state: State, token: Token, scenario: dict[str, Any]) -> bool:
	"""Aplica la poda de DROP definida en design.md.

	DROP solo se busca si el objeto ya no cambia el futuro o si hace falta
	liberar capacidad para recoger algo necesario en la zona actual.
	"""
	if _is_dead(token, state, scenario):
		return True
	capacity = int(scenario["robot"]["cargo_capacity"])
	cur_weight = _payload_weight(state, scenario)
	if cur_weight == capacity:
		needed = _needed_ground_tokens(state, scenario)
		has_ground_req = any(z == state.zone and t in needed for t, z in _ground_items(state))
		if has_ground_req:
			return True
	return False


# --- 2. MODELO DE TRANSICIÓN ---
#
# Cada transición es determinista y parcial: si una precondición falla, no se
# crea un sucesor. Los efectos se aplican sobre una copia canónica del estado.
def _successor(
	state: State, action: dict[str, Any], scenario: dict[str, Any]
) -> tuple[State, int] | None:
	cost = int(action["cost"])
	if state.battery < cost:
		return None

	kind = action["kind"]
	keys, tools, materials = _maps(state)
	doors, panels, stations = map(dict, (state.doors, state.panels, state.stations))
	payload = list(state.payload)

	if kind == "MOVE":
		destination = action["to"]
		corridor = next(
			(item for item in scenario.get("corridors", [])
			 if item["from"] == state.zone and item["to"] == destination),
			None,
		)
		if corridor is None or (corridor.get("door") and doors.get(corridor["door"]) != "OPEN"):
			return None
		return _state_with(state, zone=destination, battery=state.battery - cost), cost

	if kind == "PICKUP":
		token = action["item"]
		if _payload_weight(state, scenario) + _token_weight(token, scenario) > int(scenario["robot"]["cargo_capacity"]):
			return None
		token_kind, name = token
		if token_kind == "key" and keys.get(name) == state.zone:
			del keys[name]
		elif token_kind == "tool" and tools.get(name) == state.zone:
			del tools[name]
		elif token_kind == "material" and (name, state.zone) in materials and materials[(name, state.zone)] > 0:
			count = materials[(name, state.zone)]
			if count <= 1:
				del materials[(name, state.zone)]
			else:
				materials[(name, state.zone)] = count - 1
		else:
			return None
		payload.append(token)
		return _state_with(
			state,
			battery=state.battery - cost,
			payload=payload,
			ground_keys=keys,
			ground_tools=tools,
			ground_materials=materials,
		), cost

	if kind == "DROP":
		token = action["item"]
		if token not in payload:
			return None
		payload.remove(token)
		token_kind, name = token
		if _is_dead(token, state, scenario):
			return _state_with(state, battery=state.battery - cost, payload=payload), cost
		if token_kind == "key":
			keys[name] = state.zone
		elif token_kind == "tool":
			tools[name] = state.zone
		else:
			mkey = (name, state.zone)
			materials[mkey] = materials.get(mkey, 0) + 1
		return _state_with(
			state,
			battery=state.battery - cost,
			payload=payload,
			ground_keys=keys,
			ground_tools=tools,
			ground_materials=materials,
		), cost

	if kind == "OPEN_DOOR":
		door = next((item for item in scenario.get("doors", []) if item["id"] == action["target"]), None)
		if door is None or doors.get(door["id"]) != "CLOSED" or state.zone not in door["between"]:
			return None
		if ("key", door["key"]) not in payload:
			return None
		doors[door["id"]] = "OPEN"
		return _state_with(state, battery=state.battery - cost, doors=doors), cost

	if kind == "REPAIR":
		panel = next((item for item in scenario.get("panels", []) if item["id"] == action["target"]), None)
		if panel is None or state.zone != panel["zone"] or panels.get(panel["id"]) != "DAMAGED":
			return None
		material = panel["requires"]["material"]
		if ("tool", panel["requires"]["tool"]) not in payload or ("material", material) not in payload:
			return None
		payload.remove(("material", material))
		panels[panel["id"]] = "OK"
		return _state_with(state, battery=state.battery - cost, payload=payload, panels=panels), cost

	if kind == "ACTIVATE":
		station = next((item for item in scenario.get("stations", []) if item["id"] == action["target"]), None)
		if station is None or state.zone != station["zone"] or stations.get(station["id"]) != "OFFLINE":
			return None
		if any(panels.get(pid) != "OK" for pid in station.get("requires", {}).get("panels_ok", [])):
			return None
		if any(stations.get(sid) != "ONLINE" for sid in station.get("requires", {}).get("stations_online", [])):
			return None
		stations[station["id"]] = "ONLINE"
		return _state_with(state, battery=state.battery - cost, stations=stations), cost

	if kind == "RECHARGE":
		charger = next((item for item in scenario.get("chargers", []) if item["id"] == action["target"]), None)
		if charger is None or charger["zone"] != state.zone or state.battery >= int(scenario["robot"]["battery_max"]):
			return None
		return _state_with(state, battery=int(scenario["robot"]["battery_max"])), cost

	return None


# --- 3. APPLICABLE Y GENERACIÓN DE SUCESORES ---
def successors(state: State, scenario: dict[str, Any]) -> list[tuple[dict[str, Any], State, int]]:
	costs = _costs(scenario)
	actions: list[dict[str, Any]] = []

	# 1. Abrir puertas (cuando la llave está en carga y el robot está en el corredor)
	for door in scenario.get("doors", []):
		if dict(state.doors).get(door["id"]) == "CLOSED" and state.zone in door["between"]:
			if ("key", door["key"]) in state.payload:
				actions.append({"kind": "OPEN_DOOR", "target": door["id"], "cost": costs["interact"]})

	# 2. Reparar paneles dañados
	for panel in scenario.get("panels", []):
		if dict(state.panels).get(panel["id"]) == "DAMAGED" and state.zone == panel["zone"]:
			mat = panel["requires"]["material"]
			tool = panel["requires"]["tool"]
			if ("tool", tool) in state.payload and ("material", mat) in state.payload:
				actions.append({"kind": "REPAIR", "target": panel["id"], "cost": costs["interact"]})

	# 3. Activar estaciones si sus dependencias están resueltas
	for station in scenario.get("stations", []):
		if dict(state.stations).get(station["id"]) == "OFFLINE" and state.zone == station["zone"]:
			panels_ok = all(dict(state.panels).get(pid) == "OK" for pid in station.get("requires", {}).get("panels_ok", []))
			stations_ok = all(dict(state.stations).get(sid) == "ONLINE" for sid in station.get("requires", {}).get("stations_online", []))
			if panels_ok and stations_ok:
				actions.append({"kind": "ACTIVATE", "target": station["id"], "cost": costs["interact"]})

	# 4. Recargar batería si estamos en zona con cargador
	for charger in scenario.get("chargers", []):
		if charger["zone"] == state.zone and state.battery < int(scenario["robot"]["battery_max"]):
			actions.append({"kind": "RECHARGE", "target": charger["id"], "cost": costs["recharge"]})

	# 5. Descartar objetos muertos de la carga con prioridad
	dead_in_payload = [t for t in state.payload if _is_dead(t, state, scenario)]
	for token in dead_in_payload:
		actions.append({"kind": "DROP", "item": token, "cost": costs["drop"]})

	if not dead_in_payload:
		needed = _needed_ground_tokens(state, scenario)
		capacity = int(scenario["robot"]["cargo_capacity"])
		cur_weight = _payload_weight(state, scenario)

		# 6. Recoger objetos necesarios en la zona actual
		for token, zone in _ground_items(state):
			if zone == state.zone and token in needed:
				if cur_weight + _token_weight(token, scenario) <= capacity:
					actions.append({"kind": "PICKUP", "item": token, "cost": costs["pickup"]})

		# 7. Soltar objetos solo cuando el DROP es relevante para la búsqueda
		for token in state.payload:
			if _drop_is_relevant(state, token, scenario):
				actions.append({"kind": "DROP", "item": token, "cost": costs["drop"]})

		# 8. Desplazamientos por corredores abiertos
		for corridor in scenario.get("corridors", []):
			if corridor["from"] == state.zone:
				door_id = corridor.get("door")
				if not door_id or dict(state.doors).get(door_id) == "OPEN":
					actions.append({"kind": "MOVE", "to": corridor["to"], "cost": corridor["cost"]})

	result = []
	for action in actions:
		transition = _successor(state, action, scenario)
		if transition is not None:
			next_state, cost = transition
			result.append((action, _canonicalize(next_state, scenario), cost))
	return result


# --- 4. PRUEBA DE META Y DOMINANCIA ---
def is_goal(state: State, scenario: dict[str, Any]) -> bool:
	"""La misión termina cuando todas las estaciones requeridas están ONLINE."""
	stations = dict(state.stations)
	return all(stations.get(station_id) == "ONLINE" for station_id in scenario.get("goal", {}).get("stations_online", []))


def _physical_signature(state: State) -> tuple[Any, ...]:
	return (
		state.zone,
		state.payload,
		state.ground_keys,
		state.ground_tools,
		state.ground_materials,
		state.doors,
		state.panels,
		state.stations,
	)


def _dominated(labels: list[tuple[int, int]], cost: int, battery: int) -> bool:
	return any(old_cost <= cost and old_battery >= battery for old_cost, old_battery in labels)


def _record_label(labels: list[tuple[int, int]], cost: int, battery: int) -> None:
	labels[:] = [
		(old_cost, old_battery)
		for old_cost, old_battery in labels
		if not (cost <= old_cost and battery >= old_battery)
	]
	labels.append((cost, battery))


def _node_is_dominated(labels: list[tuple[int, int]], cost: int, battery: int) -> bool:
	return any(
		(old_cost < cost or old_battery > battery)
		and old_cost <= cost
		and old_battery >= battery
		for old_cost, old_battery in labels
	)


def _to_contract(action: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
	kind = action["kind"]
	cost = int(action["cost"])
	if kind == "MOVE":
		return {"op": "MOVE", "to": action["to"], "cost": cost}
	if kind in {"PICKUP", "DROP"}:
		token_kind, name = action["item"]
		return {"op": kind, "item": name, "cost": cost}
	if kind == "OPEN_DOOR":
		return {"op": "INTERACT", "target": action["target"], "action": "OPEN_DOOR", "cost": cost}
	if kind == "REPAIR":
		panel = next(item for item in scenario["panels"] if item["id"] == action["target"])
		return {
			"op": "INTERACT",
			"target": action["target"],
			"action": "REPAIR",
			"consumes": panel["requires"]["material"],
			"cost": cost,
		}
	if kind == "ACTIVATE":
		return {"op": "INTERACT", "target": action["target"], "action": "ACTIVATE", "cost": cost}
	return {"op": "INTERACT", "target": action["target"], "action": "RECHARGE", "cost": cost}


# --- 5. BÚSQUEDA DE COSTO UNIFORME ---
#
# OPEN se ordena por g(n), el costo acumulado. La prueba de meta se hace cuando
# el nodo sale de OPEN, que es la condición usada por UCS para conservar la
# optimalidad con costos positivos. CLOSED evita repetir estados canónicos y
# labels conserva las combinaciones no dominadas de costo y batería.
def solve(scenario: dict[str, Any]) -> dict[str, Any]:
	"""Busca y devuelve el plan válido de menor costo, o FAILURE."""
	initial = initial_state(scenario)
	queue: list[tuple[int, int, Node]] = []
	counter = itertools.count()
	labels: dict[tuple[Any, ...], list[tuple[int, int]]] = {
		_physical_signature(initial): [(0, initial.battery)]
	}
	heapq.heappush(queue, (0, next(counter), Node(initial, 0, ())))
	closed: set[State] = set()

	while queue:
		_, _, node = heapq.heappop(queue)
		if node.state in closed:
			continue
		if _node_is_dominated(
			labels[_physical_signature(node.state)], node.cost, node.state.battery
		):
			continue
		if is_goal(node.state, scenario):
			steps = [_to_contract(action, scenario) for action in node.actions]
			return {"solution_found": True, "total_cost": node.cost, "steps": steps}
		closed.add(node.state)
		for action, next_state, action_cost in successors(node.state, scenario):
			if next_state in closed:
				continue
			new_cost = node.cost + action_cost
			signature = _physical_signature(next_state)
			current_labels = labels.setdefault(signature, [])
			if _dominated(current_labels, new_cost, next_state.battery):
				continue
			_record_label(current_labels, new_cost, next_state.battery)
			next_node = Node(next_state, new_cost, node.actions + (action,))
			heapq.heappush(queue, (new_cost, next(counter), next_node))

	return {"solution_found": False, "total_cost": 0, "steps": [], "message": "FAILURE"}
