"""Protocol propagation over the IR chain (spec §17).

When a patch changes the experimental protocol, the downstream components must be
re-inspected. This module provides a directed propagation graph over the ordered
IR chain::

    data → train → val → test → metrics → plots → artifacts → conclusions → qa

A leakage/split fix at the head of the chain therefore re-flags ``metrics``,
``plots``, ``artifacts``, ``conclusions`` and ``qa`` as downstream. Propagation
only *marks* downstream sections for re-audit — it never fabricates code or
mutates notebook cells.
"""

from __future__ import annotations

from dataclasses import dataclass

from nb_audit.repair.root_cause import IR_CHAIN, downstream_sections, section_for


@dataclass(frozen=True)
class PropagationResult:
    """The downstream sections to re-flag after a patch for ``finding_id``."""

    finding_id: str
    category: str
    source_section: str
    downstream: tuple[str, ...]

    @property
    def reflags(self) -> tuple[str, ...]:
        """Alias for ``downstream``: the sections that must be re-audited."""
        return self.downstream


class PropagationGraph:
    """Directed propagation over the IR chain (§17)."""

    def __init__(self, chain: tuple[str, ...] = IR_CHAIN) -> None:
        self.chain = tuple(chain)

    def section(self, category: str) -> str:
        """Map a finding category to its IR-chain section."""
        return section_for(category)

    def downstream(self, section: str) -> tuple[str, ...]:
        """Return every chain section strictly after ``section``."""
        try:
            index = self.chain.index(section)
        except ValueError:
            index = 0
        return self.chain[index + 1:]

    def affected(self, category: str) -> tuple[str, ...]:
        """Return the downstream sections affected by a fix in ``category``."""
        return self.downstream(self.section(category))

    def reflag(self, finding_id: str, category: str) -> PropagationResult:
        """Compute the propagation result for a patch addressed to ``finding_id``."""
        source = self.section(category)
        return PropagationResult(
            finding_id=finding_id,
            category=category,
            source_section=source,
            downstream=self.downstream(source),
        )


# Convenience alias — re-exported so callers can use the section helper directly.
__all__ = ["PropagationGraph", "PropagationResult", "downstream_sections", "section_for"]
