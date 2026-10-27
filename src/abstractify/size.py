from __future__ import annotations

from abstractify.config import Config


class GraphTooLarge(Exception):
    """Graph exceeds configured size protection."""

    def __init__(
        self,
        *,
        graph_id: str,
        entity_count: int,
        edge_count: int,
        limits: dict,
        hard: bool = False,
    ) -> None:
        self.graph_id = graph_id
        self.entity_count = entity_count
        self.edge_count = edge_count
        self.limits = limits
        self.hard = hard
        action = "refused (hard cap)" if hard else "refused (pass confirm_large=true after asking the user)"
        super().__init__(
            f"Graph {graph_id!r} is too large ({entity_count} entities, {edge_count} edges); {action}."
        )

    def as_dict(self) -> dict:
        return {
            "ok": False,
            "error": "graph_too_large",
            "graph_id": self.graph_id,
            "entity_count": self.entity_count,
            "edge_count": self.edge_count,
            "limits": self.limits,
            "hard": self.hard,
            "message": str(self),
        }


def check_graph_size(
    *,
    graph_id: str,
    entity_count: int,
    edge_count: int,
    cfg: Config,
    confirm_large: bool,
) -> None:
    limits = {
        "max_entities_per_graph": cfg.max_entities_per_graph,
        "max_edges_per_graph": cfg.max_edges_per_graph,
        "hard_max_entities": cfg.hard_max_entities,
    }
    if entity_count > cfg.hard_max_entities:
        raise GraphTooLarge(
            graph_id=graph_id,
            entity_count=entity_count,
            edge_count=edge_count,
            limits=limits,
            hard=True,
        )
    over = entity_count > cfg.max_entities_per_graph or edge_count > cfg.max_edges_per_graph
    if over and not confirm_large:
        raise GraphTooLarge(
            graph_id=graph_id,
            entity_count=entity_count,
            edge_count=edge_count,
            limits=limits,
            hard=False,
        )
