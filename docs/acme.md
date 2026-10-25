# Cloudflare ACME preparation

This change is configuration preparation only. Do not restart production until
the provisioning and migration steps below are complete. The Technitium candidate
remains inactive. No public DNS changes or live issuance are part of local tests.

The new namespace is additive: `home.arpa` remains supported with its existing
routes, DNS and Vault certificates. New names may point to the same services;
there is no planned removal or replacement of `home.arpa` in this work.

## Certificate and routing

The `cloudflare` resolver uses Traefik's built-in DNS-01 issuance and renewal,
with explicit `EC256` (ECDSA P-256) keys. The dashboard router explicitly requests
one certificate for `atlas.intranet.enucatl.com` and
`*.atlas.intranet.enucatl.com`. It does not infer certificates from individual
service names or request certificates for `home.arpa`. Other routers can use
`tls: {}` and receive the matching certificate through SNI. Do not attach the
resolver to every service. For another host, add one explicit domain pair,
`host.intranet.enucatl.com` plus `*.host.intranet.enucatl.com`, to the requesting
router's `tls.domains`; no extra container is needed.

The wildcard covers `jellyfin.atlas.intranet.enucatl.com`, but neither the Atlas
exact name nor deeper names such as `a.b.atlas.intranet.enucatl.com`.
`*.intranet.enucatl.com` would not cover Jellyfin. The existing default Vault PEM
certificate stays in place for `home.arpa` and unmatched SNI. The current image,
including ML-DSA support, TLS 1.3 minimum, mTLS IPA trust, allowlists, Authelia,
redirect and unknown-host router remain unchanged. `data/unifi.yml` defines only
a backend transport and needs no hostname alias.

## Credentials and persistent state

Create a dedicated Cloudflare API token with Zone / Zone / Read and Zone / DNS /
Edit, restricted to the `enucatl.com` zone. Do not use the global API key or the
router/DDNS token. Store only the raw token in the local, Git-ignored file
`secrets/cloudflare_dns_api_token`. Compose exposes it as a read-only secret and passes
`CF_DNS_API_TOKEN_FILE=/run/secrets/cloudflare_dns_api_token`. Do not put the token
in Compose, `.env`, Git, shell history or test logs.

The running container's UID map is `0 -> 100000`, so container `1000:1000` maps to
host `101000:101000`. Create the secret under your own user with mode `0600`.
Puppet's Atlas ACL configuration grants host UID `101000` read-only access to
the token and traversal of `secrets/`, without changing file ownership. It
removes group and other access. Create the directory and token before Puppet
applies these ACLs. Recompute the mapped UID if Docker's remapping changes.
File-backed Compose secrets retain host ownership and permissions; Compose does
not remap them through secret `uid`/`gid` settings. Create the local directory and
file before starting Traefik.

ACME state uses the `acme` named volume at `/var/lib/traefik`. The `acme-init`
service sets the directory owner to container `1000:1000` and mode `0700` before
Traefik starts. Traefik creates `acme.json` with mode `0600` and owns updates
and renewal. The initializer does not replace or truncate existing state.

Back up the complete state securely (it contains private keys and the account),
preferably with Traefik stopped for a consistent copy, and preserve `0600` on
restore. Container recreation retains the named volume. Never share a
state file between instances. Use separate staging and production volumes
and accounts; never copy staging state into production. Puppet `vault_cert`
resources continue managing private and infrastructure certificates; ACME does
not replace Vault PKI.

The token is managed locally; no Puppet/Vault token provisioning is required.
Preserve `Vault_cert['atlas']`, current certificate ACLs, and
`trigger_traefik_reload`. Do not add this public certificate to `vault_cert`.

## DNS and application migration

In Technitium's internal authoritative `intranet.enucatl.com` zone, create
`atlas` A/AAAA records for Traefik's reachable private IPv4/IPv6 addresses and
either `*.atlas` A/AAAA records or explicit service records (including
`traefik.atlas`, `jellyfin.atlas`, etc.). Publish only addresses reachable by
those clients. Retain the existing `home.arpa` zone and records alongside it.

Cloudflare remains publicly authoritative for `enucatl.com`. No public service
A/AAAA records, inbound ACME ports, or delegation to Technitium are required.
Traefik temporarily creates public TXT records at
`_acme-challenge.atlas.intranet.enucatl.com` for both certificate identifiers.
Public recursive resolvers `1.1.1.1:53` and `8.8.8.8:53` avoid split DNS during
zone discovery and propagation checks. Checks remain enabled. Permit outbound
DNS (UDP/TCP 53), HTTPS to Cloudflare and the CA, and authoritative DNS queries
needed for propagation checks.

Only the dashboard route is owned here; its alias retains all middleware.
Docker-label routers in other stacks need their existing Host rule extended
with the new alias, preserving priority, middleware, TLS options and mTLS.
Do not duplicate those services in this repository. Before enabling aliases,
update Authelia session-cookie domain/portal settings for `intranet.enucatl.com`
alongside the old domain, access-control domain rules, and default redirects.
Review each application's trusted origins, proxy settings, base URL, redirects,
WebSocket origins and OAuth/OIDC callback registrations. A certificate alone
does not migrate an application. Services terminating TLS outside Traefik need
their own certificate-delivery arrangement; none is introduced here.

Concrete companion files include `authelia/config/configuration.yml` (add a
cookie entry for `atlas.intranet.enucatl.com`, the new Authelia URL and redirects;
mirror specific policies before the wildcard; review Jellyfin/Grafana/Beszel
OIDC callbacks and issuer identifiers) and `authelia/docker-compose.yml` (login
route alias). `jellyfin/docker-compose.yml` hardcodes the old domain in two
routers; `grafana-loki/docker-compose.yml` and `beszel/docker-compose.yml` use
`${DOCKER_DOMAIN}`. Add aliases rather than replacing that variable globally,
which would remove old URLs and change application settings. Audit the other
stacks' Docker labels similarly before their migration.

## Local verification

Run `bash tests/acme.sh` from this repository. The check uses disposable containers
and a temporary volume with the exact deployed image, no external network and
locally generated certificates. It validates Compose against the shared baseline,
the resolver and router settings, Atlas exact/wildcard SNI selection, the Vault
fallback and unchanged access-control references. Test-only Docker-provider and
Authelia substitutions allow an isolated dashboard router; application login and
production backend connectivity are outside that check.

## Isolated staging exercise (operator step)

After provisioning the dedicated token, copy the configuration into a temporary
directory. Use a separate empty state directory with the ownership and modes
above and set the copied resolver's `acme.caServer` to
`https://acme-staging-v02.api.letsencrypt.org/directory`. Mount that state at
`/var/lib/traefik`, the token read-only, and copied config at `/etc/traefik:ro`.
Run the same deployed image as `1000:1000`, with the normal Docker UID remapping,
on an isolated Docker network with outbound DNS/HTTPS. Publish HTTPS only on an
unused loopback port (for example `127.0.0.1:8443:443`); omit Docker provider,
production backend networks and production ports. Supply copied local test PEMs
for the default certificate and IPA CA. Replace the copied dynamic configuration
with just a test router (`noop@internal`, Atlas Host, TLS resolver and the domain
pair above), retaining the default certificate. Keep the copied static resolver,
including its EC256 key type and public DNS resolvers.

Starting this isolated instance performs real staging issuance and changes
public challenge TXT records: run it only as a separately authorized live test.
Inspect resolver logs, verify TXT propagation using public resolvers, and connect
with SNI `jellyfin.atlas.intranet.enucatl.com` to loopback port 8443. Extract the
peer certificate with `openssl s_client -connect 127.0.0.1:8443 -servername
jellyfin.atlas.intranet.enucatl.com -showcerts` and inspect it with
`openssl x509 -noout -text`: verify both SANs, `id-ecPublicKey`, and
`prime256v1`/`secp256r1`. Staging chains are intentionally untrusted. Recreate the
instance with the same staging state to check persistence; inspect renewal logs
over its lifetime. Stop/remove the test instance and temporary network afterward;
securely remove test state when no longer needed. Production uses the default
Let's Encrypt directory with its own initially empty state, never staging state.

Live Cloudflare issuance, CA key selection in an issued certificate, and scheduled
renewal cannot be proven by static/local validation and remain deployment checks.

References: [Traefik ACME](https://doc.traefik.io/traefik/master/reference/install-configuration/tls/certificate-resolvers/acme/),
[lego Cloudflare token permissions](https://go-acme.github.io/lego/dns/cloudflare/).
