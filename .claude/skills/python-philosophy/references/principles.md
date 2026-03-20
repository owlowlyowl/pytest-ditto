# Simple Made Easy — Python Principles Reference

Full reference for the `python-philosophy` skill. Read this when generating code, reviewing, refactoring, or teaching. Other skills should reference this file directly.

---

## The Core Distinction

**Simple** means having one role, one concept, one purpose — not interleaved with other concerns. It is an objective property of the artifact itself.

**Easy** means familiar, close at hand, low friction to write. It is a subjective property of the developer.

These are orthogonal. A pattern can be easy (you've done it a hundred times) and complex (it braids three concerns together). Our goal is to optimize for simple, not for easy. Easy things feel fast to write but embed complexity that compounds — the system becomes harder to understand, test, and change. Simple things feel like more work upfront but remain tractable as they grow.

**Complecting** — from "to complect", to braid together — is what we're guarding against. When two concerns are woven into one artifact, you cannot reason about, test, or change either one independently. Recognizing complecting is the core skill.

---

## Principles

### 1. One Thing at a Time

Every function, module, and data structure should do one thing. When you find yourself writing a function that "fetches and formats", or a class that "validates, persists, and notifies", that's complecting. Split it.

The test: can you describe what this does without using "and"?

```python
# Complected: fetching and transforming in one place
def get_user_report(user_id):
    row = db.query("SELECT * FROM users WHERE id = ?", user_id)
    return {"name": row[0].upper(), "email": row[1].lower()}

# Simple: separate concerns, compose at the call site
def fetch_user_row(user_id: int) -> tuple:
    return db.query("SELECT * FROM users WHERE id = ?", user_id)

def normalize_user(row: tuple) -> dict:
    return {"name": row[0].upper(), "email": row[1].lower()}

# Caller composes
report = normalize_user(fetch_user_row(user_id))
```

### 2. Data Over Objects

Prefer plain data structures. Reach for `@dataclass(frozen=True)`, `TypedDict`, or `NamedTuple` before reaching for a class that bundles state with behavior. Data is inspectable, serializable, and straightforward to transform without side effects.

The distinction: a class that *holds* data is fine. A class that *is* data and also *does* things is complecting.

```python
# Complected: state and behavior in one artifact
class UserProfile:
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email

    def display(self) -> str:
        return f"{self.name} <{self.email}>"

    def validate(self) -> bool:
        return "@" in self.email

# Simple: data is data, behavior lives in free functions
from dataclasses import dataclass

@dataclass(frozen=True)
class UserProfile:
    name: str
    email: str

def display_user(user: UserProfile) -> str:
    return f"{user.name} <{user.email}>"

def is_valid_user(user: UserProfile) -> bool:
    return "@" in user.email
```

**When to use which data type:**

| Use | When |
|---|---|
| `@dataclass(frozen=True)` | Named, typed data that shouldn't change |
| `NamedTuple` | Lightweight, positional, interops with tuple unpacking |
| `TypedDict` | JSON-shaped data, API responses, config dicts |
| `tuple` / `frozenset` | Small collections of immutable values |
| Mutable `@dataclass` | Building up state incrementally; freeze at system boundaries if possible |

**Config for collaborator classes**: when a class needs configuration, pass parameters directly via `__init__` unless the config genuinely *travels* — loaded from files or env vars, shared across multiple consumers, or passed around independently. Only introduce a separate `@dataclass(frozen=True)` config class when the config has a life of its own beyond the single class that uses it.

```python
# Config doesn't travel — use plain __init__ parameters
class SMSNotifier:
    def __init__(self, account_sid: str, auth_token: str, from_number: str, to_numbers: list[str]) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number
        self._to_numbers = to_numbers

    def send(self, message: Message) -> NotificationResult: ...

# Config travels (loaded from env, shared across multiple consumers) — separate config class
@dataclass(frozen=True)
class SMSConfig:
    account_sid: str
    auth_token: str
    from_number: str
    to_numbers: tuple[str, ...]

config = SMSConfig.from_env()
notifier = SMSNotifier(config)
alerter = SMSAlerter(config)
```

### 3. Pure Functions First

A pure function returns the same output for the same input and has no side effects. It is the simplest unit of logic: testable in isolation, composable freely, understandable without surrounding context.

Write pure functions by default. Push side effects — I/O, database calls, mutation, logging — to the edges of your system. The goal is a pure core with a thin impure shell.

```python
# Impure: logic and side effects entangled
def process_order(order_id: int) -> Decimal:
    order = db.get(order_id)                        # side effect
    total = sum(item.price for item in order.items)
    db.save(order_id, total=total)                  # side effect
    log.info(f"Processed {order_id}")               # side effect
    return total

# Simple: pure core, side effects handled by the caller
def calculate_total(items: list[Item]) -> Decimal:
    return sum(item.price for item in items)

# Caller owns the I/O
order = db.get(order_id)
total = calculate_total(order.items)
db.save(order_id, total=total)
log.info(f"Processed {order_id}")
```

### 4. Composition Over Inheritance

Inheritance braids a parent's concerns into the child permanently. It creates hidden dependencies, makes behavior hard to trace, and makes testing harder — you cannot test the child without the parent.

Prefer:
- **Free functions** that operate on data (no inheritance needed)
- **`typing.Protocol`** for structural polymorphism — duck typing with type safety, zero coupling
- **`functools.singledispatch`** for dispatching by type without a class hierarchy
- **Explicit composition** — pass collaborators as arguments

```python
# Complected: behavior locked into an inheritance hierarchy
class Animal:
    def speak(self) -> str: ...

class Dog(Animal):
    def speak(self) -> str:
        return "woof"

class Cat(Animal):
    def speak(self) -> str:
        return "meow"

# Simple: Protocol — any object with a speak() method qualifies, no coupling
from typing import Protocol

class Speaker(Protocol):
    def speak(self) -> str: ...

def make_noise(thing: Speaker) -> str:
    return thing.speak()

# No base class needed — Duck and Robot both work if they have speak()
```

When you do need shared behavior across types, prefer a free function that accepts a Protocol over a base class with inherited methods.

### 5. Immutability Preferred

Mutable state is the primary source of accidental complexity. When data can change, you must track *when* and *why* it changed to understand the system. Each mutation is a hidden dependency on time.

Prefer immutable values. When you need to "update" something, return a new value instead of mutating the existing one.

```python
from dataclasses import dataclass, replace

# Mutable: when did timeout change? who changed it?
@dataclass
class Config:
    timeout: int = 30
    retries: int = 3

config = Config()
config.timeout = 60  # somewhere, somehow

# Immutable: each state is explicit and traceable
@dataclass(frozen=True)
class Config:
    timeout: int = 30
    retries: int = 3

updated_config = replace(config, timeout=60)  # original unchanged
```

Use `dataclasses.replace()` to derive new instances from existing ones. This pattern makes state changes explicit and auditable.

### 6. Separate What from How

The *policy* (what should happen) should be separate from the *mechanism* (how it happens). Keeping them together means you cannot change the policy without touching the mechanism, or vice versa.

A function that decides *what* to do and also *does* it is complected. Extract the decision into data or a pure function; let the mechanism be a separate concern.

```python
# Complected: policy and mechanism together
def send_alerts(events: list[Event]) -> None:
    for event in events:
        if event.severity > 5:
            smtp.send(event.message, to="ops@company.com")

# Simple: policy is pure, mechanism is separate
def is_critical(event: Event) -> bool:
    return event.severity > 5

def alert_message(event: Event) -> str:
    return event.message

# Mechanism is isolated — easy to swap, test, or mock
critical_messages = [alert_message(e) for e in events if is_critical(e)]
smtp.send_bulk(critical_messages, to="ops@company.com")
```

### 7. Polymorphism A La Carte

When behavior needs to vary by type, use `functools.singledispatch` rather than inheritance. This lets you add new behaviors for new types without modifying existing code.

```python
from functools import singledispatch
from datetime import datetime
from decimal import Decimal

@singledispatch
def serialize(value) -> str:
    return str(value)

@serialize.register(datetime)
def _(value: datetime) -> str:
    return value.isoformat()

@serialize.register(Decimal)
def _(value: Decimal) -> str:
    return f"{value:.2f}"
```

New types get new dispatch registrations — existing code is untouched.

### 8. Explicit Dependencies

A function that reaches into global state or imports a singleton is complecting its logic with the surrounding environment. Pass dependencies explicitly as arguments. This makes the function's requirements visible, testable, and replaceable.

```python
# Complected: hidden dependency on global state
def get_feature_flag(flag_name: str) -> bool:
    return GLOBAL_CONFIG["flags"].get(flag_name, False)

# Simple: dependency is explicit
def get_feature_flag(flag_name: str, config: Config) -> bool:
    return config.flags.get(flag_name, False)
```

---

## Anti-Patterns (Complecting)

Flag these as design smells and explain which concerns are braided together:

| Anti-pattern | What's complected |
|---|---|
| **God class** | State + identity + behavior + I/O in one artifact |
| **Method with side effects on a data class** | Data storage + external action (e.g., `User.save()`) |
| **Deep inheritance hierarchy (3+ levels)** | Multiple layers of behavior coupling |
| **Boolean parameter that changes behavior** | Two functions pretending to be one (`process(data, validate=True)`) |
| **Output parameters / mutating arguments** | Function's logic + caller's state management |
| **Mutable global state** | Module-level variables that change at runtime |
| **Mixed abstraction levels** | High-level orchestration and low-level parsing in one function |
| **Implicit ordering requirements** | Functions that must be called in a specific sequence to work correctly |
| **`isinstance` chains** | Type dispatch woven into business logic |
| **Scoped imports** | `import x` inside a function or method — imports belong at module level; scoped imports hide dependencies and make the module's requirements non-obvious |

---

## Pragmatic Exceptions

These patterns deviate from strict Hickey ideals but are idiomatic Python. Treat them as blessed — do not flag them as anti-patterns:

| Pattern | Why it's acceptable |
|---|---|
| **Classes with methods** | Fine when methods are thin; prefer free functions for significant logic |
| **Generators and iterators** | Internal state is an implementation detail; lazy evaluation is often simpler overall |
| **Context managers (`with`)** | The right Python pattern for lifecycle management; not complecting |
| **Framework idioms** | Django models, SQLAlchemy ORM, FastAPI routes — follow the framework's conventions within the framework's domain |
| **List comprehensions** | Idiomatic Python; prefer over `map`/`filter` for readability |
| **`dataclasses` with mutation** | Acceptable when building state incrementally; aim to freeze at system boundaries |

---

## Explaining the Philosophy to Unfamiliar Users

When the user doesn't know Hickey's work, frame it this way:

> Rich Hickey's "Simple Made Easy" (2011) draws a sharp line between *simple* (having one purpose, not tangled with other things) and *easy* (familiar, close at hand). Most software complexity comes from braiding together concerns that could be kept separate — he calls this "complecting". A complected system is hard to understand because you cannot reason about one part without understanding all the parts it's tangled with.
>
> The antidote is to build systems from small, independent pieces that compose cleanly. In Python, this means pure functions, frozen dataclasses, structural protocols, and pushing side effects to the edges. The result feels like more pieces, but each piece is simple — and simple things stay understandable as the system grows.

---

## Using This Reference from Other Skills

**Code review**: For each function and class, check against the anti-patterns table. Identify which concerns are complected and explain why that makes the code harder to change or test.

**Refactoring**: Use the "Instead of / Prefer" quick reference in `SKILL.md` as your rewrite targets. Start by identifying complecting, then split concerns, then apply the relevant pattern.

**Education**: Lead with the Simple vs Easy distinction. Explain *why* a pattern is problematic (what becomes hard when concerns are braided) before showing *what* to do instead.