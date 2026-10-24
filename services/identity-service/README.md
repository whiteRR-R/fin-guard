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

## Deliver invitation emails

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_FROM_EMAIL`, and
`INVITATION_ACCEPT_URL` in `.env`. Set both `SMTP_USERNAME` and `SMTP_PASSWORD`
when the mail server requires authentication; omit both otherwise. The URL is
the frontend page where an employee accepts an invitation. The worker appends
the invitation token as the `token` query parameter.

Run the worker as a separate process after applying migrations:

```sh
uv run alembic upgrade head
uv run python -m identity.outbox_worker
```

Use `--once` to process currently due invitations and exit. Failed deliveries
are retried with a delay. The worker records success after SMTP accepts the
message; a crash between these steps may cause the same invitation email to be
sent again.
