"""데이터셋 연결 그래프 — 간접 경로 포함."""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from quality_xy.key_discovery import KeyLink


@dataclass
class LinkStep:
    from_dataset: str
    from_column: str
    to_dataset: str
    to_column: str
    link: KeyLink


@dataclass
class DatasetGraph:
    links: list[KeyLink] = field(default_factory=list)
    _graph: nx.Graph = field(default_factory=nx.Graph, repr=False)

    def __post_init__(self) -> None:
        self.rebuild()

    def rebuild(self) -> None:
        self._graph = nx.Graph()
        for link in self.links:
            self._graph.add_edge(
                link.dataset_a,
                link.dataset_b,
                link=link,
                weight=link.intersection_count,
            )

    def connected_components(self) -> list[set[str]]:
        return [set(c) for c in nx.connected_components(self._graph)]

    def path_from_anchor(self, anchor: str, target: str) -> list[LinkStep] | None:
        if anchor == target:
            return []
        if anchor not in self._graph or target not in self._graph:
            return None
        try:
            node_path = nx.shortest_path(self._graph, anchor, target, weight="weight")
        except nx.NetworkXNoPath:
            return None

        steps: list[LinkStep] = []
        for i in range(len(node_path) - 1):
            a, b = node_path[i], node_path[i + 1]
            edge_data = self._graph.get_edge_data(a, b) or {}
            link: KeyLink = edge_data["link"]
            if link.dataset_a == a:
                steps.append(LinkStep(a, link.column_a, b, link.column_b, link))
            else:
                steps.append(LinkStep(a, link.column_b, b, link.column_a, link))
        return steps

    def reachable_datasets(self, anchor: str) -> list[str]:
        if anchor not in self._graph:
            return [anchor]
        component = nx.node_connected_component(self._graph, anchor)
        return sorted(component)

    def adjacency_mermaid(self, anchor: str | None = None) -> str:
        lines = ["graph LR"]
        seen: set[tuple[str, str]] = set()
        for link in self.links:
            pair = tuple(sorted((link.dataset_a, link.dataset_b)))
            if pair in seen:
                continue
            seen.add(pair)
            label = f"{link.column_a}|{link.column_b}"
            a_style = ""
            b_style = ""
            if anchor and link.dataset_a == anchor:
                a_style = ":::anchor"
            if anchor and link.dataset_b == anchor:
                b_style = ":::anchor"
            lines.append(f'  {link.dataset_a}{a_style} -- "{label}" --> {link.dataset_b}{b_style}')
        lines.append("  classDef anchor fill:#ffe082,stroke:#f57c00")
        return "\n".join(lines)
