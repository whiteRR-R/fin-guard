# FinGuard Identity Service

## Create the first administrator

Set `DATABASE_URL` in `.env` and apply the database migrations before creating
the administrator. The CLI uses the same database settings as the service.

```sh
uv sync
uv run alembic upgrade head
uv run python -m identity.cli create-admin --email admin@example.com
```

The CLI asks for the password twice without displaying it. The command can only
create the first administrator; additional employees are added through invitations.

## Run the API

Set three distinct signing keys in `.env`. Each key must be at least 32 bytes;
`openssl rand -hex 32` generates a suitable value. Start PostgreSQL and apply
migrations before starting the API:

```sh
uv run alembic upgrade head
uv run uvicorn identity.asgi:create_application --factory
```

The API checks the database connection on startup and closes its connection pool
on shutdown.
