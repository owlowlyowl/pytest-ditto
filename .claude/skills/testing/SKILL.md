---
name: testing
description: >
  Write and review high-quality unit tests following behaviour-driven testing principles.
  Ensures tests are readable specifications, properly structured, well-named, and organised
  by behaviour rather than by class. Use this skill whenever writing new tests, reviewing
  existing tests, refactoring test suites, or discussing test strategy, test naming, test
  structure, test readability, or test organisation. Also use when the user mentions
  Good Unit Tests, Arrange-Act-Assert, Given-When-Then, test smells, or test as documentation.
metadata:
  author: owlowlyowl
  version: 1.0.0
  category: testing
---

# Testing Standards

Tests are communication first, verification second. Write every test as if the
failure report — the test name, the assertion, nothing else — must tell the next
developer exactly what broke and why it matters. If you cannot understand a test
in ten seconds, it needs rewriting.

---

## Core Conventions

- Use `pytest` as the test runner.
- Write test functions, not test classes. Use modules for logical grouping.
- Place tests in `tests/`, mirroring the source package structure.
- Write tests for all new code and features.
- Tests are code and code is a liability. Every test must justify its existence
  with clear value — confidence, documentation, or design feedback. Prioritise
  tests that verify real behaviour over achieving a 100% coverage metric.

---

## Naming Tests

Name every test as a behaviour specification. The name must make the failure
report self-explanatory without reading the test body.

Use the `behaviour_when_context` pattern:

```
test_returns_par_yield_when_curve_is_flat
test_raises_when_maturity_is_negative
test_returns_nan_when_input_contains_missing_values
test_produces_negative_forward_rate_when_curve_is_inverted
```

Do not name tests after the method under test:

```
test_interpolate       # bad — describes the method, not the behaviour
test_yield_curve       # bad — describes the subject, not the behaviour
test_calculate         # bad — meaningless without context
```

A test name that requires "and" to describe what it does is testing too many
things. Split it.

---

## Test Structure

Every test has three phases: Arrange, Act, Assert. Separate them with a blank
line. Do not write `# Arrange`, `# Act`, or `# Assert` comments. Simple tests
may omit an empty Arrange phase and go straight to Act.

```python
def test_returns_lower_discount_factor_when_rate_increases() -> None:
    """A higher rate produces a lower discount factor at the same tenor."""
    low_rate_curve = FlatCurve(rate=0.01)
    high_rate_curve = FlatCurve(rate=0.05)
    tenor = 5.0

    low_rate_factor = low_rate_curve.discount_factor(tenor)
    high_rate_factor = high_rate_curve.discount_factor(tenor)

    assert high_rate_factor < low_rate_factor
```

When testing for a concrete expected value, name the result `actual` and the
reference value `expected`. Always write `assert actual == expected`:

```python
def test_returns_par_yield_when_curve_is_flat() -> None:
    """Par yield equals the flat rate when the yield curve has no slope."""
    curve = FlatCurve(rate=0.05)

    actual = curve.par_yield(tenor=10.0)

    expected = 0.05
    assert actual == expected
```

Do not force `actual`/`expected` naming for relational or approximate
comparisons — use direct assertions instead (`assert result < threshold`,
`pytest.approx`).

- Write one short docstring sentence stating the invariant being tested.
  Do not write `Parameters`, `Returns`, or `Examples` sections in test
  docstrings.
- One logical concept per test. Multiple assertions are acceptable when they
  jointly describe a single outcome.
- Never put conditional logic (`if`, `for`, `while`) inside a test body.
  If branching seems necessary, write separate tests.

---

## Organisation

Group tests by behaviour, not by class or method.

```
tests/
  test_yield_curve_interpolation.py    # all interpolation scenarios
  test_yield_curve_discounting.py      # all discount factor scenarios
  test_forward_rate_calculation.py     # all forward rate scenarios
```

A single production function may have many behavioural tests. A single
behaviour may span multiple functions. Let tests follow the behaviour,
not the source file structure.

---

## Assertions

- Assert only on values returned by or observable through the public interface.
- Never assert on private attributes or internal call order.
- Use `pytest`'s assertion rewriting — avoid `assert x, "message"` unless the
  failure would otherwise be ambiguous.

For floating-point comparisons, use `pytest.approx` rather than exact equality.
Set `abs` or `rel` tolerance explicitly when the default is not appropriate for
the domain:

```python
def test_price_converges_to_par_at_maturity() -> None:
    """Bond price converges to par as time to maturity approaches zero."""
    bond = Bond(coupon=0.05, face=100.0)

    actual = bond.price(ttm=1e-6, yield_=0.05)

    assert actual == pytest.approx(100.0, abs=1e-4)
```

---

## Async Tests

Use `anyio` for async code and `pytest-anyio` for async test functions.

```python
import pytest

@pytest.mark.anyio
async def test_fetches_rate_when_endpoint_is_reachable() -> None:
    """Client returns a non-null rate for a reachable endpoint."""
    actual = await fetch_rate("USD", tenor=1.0)

    assert actual is not None
```

---

## Library Version Awareness

Use modern idioms appropriate for the minimum versions in use:

| Library      | Minimum version |
|--------------|-----------------|
| `numpy`      | 2.2.0           |
| `pandas`     | 2.3.0           |
| `polars`     | 1.31.0          |
| `sqlalchemy` | 2.0.37          |

---

## What to Avoid

**Eager test.** A test that verifies more than one logical concept produces an
ambiguous failure. If the test name requires "and", split it into separate
tests, one behaviour each.

**Incidental detail.** Setup code containing values irrelevant to the specific
test obscures intent. Keep the Arrange phase focused — extract unrelated setup
to well-named helpers or fixtures.

**Mystery guest.** A test that depends on data loaded from external files,
databases, or fixtures not visible in the test body is hard to understand in
isolation. Make all inputs explicit and inline.

**General fixture.** A single fixture that wires up every dependency and
creates the full subject-under-test hides which collaborators each individual
test actually cares about. Prefer focused, single-purpose fixtures — one per
collaborator — composed into the subject by the test itself, or a lightweight
factory function that accepts only the dependencies a given test needs.

**Assertion roulette.** Multiple unrelated assertions in one test produce
failures that do not identify which behaviour broke. One concept per test.

**Fragile test.** A test that breaks on refactoring when observable behaviour
is unchanged is asserting on implementation details. Assert on outcomes only —
never on private attributes or internal call order.

**Obscure test.** A test that cannot be understood without reading the
production code has failed as documentation. Improve naming, simplify setup,
and make intent obvious in the test body itself.

**Mocking everything.** Prefer real dependencies where practical. Mock only
what you must — network calls, filesystem access, time. Overuse of mocks
creates tests that verify wiring, not behaviour.

---

## When Something Is Hard to Test

> **Hard to name?** The test probably covers too many things. Split it.
>
> **Hard to set up?** The production code may have too many dependencies.
> Let the test friction improve the design rather than adding complexity
> to the test.
>
> **Breaks on refactoring when behaviour is unchanged?** The test is coupled
> to implementation details. Assert on observable outcomes only.
>
> **Requires exposing private state?** The design is wrong, not the test.
> Test through the public interface.
>
> **Flaky?** Find and eliminate hidden dependencies — time, randomness,
> shared state, network.

---

*Inspiration drawn from Kevlin Henney's "Programming with GUTs" and
"Structure and Interpretation of Test Cases."*