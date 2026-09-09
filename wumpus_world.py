"""
Wumpus World - Variante con grafo no dirigido y Wumpus dinámico.

Modelo del mapa:
    - Las salas son vértices (enteros 1..20).
    - Los pasillos son aristas bidireccionales, implementadas con
      listas de adyacencia (dict[int, set[int]]).
    - La topología usada es la cueva dodecaédrica clásica del
      juego original "Hunt the Wumpus": cada sala tiene exactamente
      3 vecinos.

Mecánica dinámica del Wumpus:
    - En cada turno, con una probabilidad WUMPUS_WAKE_PROB (o de
      forma forzada cada WUMPUS_MOVE_INTERVAL turnos), el Wumpus
      "despierta" y se desplaza a una sala adyacente válida.
    - Tras cada reubicación se recalcula el conjunto de salas con
      "hedor" (stench): se eliminan los hedores de los vecinos de
      la posición anterior y se agregan los hedores de los vecinos
      de la nueva posición.

"""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


# 1. GRAFO NO DIRIGIDO (listas de adyacencia)
class CaveGraph:
    """Grafo no dirigido representado mediante listas de adyacencia."""

    def __init__(self) -> None:
        self._adj: dict[int, set[int]] = defaultdict(set)

    def add_edge(self, u: int, v: int) -> None:
        """Agrega una arista bidireccional u <-> v."""
        self._adj[u].add(v)
        self._adj[v].add(u)

    def neighbors(self, node: int) -> set[int]:
        """Devuelve el conjunto de vecinos (copia) de 'node'."""
        return set(self._adj.get(node, set()))

    def nodes(self) -> list[int]:
        return sorted(self._adj.keys())

    def has_edge(self, u: int, v: int) -> bool:
        return v in self._adj.get(u, set())

    def __repr__(self) -> str:
        lines = [f"{n}: {sorted(self._adj[n])}" for n in self.nodes()]
        return "\n".join(lines)


def build_classic_cave() -> CaveGraph:
    """
    Construye la cueva dodecaédrica clásica de 20 salas, donde cada
    sala tiene exactamente 3 vecinos. Es la topología original de
    "Hunt the Wumpus".
    """
    edges = {
        1: (2, 5, 8),
        2: (1, 3, 10),
        3: (2, 4, 12),
        4: (3, 5, 14),
        5: (1, 4, 6),
        6: (5, 7, 15),
        7: (6, 8, 17),
        8: (1, 7, 9),
        9: (8, 10, 18),
        10: (2, 9, 11),
        11: (10, 12, 19),
        12: (3, 11, 13),
        13: (12, 14, 20),
        14: (4, 13, 15),
        15: (6, 14, 16),
        16: (15, 17, 20),
        17: (7, 16, 18),
        18: (9, 17, 19),
        19: (11, 18, 20),
        20: (13, 16, 19),
    }
    graph = CaveGraph()
    for u, vs in edges.items():
        for v in vs:
            graph.add_edge(u, v)
    return graph


# 2. ESTADO DEL MUNDO Y MECÁNICA DEL WUMPUS DINÁMICO

@dataclass
class WorldConfig:
    num_rooms: int = 20
    num_pits: int = 3
    wumpus_wake_prob: float = 0.35   # probabilidad de despertar cada turno
    wumpus_move_interval: int = 4    # además, se fuerza el movimiento cada N turnos
    num_arrows: int = 3
    entrance_room: int = 1


@dataclass
class WumpusWorld:
    graph: CaveGraph
    config: WorldConfig = field(default_factory=WorldConfig)

    def __post_init__(self) -> None:
        rooms = self.graph.nodes()
        available = [r for r in rooms if r != self.config.entrance_room]
        random.shuffle(available)

        self.wumpus_room: int = available.pop()
        self.pit_rooms: set[int] = set(available[: self.config.num_pits])
        available = available[self.config.num_pits :]
        self.gold_room: int = available.pop()

        self.player_room: int = self.config.entrance_room
        self.has_gold: bool = False
        self.arrows: int = self.config.num_arrows
        self.turn: int = 0
        self.wumpus_alive: bool = True
        self.game_over: bool = False
        self.won: bool = False

        # Percepciones dinámicas
        self.stench_rooms: set[int] = set()
        self.breeze_rooms: set[int] = set()
        self._recompute_breeze()   # las brisas de los pozos son estáticas
        self._recompute_stench()   # el hedor inicial del Wumpus

    # ---------------------- Percepciones ----------------------
    def _recompute_breeze(self) -> None:
        self.breeze_rooms.clear()
        for pit in self.pit_rooms:
            self.breeze_rooms.update(self.graph.neighbors(pit))

    def _recompute_stench(self) -> set[int]:
        """Recalcula el hedor a partir de la posición actual del Wumpus."""
        self.stench_rooms = self.graph.neighbors(self.wumpus_room)
        return self.stench_rooms

    def _relocate_wumpus(self) -> Optional[tuple[int, int, set[int], set[int]]]:
        """
        Mueve al Wumpus a una sala vecina válida y recalcula el hedor
        de forma incremental (quita el hedor viejo, agrega el nuevo).
        Devuelve (sala_vieja, sala_nueva, hedor_removido, hedor_agregado)
        o None si el Wumpus está muerto y no puede moverse.
        """
        if not self.wumpus_alive:
            return None

        old_room = self.wumpus_room
        candidates = list(self.graph.neighbors(old_room))
        if not candidates:
            return None

        new_room = random.choice(candidates)

        old_stench = self.stench_rooms
        self.wumpus_room = new_room
        new_stench = self._recompute_stench()

        removed = old_stench - new_stench
        added = new_stench - old_stench
        return old_room, new_room, removed, added

    def maybe_move_wumpus(self) -> Optional[tuple[int, int, set[int], set[int]]]:
        """
        Se llama una vez por turno. El Wumpus despierta y se mueve si:
          - ocurre el evento aleatorio (probabilidad wumpus_wake_prob), o
          - han pasado wumpus_move_interval turnos desde el último chequeo.
        """
        forced = (self.turn > 0 and self.turn % self.config.wumpus_move_interval == 0)
        woke_up = random.random() < self.config.wumpus_wake_prob

        if forced or woke_up:
            return self._relocate_wumpus()
        return None

    # ---------------------- Percepciones del jugador ----------------------
    def perceptions_at(self, room: int) -> dict[str, bool]:
        return {
            "hedor": room in self.stench_rooms,
            "brisa": room in self.breeze_rooms,
            "brillo": room == self.gold_room and not self.has_gold,
        }

    # ---------------------- Acciones del jugador ----------------------
    def move_player(self, target: int) -> str:
        if target not in self.graph.neighbors(self.player_room):
            return f"No hay pasillo directo de {self.player_room} a {target}."

        self.player_room = target

        if self.wumpus_alive and self.player_room == self.wumpus_room:
            self.game_over = True
            self.won = False
            return "¡El Wumpus te ha devorado! Fin del juego."

        if self.player_room in self.pit_rooms:
            self.game_over = True
            self.won = False
            return "Caíste en un pozo sin fondo. Fin del juego."

        return f"Te moviste a la sala {self.player_room}."

    def grab_gold(self) -> str:
        if self.player_room == self.gold_room and not self.has_gold:
            self.has_gold = True
            return "¡Recogiste el oro!"
        return "No hay oro aquí."

    def climb_out(self) -> str:
        if self.player_room == self.config.entrance_room:
            self.game_over = True
            if self.has_gold:
                self.won = True
                return "Saliste de la cueva con el oro. ¡Ganaste!"
            self.won = False
            return "Saliste de la cueva sin el oro."
        return "Debes estar en la entrada para salir."

    def shoot_arrow(self, target_room: int) -> str:
        if self.arrows <= 0:
            return "No te quedan flechas."
        self.arrows -= 1

        if target_room not in self.graph.neighbors(self.player_room):
            return "La flecha se pierde en un pasillo sin salida directa."

        if self.wumpus_alive and target_room == self.wumpus_room:
            self.wumpus_alive = False
            self.stench_rooms.clear()
            return "¡Escuchas un grito espantoso! Mataste al Wumpus."

        return "La flecha no dio en el blanco."

    def status(self) -> str:
        p = self.perceptions_at(self.player_room)
        percep = ", ".join(k for k, v in p.items() if v) or "nada especial"
        return (
            f"[Turno {self.turn}] Sala actual: {self.player_room} | "
            f"Percibes: {percep} | Flechas: {self.arrows} | "
            f"Oro en mano: {'sí' if self.has_gold else 'no'}"
        )


# 3. BUCLE DE JUEGO (consola)
def print_help() -> None:
    print(
        "\nComandos disponibles:\n"
        "  mover <sala>   - moverte a una sala adyacente\n"
        "  disparar <sala>- disparar una flecha hacia una sala adyacente\n"
        "  agarrar        - recoger el oro si está en tu sala\n"
        "  salir          - salir de la cueva (solo desde la entrada)\n"
        "  vecinos        - mostrar las salas vecinas a tu posición\n"
        "  ayuda          - mostrar esta ayuda\n"
        "  terminar       - abandonar la partida\n"
    )


def main() -> None:
    graph = build_classic_cave()
    world = WumpusWorld(graph)

    print("=== WUMPUS WORLD (grafo no dirigido, Wumpus dinámico) ===")
    print_help()
    print(world.status())

    while not world.game_over:
        world.turn += 1
        cmd = input("\n> ").strip().lower().split()

        if not cmd:
            continue

        action = cmd[0]

        if action == "ayuda":
            print_help()
            continue

        if action == "terminar":
            print("Partida abandonada.")
            break

        if action == "vecinos":
            print(f"Vecinos de {world.player_room}: {sorted(graph.neighbors(world.player_room))}")
            continue

        if action == "mover" and len(cmd) == 2 and cmd[1].isdigit():
            print(world.move_player(int(cmd[1])))

        elif action == "disparar" and len(cmd) == 2 and cmd[1].isdigit():
            print(world.shoot_arrow(int(cmd[1])))

        elif action == "agarrar":
            print(world.grab_gold())

        elif action == "salir":
            print(world.climb_out())

        else:
            print("Comando no reconocido. Escribe 'ayuda' para ver las opciones.")
            continue

        if world.game_over:
            break

        # Mecánica dinámica: el Wumpus puede despertar y moverse cada turno.
        result = world.maybe_move_wumpus()
        if result is not None:
            old_room, new_room, removed, added = result
            print(f"(El Wumpus se movió de la sala {old_room} a la sala {new_room}.)")
            if removed:
                print(f"  Hedor eliminado en: {sorted(removed)}")
            if added:
                print(f"  Hedor agregado en: {sorted(added)}")

        print(world.status())

    if world.game_over:
        print("\n=== FIN DE LA PARTIDA ===")
        print("Resultado:", "VICTORIA" if world.won else "DERROTA")


if __name__ == "__main__":
    main()
