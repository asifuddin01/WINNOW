"""The regular-expression subset allowed in keywords (guide 12.3).

Keywords are highlighted in the browser and may be matched on the server, so a pattern must
mean the same in JavaScript (with the `u` flag) and Python, and must not be able to take
exponential time. The subset: literals, `.`, character classes, the escapes `\\d \\w \\s \\b`
and their capitals, escaped syntax characters, non-capturing and capturing groups,
alternation, anchors, and quantifiers up to 100. Not allowed: backreferences, lookaround,
named groups, inline flags, other escapes, and repeating a group that contains a repeat or
alternatives, the shape behind catastrophic backtracking, e.g. `(a+)+` or `(a|ab)*`.
"""

import re
from dataclasses import dataclass

MAX_REPEAT = 100
SYNTAX_CHARACTERS = frozenset("^$\\.*+?()[]{}|/")
CLASS_ESCAPES = frozenset("dDwWsS")
BOUNDARY_ESCAPES = frozenset("bB")
_BRACE_QUANTIFIER = re.compile(r"\{(\d{1,3})(?:(,)(\d{1,3})?)?\}")


class PatternError(ValueError):
    """Why a pattern is not allowed, in words for the person who typed it."""


@dataclass(slots=True)
class _Group:
    quantified: bool = False
    alternates: bool = False


@dataclass(slots=True)
class _Atom:
    group: _Group | None = None  # set when the atom is a whole group


def check_pattern(pattern: str) -> None:
    """Raise PatternError unless `pattern` is in the allowed subset."""
    stack = [_Group()]
    atom: _Atom | None = None  # what a quantifier here would repeat
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if char == "\\":
            atom, i = _escape(pattern, i)
            continue
        if char == "[":
            i = _character_class(pattern, i)
            atom = _Atom()
            continue
        if char == "(":
            if pattern.startswith("(?", i) and not pattern.startswith("(?:", i):
                raise PatternError(
                    "Lookarounds, named groups and inline flags are not supported; "
                    "use (…) or (?:…)."
                )
            stack.append(_Group())
            i += 3 if pattern.startswith("(?:", i) else 1
            atom = None
            continue
        if char == ")":
            if len(stack) == 1:
                raise PatternError("A “)” has no matching “(”.")
            group = stack.pop()
            if group.quantified:
                stack[-1].quantified = True
            atom = _Atom(group=group)
            i += 1
            continue
        if char == "|":
            stack[-1].alternates = True
            atom = None
            i += 1
            continue
        if char in "*+?{":
            i = _quantifier(pattern, i, atom, stack[-1])
            atom = None
            continue
        if char in "^$":
            atom = None
            i += 1
            continue
        if char in "]}":
            raise PatternError(f"Escape “{char}” as “\\{char}” to match it literally.")
        atom = _Atom()
        i += 1
    if len(stack) != 1:
        raise PatternError("A “(” is never closed.")
    try:
        compiled = re.compile(pattern)
    except re.error as error:  # pragma: no cover - the checks above should catch these
        raise PatternError(f"This is not a valid pattern: {error.msg}.") from None
    if compiled.search("") is not None:
        raise PatternError("This pattern matches empty text; it must match at least a letter.")


def _escape(pattern: str, i: int) -> tuple[_Atom | None, int]:
    if i + 1 >= len(pattern):
        raise PatternError("A pattern cannot end with “\\”.")
    escaped = pattern[i + 1]
    if escaped in BOUNDARY_ESCAPES:
        return None, i + 2
    if escaped in CLASS_ESCAPES or escaped in SYNTAX_CHARACTERS:
        return _Atom(), i + 2
    raise PatternError(
        f"“\\{escaped}” is not supported. Use \\d, \\w, \\s, \\b or escape punctuation."
    )


def _character_class(pattern: str, i: int) -> int:
    """Index just past the class that starts at `i`."""
    j = i + 1
    if j < len(pattern) and pattern[j] == "^":
        j += 1
    start = j
    while j < len(pattern):
        char = pattern[j]
        if char == "\\":
            escaped = pattern[j + 1] if j + 1 < len(pattern) else ""
            if not (escaped in CLASS_ESCAPES or escaped in SYNTAX_CHARACTERS or escaped == "-"):
                raise PatternError(f"“\\{escaped}” is not supported inside […].")
            j += 2
            continue
        if char == "[":
            raise PatternError("Escape “[” inside a character class as “\\[”.")
        if char == "]":
            if j == start:
                raise PatternError("A character class cannot be empty.")
            return j + 1
        if pattern.startswith(("&&", "--", "~~"), j):
            raise PatternError("Doubled “&”, “-” or “~” inside […] is not supported.")
        j += 1
    raise PatternError("A “[” is never closed.")


def _quantifier(pattern: str, i: int, atom: _Atom | None, group: _Group) -> int:
    """Validate the quantifier at `i` against what it repeats; index just past it."""
    char = pattern[i]
    if char == "{":
        match = _BRACE_QUANTIFIER.match(pattern, i)
        if match is None:
            raise PatternError("Write repeats as {n}, {n,} or {n,m}, or escape “{” as “\\{”.")
        low = int(match[1])
        high = None if match[2] and match[3] is None else int(match[3] or match[1])
        if low > MAX_REPEAT or (high is not None and (high > MAX_REPEAT or high < low)):
            raise PatternError(f"Repeat counts must be between 0 and {MAX_REPEAT}, in order.")
        repeats = high is None or high > 1
        end = match.end()
    else:
        repeats = char != "?"
        end = i + 1
    if atom is None:
        raise PatternError(f"“{char}” must follow something to repeat.")
    if repeats and atom.group is not None and (atom.group.quantified or atom.group.alternates):
        raise PatternError(
            "A repeated group cannot contain a repeat or alternatives, "
            "e.g. (a+)+ or (a|b)*; such patterns can take very long to match."
        )
    group.quantified = True  # even "?": (a?)+ backtracks like (a+)+
    if end < len(pattern) and pattern[end] == "?":  # lazy
        end += 1
    if end < len(pattern) and pattern[end] in "*+{":
        raise PatternError("Two repeats in a row are not supported.")
    return end
