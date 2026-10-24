# Security review

## Accepted exposure

Infrastructure services that must operate independently of Traefik retain their
direct host port mappings. Restrict those ports at the host or router firewall
to the minimum required source VLANs and WireGuard subnet. In particular,
review PostgreSQL, Vault, qBittorrent, LDAP/Kerberos, SMB/NFS, and
Proton Mail Bridge; do not rely on Traefik middleware to protect them.

Apply equivalent IPv4 and IPv6 rules and verify them from an untrusted VLAN.

## Traefik networks

Each application stack owns a named `<stack>_traefik` ingress network. Traefik
joins these networks as external networks; backends from different stacks no
longer share an ingress bridge. Every ingress network enables IPv4 and IPv6.
The infrastructure Compose project uses `infra_traefik` for IPA and Wolf.

Create the application networks before starting Traefik, for example with
`docker compose create --no-build <ingress-service>` in each application stack.
Traefik does not create or remove application networks.

Only ingress-facing services join their stack's ingress network, apart from
existing stack-local workers that also use it for egress. Browser Use controller
and noVNC use `browser-use_traefik`; the browser/CDP worker and database remain
off that network because the controller trusts identity headers from reachable
peers. Send Bills scheduler retains its separate `host_egress` network.

The short-lived qBittorrent initializer joins `qbittorrent_traefik` to resolve
Traefik's network addresses and generate qBittorrent's trusted-proxy allowlist.
It exits before qBittorrent starts and exposes no listening service. Jellyfin's
persistent trusted-proxy subnet must match `jellyfin_traefik` when that network
is replaced.

This isolates direct backend access between stacks. The `secured` middleware
still permits Docker clients through Traefik; application authentication and
mTLS continue to apply where configured.

## Forwarded client addresses

Traefik receives ports 80 and 443 directly from Docker's host publishing. A
router performing ordinary NAT does not add forwarded headers or PROXY
protocol, so direct LAN, Wi-Fi, and WireGuard clients do not need to be listed
as trusted proxies. Traefik derives their address from the TCP connection and
adds the forwarding headers sent to backends itself.

`forwardedHeaders.trustedIPs` is only needed for the addresses of HTTP reverse
proxies that deliberately add `X-Forwarded-*`. `proxyProtocol.trustedIPs` is
only needed for L4 load balancers configured to emit PROXY protocol. Neither
is enabled. If an upstream proxy is added, trust only that proxy's exact
address.

## Backend TLS

Backend certificate verification is enabled globally using the host's standard
CA bundle. HTTPS backends must present a certificate whose chain and
server name Traefik can verify. Never restore a global verification bypass.

Inbound mTLS trusts only the IPA CA at `/etc/ipa/ca.crt`, keeping client
authentication restricted to infrastructure identities.

## Deferred decisions

- Traefik remains on `traefik:latest` by operator choice.
- TLS 1.3 is required for both the default and mTLS profiles.
- Direct infrastructure port mappings remain by operator choice and require
  firewall enforcement.
