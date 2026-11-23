#!/usr/bin/env python3
"""Re-apply fork-only Windows x64 sideload policy after every upstream merge.

This script deliberately fails closed if upstream changes the MSIX bundler
around the patch point. The sync workflow must not push a merge that silently
restores the universal x64+ARM64 bundle requirement.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
KEEP_WORKFLOWS = {"sync-upstream-sideload.yml"}

PUBLISH_MARKERS = (
    re.compile(r"\bgh\s+release\s+(?:create|upload|delete)\b", re.I),
    re.compile(r"softprops/action-gh-release", re.I),
    re.compile(r"actions/create-release", re.I),
    re.compile(r"scripts\.releases\.(?:sequencer|stable|channel_publish)", re.I),
    re.compile(r"desktop-bundled-release\.yml", re.I),
)

ARGUMENTS_BEFORE = """  variant: { type: 'string' }, 'no-upload': { type: 'boolean' }, candidate: { type: 'boolean' },
"""
ARGUMENTS_AFTER = """  variant: { type: 'string' }, arch: { type: 'string' }, 'no-upload': { type: 'boolean' }, candidate: { type: 'boolean' },
"""

BUNDLE_BEFORE = """const x64 = msixFile('x64')
const arm64 = msixFile('arm64')
const bundle = bundleFile()
if (!fs.existsSync(x64) || !fs.existsSync(arm64)) {
  console.error(\`[stage-msixbundle] need both per-arch msix to bundle:\\n  \${x64}\\n  \${arm64}\`)
  process.exit(1)
}

// makeappx bundle /d includes EVERY .msix in the dir — the Store-submission
// packages (Store-*.msix, same release dir after the legs merged their
// artifacts) must never ride inside the out-of-store bundle. Stage only the
// two per-arch packages into a clean dir before bundling.
const bundleStaging = path.join(releaseDir, '__bundle-staging')
fs.rmSync(bundleStaging, { recursive: true, force: true })
fs.mkdirSync(bundleStaging, { recursive: true })
fs.copyFileSync(x64, path.join(bundleStaging, path.basename(x64)))
fs.copyFileSync(arm64, path.join(bundleStaging, path.basename(arm64)))
"""

BUNDLE_AFTER = """const arch = values.arch || 'universal'
if (!['universal', 'x64'].includes(arch)) {
  throw new Error(\`--arch must be 'universal' or 'x64', got '\${arch}'\`)
}
const bundleArchs = arch === 'x64' ? ['x64'] : ['x64', 'arm64']
const packages = bundleArchs.map(msixFile)
const bundle = bundleFile()
const missing = packages.filter(file => !fs.existsSync(file))
if (missing.length) {
  console.error(\`[stage-msixbundle] missing package(s) for \${arch} bundle:\\n  \${missing.join('\\n  ')}\`)
  process.exit(1)
}

// Stage only the selected architecture packages. This prevents ARM64 or
// Store packages from entering the fork's x64-only sideload bundle.
const bundleStaging = path.join(releaseDir, '__bundle-staging')
fs.rmSync(bundleStaging, { recursive: true, force: true })
fs.mkdirSync(bundleStaging, { recursive: true })
for (const file of packages) {
  fs.copyFileSync(file, path.join(bundleStaging, path.basename(file)))
}
"""

def prune_release_workflows() -> list[str]:
    removed: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        if path.name in KEEP_WORKFLOWS:
            continue
        content = path.read_text(encoding="utf-8")
        named_release_workflow = "release" in path.stem.lower()
        publishes_release = any(pattern.search(content) for pattern in PUBLISH_MARKERS)
        if named_release_workflow or publishes_release:
            path.unlink()
            removed.append(path.relative_to(ROOT).as_posix())
    return removed


def enforce_x64_bundle() -> bool:
    path = ROOT / "scripts" / "stage-msixbundle.mjs"
    source = path.read_text(encoding="utf-8")
    changed = False

    if "arch: { type: 'string' }" not in source:
        if source.count(ARGUMENTS_BEFORE) != 1:
            raise RuntimeError(
                "Upstream changed stage-msixbundle.mjs argument declarations; "
                "refusing to sync until the x64 policy patch is reviewed."
            )
        source = source.replace(ARGUMENTS_BEFORE, ARGUMENTS_AFTER, 1)
        changed = True

    if "const bundleArchs = arch === 'x64' ? ['x64'] : ['x64', 'arm64']" not in source:
        if source.count(BUNDLE_BEFORE) != 1:
            raise RuntimeError(
                "Upstream changed the MSIX bundle assembly block; "
                "refusing to sync until the x64 policy patch is reviewed."
            )
        source = source.replace(BUNDLE_BEFORE, BUNDLE_AFTER, 1)
        changed = True

    if changed:
        path.write_text(source, encoding="utf-8", newline="\n")
    return changed


def main() -> None:
    removed = prune_release_workflows()
    patched = enforce_x64_bundle()
    for item in removed:
        print(f"removed upstream release workflow: {item}")
    print("enforced x64-only MSIX bundle mode" if patched else "x64-only MSIX bundle mode already present")


if __name__ == "__main__":
    main()
