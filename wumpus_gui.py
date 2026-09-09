"""
Interfaz gráfica (Pygame) para el proyecto Wumpus World.

Este módulo NO modifica ni reimplementa la lógica del juego.
Se limita a:
    - Dibujar el grafo (nodos = salas, aristas = pasillos).
    - Pintar el estado de cada sala (oculta, visitada, actual).
    - Mostrar indicadores sensoriales (hedor/brisa) en los vecinos
      de la sala donde está el jugador.
    - Capturar clics del mouse y traducirlos en llamadas a los
      métodos públicos de tu clase `WumpusWorld` (move_player,
      shoot_arrow, grab_gold, climb_out, maybe_move_wumpus).

Requiere: pip install pygame

Importa tu módulo de lógica existente sin tocarlo:
    from wumpus_world import build_classic_cave, WumpusWorld
"""

from __future__ import annotations

import math
import sys

import pygame

# Importa tu lógica ya existente (no se modifica nada de este archivo)
from wumpus_world import build_classic_cave, WumpusWorld


class WumpusGUI:
    """
    Clase responsable EXCLUSIVAMENTE de la ventana, los eventos de
    click/teclado y el renderizado. Recibe una instancia de
    `WumpusWorld` ya construida y opera sobre su API pública.
    """

    NODE_RADIUS = 22

    BG_COLOR = (18, 18, 24)
    EDGE_COLOR = (95, 95, 110)
    HIDDEN_COLOR = (55, 55, 65)      # sala no visitada (niebla de guerra)
    VISITED_COLOR = (95, 140, 200)   # sala ya visitada
    CURRENT_COLOR = (70, 200, 120)   # sala donde está el jugador
    GOLD_COLOR = (235, 200, 40)
    TEXT_COLOR = (230, 230, 230)
    STENCH_COLOR = (190, 90, 205)    # hedor (Wumpus cerca)
    BREEZE_COLOR = (90, 195, 230)    # brisa (pozo cerca)
    LOG_COLOR = (200, 200, 120)

    def __init__(self, world: WumpusWorld, width: int = 1000, height: int = 750) -> None:
        pygame.init()
        pygame.display.set_caption("Wumpus World - GUI")

        self.world = world
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        self.clock = pygame.time.Clock()

        self.font = pygame.font.SysFont("consolas", 18)
        self.small_font = pygame.font.SysFont("consolas", 14)
        self.big_font = pygame.font.SysFont("consolas", 44, bold=True)

        # Estado propio de la GUI (no toca la lógica del juego):
        # qué salas ha visitado el jugador, para pintar la niebla de guerra.
        self.visited: set[int] = {world.player_room}
        self.log_messages: list[str] = []

        self.positions: dict[int, tuple[float, float]] = self._compute_layout()

    # ------------------------------------------------------------------
    # Layout: distribuye los nodos del grafo en un círculo. No asume
    # ninguna topología concreta, así que funciona con cualquier mapa
    # que exponga .nodes() y .neighbors() como tu CaveGraph.
    # ------------------------------------------------------------------
    def _compute_layout(self) -> dict[int, tuple[float, float]]:
        nodes = self.world.graph.nodes()
        n = max(len(nodes), 1)
        cx, cy = self.width * 0.62, self.height * 0.5
        radius = min(self.width, self.height) * 0.36

        positions = {}
        for i, node in enumerate(nodes):
            angle = 2 * math.pi * i / n - math.pi / 2
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            positions[node] = (x, y)
        return positions

    def _log(self, msg: str) -> None:
        self.log_messages.append(msg)
        self.log_messages = self.log_messages[-6:]

    def _node_at_pos(self, pos: tuple[int, int]) -> int | None:
        for node, (x, y) in self.positions.items():
            if (pos[0] - x) ** 2 + (pos[1] - y) ** 2 <= self.NODE_RADIUS ** 2:
                return node
        return None

    # ------------------------------------------------------------------
    # Puente entre eventos de la GUI y la mecánica dinámica del Wumpus.
    # Esto es lo único que "orquesta" turnos; la mecánica en sí vive
    # en world.maybe_move_wumpus(), sin duplicar lógica aquí.
    # ------------------------------------------------------------------
    def _advance_turn_after_action(self) -> None:
        world = self.world
        world.turn += 1
        result = world.maybe_move_wumpus()
        if result is not None:
            old_room, new_room, removed, added = result
            self._log(f"El Wumpus se movió: {old_room} -> {new_room}")
            if added:
                self._log(f"Nuevo hedor en: {sorted(added)}")
            if removed:
                self._log(f"Hedor desaparece en: {sorted(removed)}")

    def _handle_click(self, mouse_pos: tuple[int, int], button: int) -> None:
        world = self.world
        if world.game_over:
            return

        node = self._node_at_pos(mouse_pos)
        if node is None:
            return

        neighbors = world.graph.neighbors(world.player_room)

        if button == 1:  # click izquierdo: moverse (requisito principal)
            if node in neighbors:
                msg = world.move_player(node)
                self.visited.add(node)
                self._log(msg)
                if not world.game_over:
                    self._advance_turn_after_action()
            else:
                self._log("Esa sala no es adyacente: movimiento inválido.")

        elif button == 3:  # click derecho: disparar flecha (extra, opcional)
            if node in neighbors:
                msg = world.shoot_arrow(node)
                self._log(msg)
                if not world.game_over:
                    self._advance_turn_after_action()

    def _handle_key(self, key: int) -> None:
        world = self.world
        if world.game_over:
            return
        if key == pygame.K_g:
            self._log(world.grab_gold())
        elif key == pygame.K_e:
            self._log(world.climb_out())

    # ------------------------------------------------------------------
    # Bucle principal de la GUI
    # ------------------------------------------------------------------
    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    self._handle_click(event.pos, event.button)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    else:
                        self._handle_key(event.key)

            self._draw()
            self.clock.tick(30)

        pygame.quit()

    # ------------------------------------------------------------------
    # Renderizado
    # ------------------------------------------------------------------
    def _draw(self) -> None:
        world = self.world
        screen = self.screen
        screen.fill(self.BG_COLOR)

        self._draw_edges()
        self._draw_nodes()
        self._draw_panel()

        if world.game_over:
            self._draw_game_over()

        pygame.display.flip()

    def _draw_edges(self) -> None:
        world = self.world
        drawn: set[tuple[int, int]] = set()
        for node in world.graph.nodes():
            for neighbor in world.graph.neighbors(node):
                key = (min(node, neighbor), max(node, neighbor))
                if key in drawn:
                    continue
                drawn.add(key)
                pygame.draw.line(
                    self.screen, self.EDGE_COLOR,
                    self.positions[node], self.positions[neighbor], 2,
                )

    def _draw_nodes(self) -> None:
        world = self.world
        neighbors_of_player = world.graph.neighbors(world.player_room)

        for node in world.graph.nodes():
            x, y = self.positions[node]

            if node == world.player_room:
                color = self.CURRENT_COLOR
            elif node in self.visited:
                color = self.VISITED_COLOR
            else:
                color = self.HIDDEN_COLOR

            pygame.draw.circle(self.screen, color, (int(x), int(y)), self.NODE_RADIUS)
            pygame.draw.circle(self.screen, (0, 0, 0), (int(x), int(y)), self.NODE_RADIUS, 2)

            label_color = (10, 10, 10) if color == self.CURRENT_COLOR else self.TEXT_COLOR
            label = self.small_font.render(str(node), True, label_color)
            self.screen.blit(label, label.get_rect(center=(x, y)))

            # Indicadores sensoriales: solo se muestran en los vecinos
            # de la sala donde está el jugador (así respetan la
            # "niebla de guerra" del juego).
            if node in neighbors_of_player:
                if node in world.stench_rooms:
                    pygame.draw.circle(
                        self.screen, self.STENCH_COLOR,
                        (int(x + self.NODE_RADIUS * 0.7), int(y - self.NODE_RADIUS * 0.7)), 7,
                    )
                if node in world.breeze_rooms:
                    pygame.draw.circle(
                        self.screen, self.BREEZE_COLOR,
                        (int(x - self.NODE_RADIUS * 0.7), int(y - self.NODE_RADIUS * 0.7)), 7,
                    )

            # Oro: solo visible cuando el jugador está parado en esa sala
            # y aún no lo ha recogido (percepción de "brillo").
            if node == world.gold_room and world.player_room == world.gold_room and not world.has_gold:
                pygame.draw.circle(
                    self.screen, self.GOLD_COLOR,
                    (int(x), int(y + self.NODE_RADIUS * 0.95)), 6,
                )

    def _draw_panel(self) -> None:
        world = self.world
        x = 20
        y = 20

        percep = world.perceptions_at(world.player_room)
        percep_txt = ", ".join(k for k, v in percep.items() if v) or "nada"

        lines = [
            f"Turno: {world.turn}",
            f"Sala actual: {world.player_room}",
            f"Flechas: {world.arrows}",
            f"Oro en mano: {'sí' if world.has_gold else 'no'}",
            f"Wumpus vivo: {'sí' if world.wumpus_alive else 'no'}",
            "",
            "Click izq: mover   Click der: disparar",
            "Tecla G: agarrar oro   Tecla E: salir",
            "",
            f"Percepciones aquí: {percep_txt}",
            "",
            "Registro:",
        ]
        for line in lines:
            surf = self.font.render(line, True, self.TEXT_COLOR)
            self.screen.blit(surf, (x, y))
            y += 24

        for msg in self.log_messages:
            surf = self.small_font.render(msg, True, self.LOG_COLOR)
            self.screen.blit(surf, (x, y))
            y += 18

    def _draw_game_over(self) -> None:
        world = self.world
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 185))
        self.screen.blit(overlay, (0, 0))

        text = "¡VICTORIA!" if world.won else "DERROTA"
        color = (80, 220, 120) if world.won else (220, 80, 80)
        surf = self.big_font.render(text, True, color)
        self.screen.blit(surf, surf.get_rect(center=(self.width // 2, self.height // 2)))

        sub = self.font.render("Presiona ESC para salir", True, self.TEXT_COLOR)
        self.screen.blit(sub, sub.get_rect(center=(self.width // 2, self.height // 2 + 50)))


# --------------------------------------------------------------------------
# Punto de entrada de la variante gráfica.
# --------------------------------------------------------------------------
def main() -> None:
    graph = build_classic_cave()
    world = WumpusWorld(graph)

    gui = WumpusGUI(world)   # <-- aquí se instancia la clase visual
    gui.run()


if __name__ == "__main__":
    main()
