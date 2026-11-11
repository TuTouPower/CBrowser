"""t054 AC-003/AC-004/AC-005/AC-006/AC-008/AC-009: deploy structure tests.

- Caddy HTTPS and every Stream UDP mux port bind loopback only.
- The edge network carries a fixed IPAM subnet (per-instance, derived by
  deploy.sh from the instance identity); deploy.sh injects the same
  subnet as CBROWSER_TRUSTED_PROXY_CIDRS into API and Gateway.
- The deploy fingerprint hashes the rendered Caddyfile product, never
  the generator source; deploy.sh renders it from the deployment port
  through the single ``render`` CLI entry point.

Compose is asserted on its text (PyYAML is not in the gate venv), the
same style as test_a24_deploy_network_source.py.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _compose_text() -> str:
    return (ROOT / "compose.yaml").read_text(encoding="utf-8")


def _deploy_text() -> str:
    return (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")


def _service_block(text: str, service: str, next_service: str) -> str:
    start = text.index(f"\n  {service}:")
    end = text.index(f"\n  {next_service}:", start)
    return text[start:end]


def test_caddy_port_binds_loopback_only() -> None:
    text = _compose_text()
    assert (
        '"127.0.0.1:${CBROWSER_HTTPS_PORT:?run scripts/deploy.sh first}:443"'
        in text
    )
    assert "CBROWSER_BIND_HOST" not in text


def test_edge_network_has_fixed_ipam_subnet() -> None:
    text = _compose_text()
    block = text[text.index("\nnetworks:"):]
    assert "name: ${CBROWSER_PREFIX:-cbrowser}-edge" in block
    assert "ipam:" in block
    assert "- subnet: ${CBROWSER_EDGE_SUBNET:?run scripts/deploy.sh first}" in block


def test_api_and_gateway_receive_trusted_proxy_cidrs() -> None:
    text = _compose_text()
    needle = (
        "CBROWSER_TRUSTED_PROXY_CIDRS: "
        "${CBROWSER_TRUSTED_PROXY_CIDRS:?run scripts/deploy.sh first}"
    )
    assert text.count(needle) == 2
    for service, nxt in (("api", "gateway"), ("gateway", "supervisor")):
        assert needle in _service_block(text, service, nxt), service


def test_gateway_has_no_network_state_dir() -> None:
    text = _compose_text()
    assert "CBROWSER_NETWORK_STATE_DIR" not in text
    gateway = _service_block(text, "gateway", "supervisor")
    assert "/network" not in gateway


def test_no_wildcard_bind_in_compose() -> None:
    # Only published host ports matter: Gateway/Supervisor listen on
    # 0.0.0.0 inside the container network (unpublished), which is not a
    # host bind. No published port mapping may bind a wildcard address.
    import re

    text = _compose_text()
    assert not re.search(r'^\s+- "0\.0\.0\.0:', text, re.MULTILINE)
    assert not re.search(r"^\s+- '0\.0\.0\.0:", text, re.MULTILINE)


def test_deploy_derives_default_port_from_single_constant() -> None:
    text = _deploy_text()
    assert ":-56661" not in text
    assert "DEFAULT_HTTPS_PORT" in text


def test_deploy_renders_caddyfile_and_hashes_the_product() -> None:
    text = _deploy_text()
    assert "-m cbrowser.network_config_cli" in text
    assert "render --network-dir" in text
    assert "init --network-dir" not in text
    assert "read --network-dir" not in text
    # The fingerprint is the hash of the rendered Caddyfile file, never
    # of the generator source.
    assert 'sha256_of_file "$DATA_ROOT/network/Caddyfile"' in text
    assert 'sha256_of_file "$ROOT/src/backend/cbrowser/network_config.py"' not in text


def test_deploy_derives_edge_subnet_and_trusted_cidrs() -> None:
    text = _deploy_text()
    assert "CBROWSER_EDGE_SUBNET" in text
    assert "CBROWSER_TRUSTED_PROXY_CIDRS" in text
    # The release env records the edge subnet, and the trusted proxy
    # CIDRs equal the edge subnet (same value, both names).
    assert "CBROWSER_EDGE_SUBNET=$CBROWSER_EDGE_SUBNET" in text
    assert "CBROWSER_TRUSTED_PROXY_CIDRS=$CBROWSER_EDGE_SUBNET" in text
    assert 'export CBROWSER_TRUSTED_PROXY_CIDRS="$CBROWSER_EDGE_SUBNET"' in text
    assert "CBROWSER_BIND_HOST" not in text


def test_deploy_prechecks_edge_subnet_conflicts() -> None:
    text = _deploy_text()
    assert "check_edge_subnet_conflict" in text
    # The refusal must name an actionable fix, not just fail.
    assert "CBROWSER_EDGE_SUBNET" in text


def test_env_example_documents_deploy_derived_cidrs() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "CBROWSER_TRUSTED_PROXY_CIDRS" in text
    assert "applied network version" not in text
