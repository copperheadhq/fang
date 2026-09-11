"""The check classes the commit gate can require.

Spec: "The Commit Gate". Absent a project policy the required set is structural
validation together with every check class whose scope intersects the
transaction's affected entities, so a check class is defined by what it covers
as much as by what it evaluates.
"""

from __future__ import annotations

from .compatibility import compatibility_check, compatibility_scope
from .graph import CONSTRAINT_CHECK, CheckClass
from .routing import ROUTING_CHECK as _ROUTING_CHECK
from .topology import topology_check, topology_scope

#: Interface compatibility over every link in the graph.
COMPATIBILITY_CHECK = CheckClass(
    "interface_compatibility", compatibility_check, compatibility_scope
)

#: Topology intent, verified by enumerating conductive paths.
TOPOLOGY_CHECK = CheckClass("topology", topology_check, topology_scope)

#: Routing, placement, and manufacturing intent over the physical layer.
ROUTING_CHECK = _ROUTING_CHECK

#: Every check class this implementation ships. A project narrows or widens the
#: required set through its policy; it never removes structural validation,
#: which the gate runs regardless of this list.
#:
#: `KernelGraph` resolves the same set itself through `graph.default_checks()`,
#: which is where it has to live: the gate cannot import this module without
#: inverting the dependency order.
DEFAULT_CHECKS = (
    CONSTRAINT_CHECK,
    TOPOLOGY_CHECK,
    COMPATIBILITY_CHECK,
    ROUTING_CHECK,
)
