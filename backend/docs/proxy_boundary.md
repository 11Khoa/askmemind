# API proxy boundary

Compose publishes API port 8000 on host loopback only. External traffic must use
an HTTPS reverse proxy. Keep PostgreSQL/Redis unpublished. An external check of
`VPS_IP:8000` should fail while the HTTPS API succeeds; verify firewall/Docker
rules on the actual host rather than relying on this source configuration alone.

Uvicorn uses `FORWARDED_ALLOW_IPS` to decide which peer may supply forwarded
client addresses. Use explicit trusted addresses/networks, not `*`. With host
Nginx forwarding into a Docker-published port, the peer may be a Docker gateway,
not 127.0.0.1. Inspect that deployment's network and access logs, then configure
the actual proxy peer. Confirm two external clients have distinct rate-limit
identities and a direct client cannot spoof its IP with X-Forwarded-For.

The Nginx example is a template; terminate HTTPS with valid certificates and
review trusted-proxy settings before deployment. No production network/firewall
was changed by this repository fix.
