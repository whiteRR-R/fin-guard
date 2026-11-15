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

## Service accounts

External systems authenticate as service accounts. Set `CLIENT_SECRET_HASH_KEY`
in `.env` (at least 32 bytes, `openssl rand -hex 32`) and apply migrations.
`MACHINE_TOKEN_LIFETIME_SECONDS` (default 900, at most 3600) and
`CLIENT_SECRET_ROTATION_GRACE_HOURS` (default 24, at most 168) are optional.

An administrator creates a service account with an employee access token. The
response contains `client_secret` only once; store it in the external system's
secret storage immediately.

```sh
curl -X POST http://localhost:8000/api/v1/service-accounts \
  -H "Authorization: Bearer $ADMIN_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Bank X backend", "scopes": ["transactions:write"]}'
```

The external system exchanges its credentials for a short-lived access token
using the OAuth 2.0 client credentials grant. Credentials may be sent with HTTP
Basic authentication or in the form body, but not both. `scope` is optional and
may only narrow the granted scopes. There is no refresh token: request a new
access token when the current one expires.

```sh
curl -X POST http://localhost:8000/api/v1/oauth/token \
  -u "$CLIENT_ID:$CLIENT_SECRET" \
  -d grant_type=client_credentials \
  -d scope=transactions:write
```

`POST /api/v1/service-accounts/{id}/secrets` issues a new secret. The previous
secret keeps working for the configured grace period so the client can switch
without downtime. `DELETE /api/v1/service-accounts/{id}` revokes the account and
all its secrets permanently.

## Rate limits

`POST /api/v1/auth/login` and `POST /api/v1/oauth/token` are rate limited.
Counters are stored in PostgreSQL, so limits hold across API replicas and
workers. Only SHA-256 hashes of IP addresses, emails and client IDs are stored.

| Limit | Counts | Default |
|---|---|---|
| Login per IP | every attempt | 30 per 5 minutes |
| Login per email | failed attempts | 5 per 15 minutes |
| Token per IP | every request | 120 per minute |
| Token per client_id | failed attempts | 10 per 5 minutes |

A limited request gets `429` with a `Retry-After` header. Defaults can be
changed with `LOGIN_ATTEMPTS_PER_IP`, `LOGIN_IP_WINDOW_SECONDS`,
`LOGIN_FAILURES_PER_EMAIL`, `LOGIN_EMAIL_WINDOW_SECONDS`,
`TOKEN_REQUESTS_PER_IP`, `TOKEN_IP_WINDOW_SECONDS`,
`TOKEN_FAILURES_PER_CLIENT` and `TOKEN_CLIENT_WINDOW_SECONDS`.

Limits per IP rely on the real client address. Behind a reverse proxy, set
`IDENTITY_FORWARDED_ALLOW_IPS` to the proxy address so the API trusts its
`X-Forwarded-For` header; otherwise every request appears to come from the proxy.

## Run with Docker

Fill in `.env` from `.env.example`, then start the database, migrations, API and
outbox worker:

```sh
docker compose up --build
```

`identity-migrate` applies migrations and exits; the API and the worker start
only after it succeeds. The API listens on `IDENTITY_API_PORT` (default 8000).
Inside containers the database host is `identity-database`, which compose sets
in `DATABASE_URL` automatically. `SMTP_HOST=localhost` points at the worker
container itself, so set it to a reachable mail server. Create the first
administrator with:

```sh
docker compose run --rm identity-api python -m identity.cli create-admin --email admin@example.com
```
