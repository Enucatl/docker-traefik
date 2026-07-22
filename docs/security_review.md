# Security review

## Accepted exposure

Infrastructure services that must operate independently of Traefik retain their
direct host port mappings. Restrict those ports at the host or router firewall
to the minimum required source VLANs and WireGuard subnet. In particular,
review PostgreSQL, Vault, Checkmk, qBittorrent, LDAP/Kerberos, SMB/NFS, and
Proton Mail Bridge; do not rely on Traefik middleware to protect them.

Apply equivalent IPv4 and IPv6 rules and verify them from an untrusted VLAN.

## Traefik network

Only Traefik and processes receiving traffic from it join `traefik_proxy`.
Worker, CLI, evaluation, and webhook processes use internal or dedicated
egress networks instead. The Send Bills scheduler uses its `host_egress`
network for SMTP access without joining the ingress network.

The short-lived qBittorrent initializer remains attached because it resolves
Traefik's Docker-network address to generate qBittorrent's trusted-proxy
allowlist. It exits before qBittorrent starts and exposes no listening service.

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

Backend certificate verification is enabled globally using the internal root
and intermediate CA. HTTPS backends must present a certificate whose chain and
server name Traefik can verify. Never restore a global verification bypass.

## Deferred decisions

- Traefik remains on `traefik:latest` by operator choice.
- TLS 1.3 is required for both the default and mTLS profiles.
- Direct infrastructure port mappings remain by operator choice and require
  firewall enforcement.
