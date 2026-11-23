#!/usr/bin/env python3
"""Re-apply fork-only release and x64 MSIX policy after a manual upstream sync.

This script is run by the manually dispatched release workflow. It never
fetches or merges upstream; it only restores the fork's packaging policy on
the already-synced main branch.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
KEEP_WORKFLOWS = {"publish-windows-x64-sideload.yml"}

PUBLISH_MARKERS = (
    re.compile(r"\bgh\s+release\s+(?:create|upload|delete)\b", re.I),
    re.compile(r"softprops/action-gh-release", re.I),
    re.compile(r"actions/create-release", re.I),
    re.compile(r"scripts\.releases\.(?:sequencer|stable|channel_publish)", re.I),
    re.compile(r"desktop-bundled-release\.yml", re.I),
)

ARGUMENTS_BEFORE = """  variant: { type: 'string' }, 'no-upload': { type: 'boolean' }, candidate: { type: 'boolean' },
"""
ARGUMENTS_AFTER = """  variant: { type: 'string' }, arch: { type: 'string' }, 'no-upload': { type: 'boolean' }, unsigned: { type: 'boolean' }, candidate: { type: 'boolean' },
"""

BUNDLE_PATTERN = re.compile(
    r"const x64 = msixFile\('x64'\)\n"
    r"const arm64 = msixFile\('arm64'\)\n"
    r"const bundle = bundleFile\(\)\n"
    r"if \(!fs\.existsSync\(x64\) \|\| !fs\.existsSync\(arm64\)\) \{\n"
    r".*?\n"
    r"\}\n\n"
    r"// makeappx bundle /d includes EVERY \.msix in the dir.*?\n"
    r"fs\.copyFileSync\(arm64, path\.join\(bundleStaging, path\.basename\(arm64\)\)\)\n",
    re.S,
)

BUNDLE_AFTER = """const arch = values.arch || 'x64'
if (arch !== 'x64') {
  throw new Error('--arch must be x64 in this fork; received ' + arch)
}
const packages = [msixFile('x64')]
const bundle = bundleFile()
const missing = packages.filter(file => !fs.existsSync(file))
if (missing.length) {
  console.error('[stage-msixbundle] missing package(s) for ' + arch + ' bundle:\\n  ' + missing.join('\\n  '))
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

def find_competing_release_workflows() -> list[str]:
    competing: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.y*ml")):
        if path.name in KEEP_WORKFLOWS:
            continue
        content = path.read_text(encoding="utf-8")
        named_release_workflow = "release" in path.stem.lower()
        publishes_release = any(pattern.search(content) for pattern in PUBLISH_MARKERS)
        if named_release_workflow or publishes_release:
            competing.append(path.relative_to(ROOT).as_posix())
    return competing


def enforce_x64_bundle() -> bool:
    path = ROOT / "scripts" / "stage-msixbundle.mjs"
    source = path.read_text(encoding="utf-8")
    changed = False

    if "arch: { type: 'string' }" not in source:
        if source.count(ARGUMENTS_BEFORE) != 1:
            raise RuntimeError(
                "Upstream changed stage-msixbundle.mjs argument declarations; "
                "refusing to continue until the x64 policy patch is reviewed."
            )
        source = source.replace(ARGUMENTS_BEFORE, ARGUMENTS_AFTER, 1)
        changed = True

    if "unsigned: { type: 'boolean' }" not in source:
        source = source.replace(
            "'no-upload': { type: 'boolean' }, candidate:",
            "'no-upload': { type: 'boolean' }, unsigned: { type: 'boolean' }, candidate:",
            1,
        )
        if "unsigned: { type: 'boolean' }" not in source:
            raise RuntimeError("Could not restore the explicit unsigned mode.")
        changed = True

    marker = "const packages = [msixFile('x64')]"
    if marker not in source:
        matches = list(BUNDLE_PATTERN.finditer(source))
        if len(matches) != 1:
            raise RuntimeError(
                "Upstream changed the MSIX bundle assembly block; "
                "refusing to continue until the x64 policy patch is reviewed."
            )
        source = BUNDLE_PATTERN.sub(lambda _: BUNDLE_AFTER, source, count=1)
        changed = True

    if "values.unsigned !== true" not in source:
        old = "const signing = Boolean(process.env.AZURE_SIGN_ENDPOINT && process.env.AZURE_SIGN_ACCOUNT && process.env.AZURE_SIGN_PROFILE)"
        new = "const signing = values.unsigned !== true && Boolean(process.env.AZURE_SIGN_ENDPOINT && process.env.AZURE_SIGN_ACCOUNT && process.env.AZURE_SIGN_PROFILE)"
        if old not in source:
            raise RuntimeError("Could not restore explicit unsigned MSIX bundle mode.")
        source = source.replace(old, new, 1)
        changed = True

    if changed:
        path.write_text(source, encoding="utf-8", newline="\n")
    return changed


def validate_release_workflow() -> None:
    path = WORKFLOWS / "publish-windows-x64-sideload.yml"
    if not path.is_file():
        raise RuntimeError("Fork-owned manual release workflow is missing.")
    source = path.read_text(encoding="utf-8")
    required = (
        "name: Build and publish Windows x64 sideload bundle",
        "workflow_dispatch:",
        "scripts/stage-msixbundle.mjs",
        "--arch x64 --unsigned",
        "-v1900m",
        "SHA256SUMS.txt",
        "gh release create",
        "gh release upload",
    )
    missing = [marker for marker in required if marker not in source]
    if missing:
        raise RuntimeError(
            "The fork-owned manual release workflow changed unexpectedly; "
            "refusing to continue: " + ", ".join(missing)
        )


def main() -> None:
    validate_release_workflow()
    competing = find_competing_release_workflows()
    if competing:
        raise RuntimeError(
            "Upstream release-publishing workflows were found. Disable or delete "
            "these workflows manually before dispatching this build: "
            + ", ".join(competing)
        )
    patched = enforce_x64_bundle()
    print("enforced x64-only unsigned MSIX bundle mode" if patched else
          "x64-only unsigned MSIX bundle mode already present")


if __name__ == "__main__":
    main()
