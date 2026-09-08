"""Reading the s-expression form CAD tools write.

Spec: "External Adapters Report Loss". The reader is strict: a malformed file is
reported rather than guessed at, because a guess here becomes a silent semantic
change downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Sequence


class SExprError(ValueError):
    """A file that is not well-formed s-expressions."""


@dataclass(frozen=True)
class Atom:
    """A leaf. `quoted` is preserved so a re-emit can round-trip the form."""

    value: str
    quoted: bool = False

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Node:
    """A list: a head symbol and the items after it."""

    items: tuple["Node | Atom", ...]

    @property
    def head(self) -> str:
        if not self.items:
            return ""
        first = self.items[0]
        return first.value if isinstance(first, Atom) else ""

    @property
    def rest(self) -> tuple["Node | Atom", ...]:
        return self.items[1:]

    def children(self, head: str) -> list["Node"]:
        """Every direct child list with this head."""
        return [item for item in self.items if isinstance(item, Node) and item.head == head]

    def child(self, head: str) -> "Node | None":
        found = self.children(head)
        return found[0] if found else None

    def atoms(self) -> list[str]:
        return [item.value for item in self.rest if isinstance(item, Atom)]

    def value(self, head: str, index: int = 0) -> str | None:
        """The nth atom of the first child with this head."""
        child = self.child(head)
        if child is None:
            return None
        atoms = child.atoms()
        return atoms[index] if index < len(atoms) else None

    def pairs(self) -> dict[str, str]:
        """A child's atoms read as key/value pairs, as KiCad writes them."""
        atoms = self.atoms()
        return {atoms[i]: atoms[i + 1] for i in range(0, len(atoms) - 1, 2)}

    def __iter__(self) -> Iterator["Node | Atom"]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char in "()":
            tokens.append(char)
            index += 1
        elif char.isspace():
            index += 1
        elif char == ";":                     # a comment runs to end of line
            newline = text.find("\n", index)
            index = length if newline == -1 else newline + 1
        elif char == '"':
            start, index = index, index + 1
            buffer = ['"']
            while index < length:
                if text[index] == "\\" and index + 1 < length:
                    buffer.append(text[index : index + 2])
                    index += 2
                    continue
                if text[index] == '"':
                    buffer.append('"')
                    index += 1
                    break
                buffer.append(text[index])
                index += 1
            else:
                raise SExprError(f"unterminated string starting at offset {start}")
            tokens.append("".join(buffer))
        else:
            start = index
            while index < length and not text[index].isspace() and text[index] not in "()":
                index += 1
            tokens.append(text[start:index])
    return tokens


def _unquote(token: str) -> tuple[str, bool]:
    if len(token) >= 2 and token.startswith('"') and token.endswith('"'):
        body = token[1:-1]
        return body.replace('\\"', '"').replace("\\\\", "\\"), True
    return token, False


def parse(text: str) -> Node:
    """Parse one top-level s-expression."""
    tokens = tokenize(text)
    if not tokens:
        raise SExprError("the file is empty")

    position = 0

    def read() -> Node | Atom:
        nonlocal position
        if position >= len(tokens):
            raise SExprError("the file ends inside a list")
        token = tokens[position]
        position += 1
        if token == "(":
            items: list[Node | Atom] = []
            while position < len(tokens) and tokens[position] != ")":
                items.append(read())
            if position >= len(tokens):
                raise SExprError("the file ends inside a list")
            position += 1                     # consume ")"
            return Node(tuple(items))
        if token == ")":
            raise SExprError("a closing parenthesis with no list to close")
        value, quoted = _unquote(token)
        return Atom(value, quoted)

    result = read()
    if position != len(tokens):
        raise SExprError("the file carries more than one top-level expression")
    if not isinstance(result, Node):
        raise SExprError("the file's top level is an atom, not a list")
    return result
