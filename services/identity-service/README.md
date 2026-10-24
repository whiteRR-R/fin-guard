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
