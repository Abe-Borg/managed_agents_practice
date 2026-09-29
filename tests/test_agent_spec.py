from __future__ import annotations

from csv_analyst.agent_spec import (
    build_agent_spec,
    build_environment_spec,
    config_hash,
)
from csv_analyst.config import load_settings


def test_config_hash_ignores_dictionary_key_order() -> None:
    left = {"name": "csv-analyst", "nested": {"enabled": True, "tools": ["bash"]}}
    right = {"nested": {"tools": ["bash"], "enabled": True}, "name": "csv-analyst"}
    assert config_hash(left) == config_hash(right)


def test_agent_spec_restricts_tools_and_does_not_set_haiku_effort() -> None:
    spec = build_agent_spec(load_settings(env={}, dotenv_path=None))
    assert spec.model == "claude-haiku-4-5"
    assert spec.skills == []
    toolset = spec.tools[0]
    assert toolset["type"] == "agent_toolset_20260401"
    assert toolset["default_config"] == {"enabled": False}
    assert toolset["configs"] == [
        {"name": name, "enabled": True}
        for name in ("bash", "read", "write", "edit", "glob", "grep")
    ]


def test_environment_spec_has_no_outbound_hosts_or_package_installs() -> None:
    spec = build_environment_spec()
    assert spec.config == {
        "type": "cloud",
        "networking": {
            "type": "limited",
            "allowed_hosts": [],
            "allow_package_managers": False,
            "allow_mcp_servers": False,
        },
    }
