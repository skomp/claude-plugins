#!/usr/bin/env python3
"""Generate the Codex and GitHub Copilot CLI manifests from the Claude Code ones.

The Claude Code manifests are the source of truth:

  .claude-plugin/marketplace.json            the marketplace
  plugins/<name>/.claude-plugin/plugin.json  each plugin

From them this script writes:

  .agents/plugins/marketplace.json           Codex marketplace
  .github/plugin/marketplace.json            Copilot CLI marketplace
  plugins/<name>/.codex-plugin/plugin.json   Codex plugin manifest

Copilot CLI reads each plugin's .claude-plugin/plugin.json directly, so it needs
no plugin manifest of its own.

Plugins named in CLAUDE_ONLY are left out of both generated marketplaces: they
depend on Claude Code features (output styles, hooks) the other tools lack.

Usage:
  scripts/sync-manifests.py           write the generated files
  scripts/sync-manifests.py --check   exit 1 if any generated file is stale
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_ONLY = {"tone-roulette"}

# Codex shows plugins grouped by category; map the Claude Code categories onto its labels.
CODEX_CATEGORY = {
    "development": "Developer Tools",
    "productivity": "Productivity",
}


def load(path):
    return json.loads((ROOT / path).read_text())


def render(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def generate():
    """Return {relative path: file content} for every generated file."""
    market = load(".claude-plugin/marketplace.json")
    entries = [p for p in market["plugins"] if p["name"] not in CLAUDE_ONLY]
    out = {}

    copilot = {
        "name": market["name"],
        "owner": market["owner"],
        "metadata": {"description": market["description"]},
        "plugins": [
            {k: p[k] for k in ("name", "source", "version", "category", "description", "author") if k in p}
            for p in entries
        ],
    }
    out[".github/plugin/marketplace.json"] = render(copilot)

    codex = {
        "name": market["name"],
        "interface": {"displayName": "skomp plugins"},
        "plugins": [
            {
                "name": p["name"],
                "source": {"source": "local", "path": p["source"]},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": CODEX_CATEGORY.get(p.get("category"), "Developer Tools"),
            }
            for p in entries
        ],
    }
    out[".agents/plugins/marketplace.json"] = render(codex)

    for p in entries:
        plugin_dir = Path(p["source"])
        manifest = load(plugin_dir / ".claude-plugin/plugin.json")
        if manifest["version"] != p["version"]:
            sys.exit(f"{p['name']}: marketplace version {p['version']} differs from plugin.json {manifest['version']}")
        codex_manifest = {
            k: manifest[k]
            for k in ("name", "version", "description", "author", "homepage", "repository", "license", "keywords")
            if k in manifest
        }
        if (ROOT / plugin_dir / "skills").is_dir():
            codex_manifest["skills"] = "./skills/"
        out[str(plugin_dir / ".codex-plugin/plugin.json")] = render(codex_manifest)

    return out


def main():
    check = sys.argv[1:] == ["--check"]
    stale = []
    for rel, content in generate().items():
        path = ROOT / rel
        current = path.read_text() if path.exists() else None
        if current == content:
            continue
        if check:
            stale.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            print(f"wrote {rel}")
    if stale:
        print("stale, run scripts/sync-manifests.py:\n  " + "\n  ".join(stale))
        sys.exit(1)


if __name__ == "__main__":
    main()
