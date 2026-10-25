"""Offline integration check invoked by acme.sh inside disposable containers."""

import base64
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import time
import urllib.request

root = Path("/test")
repo = Path("/repo")

if sys.argv[1] == "prepare":
    static = (repo / "data/traefik.yml").read_text()
    dynamic = (repo / "data/config.yml").read_text()
    assert "keyType: EC256" in static
    assert "provider: cloudflare" in static
    assert "disableANSChecks: true" in static
    assert "requireAllRNS: true" in static
    assert '"1.1.1.1:53"' in static and '"8.8.8.8:53"' in static
    assert "certResolver: cloudflare" in dynamic
    assert "- authelia@docker" in dynamic
    assert "- secured" in dynamic
    assert "minVersion: VersionTLS13" in dynamic
    assert "clientAuthType: RequireAndVerifyClientCert" in dynamic
    assert "defaultCertificate:" in dynamic
    # Only the isolated fixture exposes the API and substitutes external services.
    static = static.replace("insecure: false", "insecure: true")
    static = static.replace(
        '  docker:\n    endpoint: "unix:///var/run/docker.sock"\n    exposedByDefault: false\n',
        "",
    )
    static = static.replace("/etc/traefik", "/test/dynamic")
    static = static.replace("/var/lib/traefik/acme.json", "/test/acme.json")
    (root / "dynamic/certs").mkdir(parents=True)
    (root / "traefik.yml").write_text(static)
    dynamic = dynamic.replace("/etc/traefik", "/test/dynamic")
    dynamic = dynamic.replace(
        "/etc/ipa/ca.crt", "/test/dynamic/certs/atlas_fullchain.pem"
    )
    dynamic = dynamic.replace("authelia@docker", "security-headers@file")
    for variable in (
        "LAN_SUBNET",
        "TRUSTED_WIFI_SUBNET",
        "CORTEX_SUBNET",
        "WG_SUBNET",
        "IPV6_LAN_SUBNET",
        "IPV6_TRUSTED_WIFI_SUBNET",
        "IPV6_CORTEX_SUBNET",
        "IPV6_WG_SUBNET",
    ):
        dynamic = dynamic.replace('{{ env "' + variable + '" }}', "127.0.0.0/8")
    (root / "dynamic/config.yml").write_text(dynamic)
    (root / "dynamic/unifi.yml").write_text((repo / "data/unifi.yml").read_text())
    for name, domains in [
        ("atlas", ["vault.home.arpa"]),
        ("acme", ["atlas.intranet.enucatl.com", "*.atlas.intranet.enucatl.com"]),
    ]:
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "ec",
                "-pkeyopt",
                "ec_paramgen_curve:P-256",
                "-nodes",
                "-days",
                "90",
                "-subj",
                "/CN=" + domains[0],
                "-addext",
                "subjectAltName=" + ",".join("DNS:" + d for d in domains),
                "-keyout",
                str(root / f"dynamic/certs/{name}_key.pem"),
                "-out",
                str(root / f"dynamic/certs/{name}_fullchain.pem"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    state = {
        "cloudflare": {
            "Certificates": [
                {
                    "domain": {
                        "main": "atlas.intranet.enucatl.com",
                        "sans": ["*.atlas.intranet.enucatl.com"],
                    },
                    "certificate": base64.b64encode(
                        (root / "dynamic/certs/acme_fullchain.pem").read_bytes()
                    ).decode(),
                    "key": base64.b64encode(
                        (root / "dynamic/certs/acme_key.pem").read_bytes()
                    ).decode(),
                    "Store": "default",
                }
            ]
        }
    }
    (root / "acme.json").write_text(json.dumps(state))
    os.chmod(root / "acme.json", 0o600)
    (root / "cloudflare-token").write_text("offline-test")
    os.chmod(root / "cloudflare-token", 0o400)
    for path in [root, *root.rglob("*")]:
        os.chown(path, 1000, 1000)
else:
    for attempt in range(100):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8080/api/rawdata", timeout=1
            ) as response:
                raw = json.load(response)
            if "traefik@file" in raw.get("routers", {}):
                break
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    else:
        raise AssertionError("Traefik API did not become ready")
    assert not raw.get("errors"), raw.get("errors")
    assert raw["routers"]["traefik@file"]["status"] == "enabled", raw
    tls = raw["routers"]["traefik@file"]["tls"]
    assert tls["certResolver"] == "cloudflare", tls
    assert tls["domains"] == [
        {"main": "atlas.intranet.enucatl.com", "sans": ["*.atlas.intranet.enucatl.com"]}
    ], tls
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    for hostname, fixture in [
        ("atlas.intranet.enucatl.com", "acme"),
        ("traefik.atlas.intranet.enucatl.com", "acme"),
        ("traefik.atlas.home.arpa", "atlas"),
        ("unknown.example", "atlas"),
        ("deep.traefik.atlas.intranet.enucatl.com", "atlas"),
    ]:
        with socket.create_connection(("127.0.0.1", 443)) as connection:
            with context.wrap_socket(connection, server_hostname=hostname) as secure:
                expected = ssl.PEM_cert_to_DER_cert(
                    (root / f"dynamic/certs/{fixture}_fullchain.pem").read_text()
                )
                assert secure.getpeercert(binary_form=True) == expected, hostname
    print(
        "PASS: router enabled, Cloudflare resolver/domain selection, exact/wildcard SNI, Vault fallback"
    )
