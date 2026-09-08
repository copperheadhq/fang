"""Fang: the Copperhead hardware kernel and its authoring language.

The kernel holds exactly one canonical model, the Engineering Intermediate
Representation (EIR). Everything else this package produces is a lowering of
it, a projection of it, or an interchange encoding of it.
"""

__version__ = "0.1.0"

#: The data schema version this implementation produces and accepts.
SCHEMA_VERSION = "1.1"
