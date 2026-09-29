from __future__ import annotations

import re
import shutil
from pathlib import Path

from csv_analyst.agent_spec import build_agent_spec
from csv_analyst.config import load_settings
from csv_analyst.resources import ensure_skill, load_state
from tests.fakes import FakePlatform

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "csv-report"


def test_skill_frontmatter_and_instructions() -> None:
    lines = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    fields = dict(line.split(": ", 1) for line in lines[1:end])
    name = fields["name"]
    description = fields["description"]
    assert re.fullmatch(r"[a-z0-9-]{1,64}", name)
    assert "anthropic" not in name and "claude" not in name
    assert 0 < len(description) <= 1024
    assert "<" not in description and ">" not in description
    body = "\n".join(lines[end + 1 :])
    for section in ("Overview", "Data quality", "Key findings", "Charts", "Caveats", "Reproduce"):
        assert section in body
    assert "scripts/profile_csv.py <csv>" in body


def test_ensure_skill_reuses_then_versions_changed_bundle(tmp_path: Path) -> None:
    directory = tmp_path / "csv-report"
    shutil.copytree(SKILL_DIR, directory)
    state_path = tmp_path / "state.json"
    platform = FakePlatform()

    first = ensure_skill(platform, directory, state_path)
    second = ensure_skill(platform, directory, state_path)
    with (directory / "SKILL.md").open("a", encoding="utf-8") as stream:
        stream.write("\nExtra chart guidance.\n")
    changed = ensure_skill(platform, directory, state_path)

    assert (first.action, second.action, changed.action) == (
        "created",
        "unchanged",
        "updated",
    )
    assert first.resource.id == second.resource.id == changed.resource.id
    assert changed.resource.latest_version_id != first.resource.latest_version_id
    assert platform.skill_creates == 1
    assert platform.skill_version_creates == 1
    assert load_state(state_path).skill_version == changed.resource.latest_version_id


def test_agent_spec_attaches_custom_skill() -> None:
    settings = load_settings(env={}, dotenv_path=None)
    spec = build_agent_spec(settings, skill_id="skill_123")
    assert spec.skills == [
        {"type": "custom", "skill_id": "skill_123", "version": "latest"}
    ]
