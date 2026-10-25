#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image=${TRAEFIK_TEST_IMAGE:-$(docker inspect traefik-traefik-1 --format '{{.Image}}')}
volume=$(docker volume create)
container=
trap 'if [[ -n "$container" ]]; then docker rm -f "$container" >/dev/null; fi; docker volume rm "$volume" >/dev/null' EXIT
# All generated keys, certificates, and ACME state stay in a disposable volume.
docker run --rm --userns=host --network none -v "$volume:/test" --entrypoint /bin/sh "$image" -c 'cp /traefik /test/traefik'
docker run --rm --userns=host --network none -v "$volume:/test" -v "$PWD:/repo:ro" python:3.14-slim python /repo/tests/acme.py prepare
container=$(docker run -d --rm --userns=host --network none --user 1000:1000 -v "$volume:/test" -v "$volume:/run/secrets:ro" -e CF_DNS_API_TOKEN_FILE=/run/secrets/cloudflare-token --entrypoint /test/traefik "$image" --configFile=/test/traefik.yml)
docker run --rm --userns=host --network "container:$container" -v "$volume:/test" -v "$PWD:/repo:ro" python:3.14-slim python /repo/tests/acme.py verify
docker logs "$container" 2>&1 | tee /dev/stderr | (! rg '"level":"error"')
docker compose config --quiet
