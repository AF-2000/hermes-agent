# Fork release policy

This fork publishes exactly one release artifact: the **unsigned Windows x64
bundled Sideload MSIXBundle**. It does not publish Store, ARM64, macOS, Linux,
ZIP, or EXE release assets.

## Manual upstream and release workflow

1. When an upstream update is wanted, use GitHub's **Sync fork** control to
   merge `NousResearch/hermes-agent:main` into this fork's `main`.
2. Review the sync result, then open
   **Actions → Build and publish Windows x64 sideload bundle** and run it
   manually against the `main` branch.
3. Before building, the Action runs `.fork/upstream_policy.py`. It restores
   the x64-only and explicit unsigned MSIX bundle mode. If upstream changed
   the MSIX assembly implementation beyond the known patch, the script fails
   closed rather than silently creating an incorrect bundle.
4. If the packaging policy needed repair, the Action commits that source-code
   change to `main`, then builds the resulting fork commit. It does not fetch,
   merge, or sync upstream itself.

The preflight deliberately does not scan unrelated workflow files for
release-related names or helper-module references. Upstream smoke/test
workflows may use `scripts.releases.*` without publishing a GitHub Release,
and disabling a workflow does not remove its YAML file. The publishing
workflow is manually dispatched and uses a commit-specific tag; its own
concurrency group serializes its runs. No historical Release or tag is
deleted or modified.

No scheduled sync, automatic release, personal access token, Azure Trusted
Signing configuration, or GitHub Actions OIDC permission is required. The
workflow uses the built-in `GITHUB_TOKEN` with `contents: write` to commit
the packaging-policy repair and publish the Release.

## Artifact and integrity

The workflow creates one x64-only MSIXBundle and does not sign it. It computes
the original bundle's SHA-256 and places the full value in the GitHub Release
description. It also creates uncompressed 7-Zip split volumes
(`.7z.001`, `.7z.002`, ...), each capped at 1900 MiB, and publishes
`SHA256SUMS.txt` containing the SHA-256 of every volume.

The MSIXBundle is already compressed, so 7-Zip uses store mode (`-mx=0`) to
avoid ineffective recompression. Download every volume and the checksum file
into the same directory. Verify the volumes against `SHA256SUMS.txt`, then
open/extract the first volume (`.7z.001`) with 7-Zip. This reconstructs the
original `.msixbundle`, whose SHA-256 should match the value in the Release
description.

Because the bundle is unsigned, Windows will not treat it as trusted for
installation by default. Apply your own signing certificate and trust policy
before deployment if your sideload environment requires a signed MSIX.

The release tag is tied to the exact build commit:
`sideload-win-x64-<first-12-commit-sha>`. Re-running the workflow for the
same commit replaces only the assets on that commit-specific Release; it does
not delete other Releases or tags.
