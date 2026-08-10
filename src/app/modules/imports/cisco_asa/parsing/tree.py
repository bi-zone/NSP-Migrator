"""Indentation-based config tree for Cisco ASA raw text.

First structural step in CiscoAsaParserAdapter.parse: raw text becomes a
flat nodes list with parent/child links derived from leading whitespace.

AsaIndex and extractors use ConfigNode.idx to locate object headers and
ConfigTree.children to read indented object bodies (address/service groups).
ACL and zone extractors mostly iterate tree.nodes linearly.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.imports.cisco_asa.parsing.lines import ConfigLine


@dataclass(slots=True)
class ConfigNode:
    """One non-empty, non-comment config line in tree order.

    Attributes:
        idx: Stable index into ConfigTree.nodes — stored in AsaIndex maps.
        line: Original line number, text, and computed indent.
        parent_idx: Parent node index, or None for top-level lines.
        children: Direct child node indices (indented body lines).
    """

    idx: int
    line: ConfigLine
    parent_idx: int | None
    children: list[int]


@dataclass(slots=True)
class ConfigTree:
    """Parent/child graph over parsed ASA configuration lines.

    Built once per parse; passed to AsaIndex.from_tree and all extractors.
    """

    nodes: list[ConfigNode]

    def children(self, node_idx: int) -> list[ConfigNode]:
        """Return direct child nodes for a header node index.

        Used by AddressExtractor, ServiceExtractor, and
        ProtocolGroupExtractor to collect indented stanza bodies.
        """
        return [self.nodes[i] for i in self.nodes[node_idx].children]


class ConfigTreeBuilder:
    """Build ConfigTree from raw ASA configuration text."""

    @staticmethod
    def _indent_of(line: str) -> int:
        """Measure leading whitespace (tab counts as 4 spaces)."""
        indent = 0
        for ch in line:
            if ch == " ":
                indent += 1
            elif ch == "\t":
                indent += 4
            else:
                break
        return indent

    def build(self, raw_text: str) -> ConfigTree:
        """Parse raw text into an indentation tree.

        Skips blank lines and ASA comments (lines starting with !). Uses a
        stack of (indent, idx) pairs to assign parent_idx — when a line
        is less-indented than the stack top, parents are popped until the correct
        nesting level is found.

        Called from CiscoAsaParserAdapter.parse before AsaIndex and
        extractors run.

        Returns:
            ConfigTree with nodes in source-file order.
        """
        nodes: list[ConfigNode] = []
        stack: list[tuple[int, int]] = []

        for line_no, text in enumerate(raw_text.splitlines(), start=1):
            stripped = text.strip()
            if not stripped or stripped.startswith("!"):
                continue

            indent = self._indent_of(text)
            cfg_line = ConfigLine(line_no=line_no, text=text, indent=indent)

            while stack and indent <= stack[-1][0]:
                stack.pop()

            parent_idx = stack[-1][1] if stack else None
            idx = len(nodes)
            node = ConfigNode(
                idx=idx, line=cfg_line, parent_idx=parent_idx, children=[]
            )
            nodes.append(node)
            if parent_idx is not None:
                nodes[parent_idx].children.append(idx)

            stack.append((indent, idx))

        return ConfigTree(nodes=nodes)