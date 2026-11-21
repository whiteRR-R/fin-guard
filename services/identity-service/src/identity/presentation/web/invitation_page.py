import secrets

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

ACCEPT_INVITATION_PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FinGuard</title>
<style nonce="__NONCE__">
  :root { color-scheme: light dark; --fg: #111; --muted: #777; --line: #ddd; --bg: #fff; }
  @media (prefers-color-scheme: dark) {
    :root { --fg: #eee; --muted: #888; --line: #333; --bg: #111; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px;
         background: var(--bg); color: var(--fg); font: 15px/1.5 system-ui, sans-serif; }
  form { width: 100%; max-width: 320px; }
  h1 { font-size: 18px; font-weight: 600; margin: 0 0 32px; }
  input { display: block; width: 100%; padding: 10px 0; margin-bottom: 20px; border: 0;
          border-bottom: 1px solid var(--line); background: transparent; color: inherit;
          font: inherit; outline: none; }
  input:focus { border-bottom-color: var(--fg); }
  button { width: 100%; margin-top: 12px; padding: 11px; border: 1px solid var(--fg);
           background: var(--fg); color: var(--bg); font: inherit; cursor: pointer; }
  button:disabled { opacity: .4; cursor: default; }
  #message { margin: 16px 0 0; min-height: 22px; font-size: 14px; color: var(--muted); }
</style>
</head>
<body>
<form id="form" novalidate>
  <h1>FinGuard</h1>
  <input id="password" type="password" placeholder="Пароль" aria-label="Пароль"
         autocomplete="new-password" maxlength="72" required>
  <input id="confirmation" type="password" placeholder="Повторите пароль"
         aria-label="Повторите пароль" autocomplete="new-password" maxlength="72" required>
  <button id="submit" type="submit">Активировать</button>
  <p id="message" role="status"></p>
</form>
<script nonce="__NONCE__">
  const token = new URLSearchParams(window.location.search).get("token");
  window.history.replaceState(null, "", window.location.pathname);

  const form = document.getElementById("form");
  const button = document.getElementById("submit");
  const message = document.getElementById("message");
  const show = (text) => { message.textContent = text; };

  if (!token) {
    show("Ссылка неполная. Откройте её из письма.");
    button.disabled = true;
  }

  const errors = {
    404: "Приглашение не найдено.",
    409: "Приглашение уже использовано или отозвано.",
    410: "Срок приглашения истёк.",
    422: "Пароль должен быть не короче 12 символов.",
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = document.getElementById("password").value;
    const confirmation = document.getElementById("confirmation").value;

    if (password.length < 12) return show("Минимум 12 символов.");
    if (new TextEncoder().encode(password).length > 72) return show("Слишком длинный пароль.");
    if (password !== confirmation) return show("Пароли не совпадают.");

    button.disabled = true;
    show("");
    try {
      const response = await fetch("/api/v1/invitations/accept", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
        credentials: "omit",
        cache: "no-store",
      });
      if (response.status === 204) {
        form.querySelectorAll("input").forEach((input) => {
          input.value = "";
          input.disabled = true;
        });
        return show("Готово. Теперь можно войти.");
      }
      show(errors[response.status] || "Ссылка недействительна.");
    } catch (error) {
      show("Сервер недоступен.");
    }
    button.disabled = false;
  });
</script>
</body>
</html>
"""


def _security_headers(nonce: str) -> dict[str, str]:
    return {
        "Content-Security-Policy": (
            "default-src 'none'; "
            f"script-src 'nonce-{nonce}'; "
            f"style-src 'nonce-{nonce}'; "
            "connect-src 'self'; "
            "form-action 'none'; "
            "base-uri 'none'; "
            "frame-ancestors 'none'"
        ),
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
    }


@router.get("/invitations/accept", include_in_schema=False)
@router.get("/accept-invitation", include_in_schema=False)
async def accept_invitation_page() -> HTMLResponse:
    nonce = secrets.token_urlsafe(16)
    return HTMLResponse(
        ACCEPT_INVITATION_PAGE.replace("__NONCE__", nonce),
        headers=_security_headers(nonce),
    )
