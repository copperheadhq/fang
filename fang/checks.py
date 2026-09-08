"""The check classes the commit gate can require.

Spec: "The Commit Gate". Absent a project policy the required set is structural
validation together with every check class whose scope intersects the
transaction's affected entities, so a check class is defined by what it covers
as much as by what it evaluates.
"""

from __future__ import annotations

from .compatibility import compatibility_check, compatibility_scope
from .graph import CONSTRAINT_CHECK, CheckClass
from .topology import topology_check, topology_scope

#: Interface compatibility over every link in the graph.
COMPATIBILITY_CHECK = CheckClass(
    "interface_compatibility", compatibility_check, compatibility_scope
)

#: Topology intent, verified by enumerating conductive paths.
TOPOLOGY_CHECK = CheckClass("topology", topology_check, topology_scope)

#: Every check class this implementation ships. A project narrows or widens the
#: required set through its policy; it never removes the structural check, which
#: the gate runs regardless of this list.
DEFAULT_CHECKS = (CONSTRAINT_CHECK, TOPOLOGY_CHECK, COMPATIBILITY_CHECK)
