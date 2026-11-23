# Fork release policy

This fork intentionally publishes one artifact only: the Windows x64 bundled
Sideload MSIXBundle. It does not publish Store, ARM64, macOS, Linux, ZIP, or
EXE release assets.

## Upstream synchronization

`.github/workflows/sync-upstream-sideload.yml` merges
`NousResearch/hermes-agent:main` into this fork's `main`. After every merge,
it runs `upstream_policy.py` before pushing:

- removes upstream workflow files whose names identify release publishing,
  plus workflows that directly invoke known release publishers;
- reapplies the fork's `--arch x64` support to
  `scripts/stage-msixbundle.mjs`;
- fails the sync if upstream changes the MSIX assembly code so the patch can
  no longer be applied safely.

The sync merge prefers upstream on overlapping source changes. Fork policy is
then re-applied and committed as a separate sync commit. The desktop build uses
that resulting fork commit, not the upstream SHA, so the policy patch is part
of the packaged source.

If upstream substantially redesigns MSIX assembly, the policy step deliberately
fails before pushing. Update the patch in `upstream_policy.py` and retest it
before resuming scheduled syncs.

## Required GitHub configuration

1. Add repository secret `SYNC_PAT`. It must be a fine-grained PAT with
   Contents: Read and write and Workflows: Read and write. The sync job uses it
   to push upstream merges and workflow-file deletions to `main`.
2. Configure the `release-signing` environment with these repository
   variables:
   - `AZURE_SIGN_ENDPOINT`
   - `AZURE_SIGN_ACCOUNT`
   - `AZURE_SIGN_PROFILE`
   - `AZURE_SIGN_PUBLISHER`
   - `AZURE_CLIENT_ID`
   - `AZURE_TENANT_ID`
3. Configure Azure federated credentials for the repository's GitHub Actions
   OIDC identity. Do not store an Azure client secret in GitHub.

The build intentionally fails rather than publishing an unsigned package when
Trusted Signing is not configured. The signed MSIXBundle is verified before
publication.

## Release identity

A release tag is derived from the exact upstream commit:
`sideload-win-x64-<first-12-upstream-sha>`. The artifact itself is built from
the fork's post-sync commit, which includes the fork policy. A normal scheduled
run skips a revision that already has a Release; manual dispatch with
`force=true` rebuilds and replaces the bundle asset for that same revision.

Each newly published Release contains the Windows x64 Sideload MSIXBundle as
uncompressed 7-Zip split volumes (`.7z.001`, `.7z.002`, ...), each capped at
1900 MiB, plus `SHA256SUMS.txt`. The MSIXBundle is already compressed, so the
7-Zip archive uses store mode (`-mx=0`) to avoid wasting CPU time and build
time on ineffective recompression.

Download every volume and the checksum file into the same directory. Verify
the volumes against `SHA256SUMS.txt`, then open/extract the first volume
(`.7z.001`) with 7-Zip; it reconstructs the original `.msixbundle`, which
can then be installed using the normal Windows sideload procedure. Do not try
to install an individual volume.

A forced rebuild removes all assets from that revision's dedicated Release
before uploading the new volume set, preventing stale extra volumes from
remaining if the rebuilt bundle is smaller. No App Installer feed, certificate,
standalone ZIP, EXE, ARM64, or Store package is uploaded.
