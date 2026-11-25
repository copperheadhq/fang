# RFC 11 example records

Copied unchanged from `schemas/rfc11/examples/` in
[copperheadhq/copperhead-rfcs](https://github.com/copperheadhq/copperhead-rfcs),
as adopted with RFC 11 version 1.4 and RFC 3 version 1.6 (pull request #15,
merged as `8c91020`). They have not changed since commit `c7f6643`.

The records cite one another by content hash, and the RFC repository's checker
computed every cited hash. `tests/test_canonical_form.py` recomputes them with
the kernel's encoder: the kernel conforms to RFC 3 Section 17.1 only if every
one matches.

When the RFC revises its examples, copy the directory again and update the
commit above. Do not edit these files by hand.
