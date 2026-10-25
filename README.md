# traefik
Setup traefik to serve intranet services from docker and others with https

Cloudflare DNS-01 ACME for the mirrored intranet names is prepared here. See
[ACME setup and validation](docs/acme.md) before deployment; credentials, state,
DNS and application migration must be provisioned first.

## Security baseline

This compose project uses the shared [docker-compose-security-baseline](https://github.com/Enucatl/docker-compose-security-baseline) for common container hardening defaults, including capabilities, no-new-privileges, memory/swap, and PID limits.

## Healthchecks

Traefik uses `traefik healthcheck --ping` against the `:8082` ping entrypoint every 30s.

The socket-proxy healthcheck is disabled. The image’s `--healthcheck` dials `/run/proxy/docker.sock`, which is owned by `SOCKET_PROXY_UID`/`GID` (`101000`) so remapped Traefik can connect. Docker always runs the healthcheck as the container `user` (`0:988`, required for host `docker.sock` / group `docker`). With `cap_drop: ALL` there is no `CAP_DAC_OVERRIDE`, so that check cannot open the proxy socket and always fails. Compose cannot run the healthcheck as a different user.
