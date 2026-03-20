---
name: python-philosophy
description: >
  Python design philosophy based on Rich Hickey's "Simple Made Easy" principles —
  separating simple from easy, avoiding complecting, data over objects, pure
  functions, composition over inheritance (Protocol over ABC), and immutability.
  Invoke when designing or architecting a Python module, service, or system;
  when generating non-trivial Python code where structure and testability matter;
  when the user asks how to separate concerns, structure code, or choose between
  patterns (classes vs functions, ABC vs Protocol, inheritance vs composition);
  when the user wants to untangle a large or messy file; when designing pluggable
  or extensible systems; or when the user mentions wanting cleaner, simpler, or
  more testable code. Do not invoke for bug fixes, debugging, basic Python
  questions, tooling setup, or mechanical tasks like adding type hints, writing
  a regex, or parsing JSON.
allowed-tools: Read
---

# Python Philosophy — Simple Made Easy

This skill guides Python code generation and design using Rich Hickey's "Simple Made Easy" principles, adapted for idiomatic Python. Apply these principles silently when writing code. When a choice is non-obvious or runs against what the user might expect, include a brief inline comment or a short rationale note.

**If you're unfamiliar with the philosophy**, read `references/principles.md` for the full grounding. The short version: *simple* means having one role (not tangled with other things). *Easy* means familiar. We optimize for simple, not easy. Complexity comes from braiding concerns together — Hickey calls this "complecting".

## Quick Reference

| Instead of | Prefer |
|---|---|
| Mutable class with behavior | `@dataclass(frozen=True)` + free functions |
| Inheritance for behavior | `typing.Protocol` + composition |
| Method that does two things | Two pure functions |
| Mutable default, mutate in place | Return a new value (`dataclasses.replace`) |
| `isinstance` chains | `functools.singledispatch` |
| Mixed I/O and logic | Pure core, I/O at the edges |
| Boolean flag parameter | Two separate functions |
| Global mutable state | Passed arguments, explicit dependencies |

## When to Surface Rationale

Apply principles silently. Add a brief comment or note when:

- Choosing a `Protocol` over a base class (user may expect inheritance)
- Splitting a function the user asked for as one thing
- Using `frozen=True` when the user might expect a mutable object
- Avoiding a pattern that's common in frameworks the user is likely familiar with

Keep rationale short — one sentence is enough. Example:
```python
# Using Protocol rather than ABC — no inheritance coupling needed
class Serializable(Protocol):
    def to_dict(self) -> dict: ...
```

## For Other Skills

This file is the entry point. For full principle detail, examples, anti-patterns, and the pragmatic exceptions table, read:

> `references/principles.md`

Code review skills: check each construct against the anti-patterns section.
Refactoring skills: use the "Instead of / Prefer" patterns as your rewrite targets.
Education skills: use the Simple vs Easy framing to explain *why*, not just *what*.