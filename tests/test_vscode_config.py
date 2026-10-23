"""The shipped VS Code configuration must point at things that exist."""
import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VSCODE = ROOT / ".vscode"


def load(name):
    return json.loads((VSCODE / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["launch.json", "tasks.json", "settings.json", "extensions.json"])
def test_files_are_valid_json(name):
    assert load(name)


def test_launch_targets_exist():
    launch = load("launch.json")
    inputs = {i["id"] for i in launch.get("inputs", [])}
    for cfg in launch["configurations"]:
        if "program" in cfg and cfg["program"] != "${file}":
            assert (ROOT / cfg["program"].replace("${workspaceFolder}/", "")).is_file(), cfg["name"]
        if "module" in cfg:
            assert importlib.util.find_spec(cfg["module"].split(".")[0]) is not None, cfg["name"]
            if cfg["module"].startswith("backend"):
                assert importlib.util.find_spec(cfg["module"]) is not None, cfg["name"]
        for arg in cfg.get("args", []):
            for used in re.findall(r"\$\{input:(\w+)\}", arg):
                assert used in inputs, f"{cfg['name']}: undefined input {used}"
    # The app serves the whole Kalakriti site (including the chatbot) from "/" -
    # backend/main.py mounts the frontend at the root, there is no separate
    # "/assistant/" route - so the launch config should just open the root.
    assert launch["configurations"][0]["serverReadyAction"]["uriFormat"].endswith("/")


def test_tasks_reference_existing_scripts():
    for task in load("tasks.json")["tasks"]:
        for script in re.findall(r"((?:scripts|evaluation)/[\w./-]+\.(?:py|sh))", task["command"]):
            assert (ROOT / script).is_file(), f"{task['label']}: {script}"


def test_gitignore_keeps_vscode_files_but_not_others():
    text = (ROOT / ".gitignore").read_text()
    for keep in ("launch.json", "tasks.json", "settings.json", "extensions.json"):
        assert f"!.vscode/{keep}" in text


def test_bootstrap_script_is_executable_and_strict():
    script = ROOT / "scripts" / "bootstrap.sh"
    assert script.stat().st_mode & 0o111 and "set -euo pipefail" in script.read_text()
