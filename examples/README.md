# Examples

These examples are runnable snapshots patterns that sit outside the default
`tests/ci` collection. Run them directory-by-directory so each example can use
the configuration and optional dependencies it needs.

## Quick Start

```bash
pixi run -e examples examples-local
pixi run -e examples examples-postgres-up
pixi run -e examples examples-postgres
pixi run -e examples examples-redis-up
pixi run -e examples examples-redis
pixi run -e examples examples-duckdb
```

The examples Pixi environment installs the Python dependencies needed by the
Redis, DuckDB, and Postgres examples.

The Redis example also needs Docker because the example starts a real Redis
container from `redis:7-alpine`.

The Postgres example also needs Docker because the example starts a real
PostgreSQL container from `postgres:16-alpine`.

The DuckDB example needs no extra runtime setup once the `examples`
environment is available.

## Persistence

These examples are configured so you can play with the backing stores across
multiple runs.

- The first run writes the stored values.
- Later runs read from the same target again.
- Reset tasks are available when you want to get back to a clean first-run
  state.

Postgres persistence:

- target profile: `postgres_frames`
- target URI: `postgresql://localhost:5433/ditto_examples`
- runtime: Docker container `pytest-ditto-examples-postgres`
- storage: Docker volume `pytest-ditto-examples-postgres`
- recorder: `@ditto.pandas.json`

Redis persistence:

- target: `redis://localhost:6380/0`
- runtime: Docker container `pytest-ditto-examples-redis`
- storage: Docker volume `pytest-ditto-examples-redis`

DuckDB persistence:

- target: `duckdb:///.../examples/duckdb/.example-snapshots.duckdb`
- storage: `.example-snapshots.duckdb` beside the DuckDB example files

Reset commands:

```bash
pixi run -e examples examples-postgres-reset
pixi run -e examples examples-redis-reset
pixi run -e examples examples-duckdb-reset
```

## Requirements

The Postgres example needs:

- Docker with the daemon running locally
- optional auth overrides via `DITTO_POSTGRES_USER` and `DITTO_POSTGRES_PASSWORD`
- the examples Pixi environment so `pytest-ditto-pandas` and `psycopg2` are available

The Redis example needs:

- Docker with the daemon running locally
- optional auth via `REDIS_USERNAME` and `REDIS_PASSWORD`

The DuckDB example optionally uses:

- `MOTHERDUCK_TOKEN` if you point it at a MotherDuck target

## Layout

| Directory | What it shows | Extra setup |
|---|---|---|
| `examples/local` | explicit `file://` target and project-wide `ditto_target` | none |
| `examples/postgres` | a named `target_profile` that points at a persistent PostgreSQL backend and stores pandas dataframes | Docker |
| `examples/redis` | a registered `redis://` backend backed by a persistent Docker container | Docker |
| `examples/duckdb` | a registered `duckdb://` backend backed by a persistent local file | none |

## Notes

- `examples/conftest.py` provides shared raw-target `ditto_storage_options`.
- The Redis and DuckDB examples register their backends in example-local
  `conftest.py` files because this repository does not ship installable
  `ditto_backends` plugins for those schemes.
- `examples/postgres` does the same for `postgresql://`, but it resolves the
  backend through a named `ditto_target_profiles` entry so the example shows the
  profile path rather than the raw-target path.
- `examples/local` includes its own `pytest.ini` so `ditto_target` stays scoped
  to that directory.
- `examples-postgres-up` starts or reuses the persistent PostgreSQL container on
  port `5433` so the example does not collide with a host PostgreSQL server on
  `5432`.
- `examples-redis-up` starts or reuses the persistent Redis container on port
  `6380` so the example does not collide with a host Redis on `6379`.
- The DuckDB example defaults to a persistent file in `examples/duckdb/`.
  Override it with `DITTO_DUCKDB_TARGET=duckdb:///absolute/path/to/snaps.duckdb`
  or `DITTO_DUCKDB_TARGET=duckdb://md:mydb` if you want a different local file
  or a MotherDuck target instead.
- Generated example artifacts are ignored by `examples/.gitignore`.
