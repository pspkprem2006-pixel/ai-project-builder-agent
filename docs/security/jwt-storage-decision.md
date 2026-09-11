# JWT Storage Decision — localStorage vs httpOnly Cookies

**Status:** Decision recorded (Phase 8, Part 11). No code change in this phase.

## Current state

- The frontend stores the JWT in `localStorage` (`frontend/src/lib/auth-context.ts`) and
  sends it as an `Authorization: Bearer` header.
- Deployment topology in `docker-compose.yml`: frontend on `:3010`, backend on `:8010`,
  **no TLS** (plain HTTP), two separate origins, CORS restricted to explicit origins.

## Why localStorage is retained

An httpOnly cookie is only meaningfully more secure than localStorage when the whole
chain is in place:

1. **HTTPS everywhere** — `Secure` cookies are dropped on HTTP; without TLS the token is
   already exposed in transit regardless of storage.
2. **SameSite / CSRF** — a SameSite cookie with credentials requires CSRF tokens for
   cross-site request forgery protection on every state-changing endpoint.
3. **Cookie scope** — frontend (`:3010`) and backend (`:8010`) are different registrable
   origins; a first-party cookie on `:3010` is NOT sent to `:8010` automatically, so the
   current split-origin topology would need a reverse proxy making both origins share a
   host before cookies give any benefit.

Because the current intended production topology (docker-compose, split origins, plain
HTTP behind the operator's own TLS proxy decision) does **not** yet satisfy (1)–(3), the
JWT stays in localStorage. The XSS risk of localStorage is mitigated today by the
hardened Mermaid renderer and React's default output escaping.

## Decision

**Keep localStorage for now.** Do not introduce a half-cookie/half-localStorage
architecture.

## Requirements for the future cookie migration

Adopt all of the following at once, then switch the client to cookie-based auth:

1. **Single origin via reverse proxy** — serve frontend and `/api/v1` from one hostname
   (e.g. nginx/Caddy), or a dedicated auth domain with a cross-site cookie policy.
2. **HTTPS with a valid certificate** (TLS termination at the proxy).
3. **httpOnly + Secure + SameSite=Lax** (Strict if no external link flows) on the JWT cookie.
4. **CSRF protection** — double-submit token or SameSite + custom-header verification for
   all mutating endpoints; add a CSRF middleware before rollout.
5. **Short-lived access tokens + refresh rotation** — cookies alone do not add revocation;
   keep the 24h expiry and add refresh-token rotation with reuse detection.
6. **Logout** must clear the cookie server-side (Set-Cookie with expired Max-Age).
7. **Audit** — after migration, remove all `localStorage` token reads/writes from the
   frontend and assert in CI that no `localStorage` auth key is referenced.

## Rejected alternatives

- **Middleware-only cookie issuance without the above** — creates a two-path token flow
  and complicates every client call; rejected per "no half-cookie architecture".
- **Redis/session store** — JWT remains stateless by design; no added infrastructure
  until a revocation requirement is demonstrated.