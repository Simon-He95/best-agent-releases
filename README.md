# best-agent distributions

Standalone CLI/TUI binaries for macOS, Linux (glibc), and Windows, on ARM64 and x64.
Download an archive from [Releases](https://github.com/Simon-He95/best-agent-releases/releases), verify it against `SHA256SUMS`, extract it, then run `install.sh` (macOS/Linux) or `install.ps1` (Windows). Node.js and npm are not needed to install or run these archives. Each archive includes installation instructions.

Releases are published only after all six native runners pass installation with Node absent and unusable, real PTY/ConPTY TUI interaction, native dependency checks, and CPU supervisor checks. `acceptance.json` identifies the source commit and checked targets. Seven npm tarballs are attached for later registry publication; this workflow never publishes to npm.

This repository contains distribution tooling and final artifacts. Application source remains private. A binary distribution is not a guarantee against reverse engineering.

## Maintainers

`native-read-helper.yml` is a manual, verification-only six-platform build. Supply an exact private `source_sha` and matching CLI `version`. It writes requests only inside each runner checkout, leaves the tracked public build request unchanged, uses the exact private candidate's build driver with encrypted diagnostics, and keeps the resulting Release draft. It never invokes npm publication or the normal distribution publication step. POSIX runners additionally assert native helper execution, source errors and permission denial in the installed standalone CLI; Windows retains its unsupported sandbox filesystem behavior. A successful verification is evidence for the private integration, not a product default switch.

For a full release, run `pnpm release:tui [version]` from the private source repository's clean `main` checkout. Omitting the version opens the bumpp version selector using the current remote-synchronized CLI version; choosing a version continues the release and cancelling stops it. The selector does not modify files. It fast-forwards main, commits the CLI version, calls `distribute:cli`, waits for the exact six-platform build, then dispatches this repository's existing `publish.yml` and waits until npm versions pass visibility, integrity and channel checks. Prerelease versions use `beta`; stable versions use `latest`. Use `pnpm release:tui [version] --dry-run` to print the plan without changing the version, committing, pushing or dispatching any workflow. Keep the command running between phases. It requires authenticated GitHub CLI 2.92+ and the existing seven trusted publisher connections, with no local npm login or token. A failed step stops the chain. After interruption, let an already-running CI finish before retrying. When main still points at the same release commit, rerunning with the same explicit version reuses an accepted Release without another version bump or native rebuild; if main has advanced, recover the original Release through `publish.yml` rather than reusing its npm version for different source.

Run `pnpm distribute:cli` from a clean source checkout. It pushes the source commit, synchronizes only the public tooling and `build-request.json`, and pushes this repository to trigger CI. Watch the Actions run for completion. A failed target leaves an unpublished draft.

Only trusted pushes to `main` and manual runs on `main` can build. CI uses a read-only source deploy key. Raw build output and validation metadata are encrypted with AES-256-GCM; encrypted staging assets are removed before a successful Release is published. No source checkout, source maps, raw logs or internal build reports are uploaded as public release assets. The embedded JavaScript inside a SEA is still part of the distributed program.

## Manual npm publication

`publish.yml` has only a manual trigger and defaults to `dry_run=true`. It accepts an existing Release tag, never builds application source, and needs no source deploy key or build encryption key. Before any npm write it verifies the published Release's exact assets and GitHub digests, the historical source request, a successful trusted `build.yml` run with all six native jobs and distribution successful, all six acceptance records, checksums, package identities, and the launcher's exact six platform dependencies. A draft, failed build, missing target, altered bytes, or conflicting registry version blocks publication.

After `pnpm distribute:cli` and a successful build, preview the selected Release (replace the example tag with the actual tag):

```sh
gh workflow run publish.yml --repo Simon-He95/best-agent-releases --ref main \
  -f release_tag=cli-v0.0.17-beta.1-0123456789ab -f npm_tag=beta -f dry_run=true
gh run watch --repo Simon-He95/best-agent-releases --exit-status
```

Only when ready to publish, run the same command with `-f dry_run=false`. Six platform packages publish first; the launcher publishes last. All seven package versions are preflighted before the first write. After an interrupted publish, rerun with the same Release and channel: only byte-identical existing versions already on that channel are skipped. Conflicting bytes or a different existing dist-tag fail before publication; dist-tag promotion is a separate explicit npm operation. Use `npm_tag=latest` only for a stable version without a prerelease suffix.

npm [scans new uploads before making them installable](https://github.blog/changelog/2026-07-28-npm-publish-time-malware-scanning-and-dual-use-metadata/). A successful `npm publish` response can precede registry visibility by several minutes. The workflow waits for all six platform versions, matching tarball integrity and channel, before publishing the launcher, then waits for the launcher too. These waits share a 45-minute deadline; the job has a 60-minute timeout. A retry returning `E409` for the same previously staged version enters the same visibility and integrity checks; it never counts as proof of successful publication on its own. Dry runs perform no availability wait. A timeout leaves the accepted uploads intact and reports the pending packages; it does not approve/reject staged packages or bypass npm scanning.

### npm permissions

Use [npm Trusted Publishing](https://docs.npmjs.com/trusted-publishers/) rather than adding an npm token to this repository. On npmjs.com, open each package's **Settings → Trusted publishing → GitHub Actions** and configure:

| Field                | Value                                                                                         |
| -------------------- | --------------------------------------------------------------------------------------------- |
| Organization or user | `Simon-He95`                                                                                  |
| Repository           | `best-agent-releases`                                                                         |
| Workflow filename    | `publish.yml` (without `.github/workflows/`)                                                  |
| Environment name     | Leave empty; the workflow does not declare an environment                                     |
| Allowed actions      | Enable direct `npm publish`; this workflow does not use `npm stage publish` or `npm dist-tag` |

Apply this to all seven packages:

- `@best-agent/cli`
- `@best-agent/cli-darwin-arm64`
- `@best-agent/cli-darwin-x64`
- `@best-agent/cli-linux-arm64-gnu`
- `@best-agent/cli-linux-x64-gnu`
- `@best-agent/cli-win32-arm64`
- `@best-agent/cli-win32-x64`

The workflow uses GitHub-hosted runners, Node 24.15.0, npm 11.21.1, and `id-token: write`. Generated packages identify this public distribution repository for OIDC/provenance; older Release tarballs without that metadata are rejected and must not be silently repacked. Build a new source commit to obtain compatible tarballs.

An npm account with package administration rights must configure each trusted publisher. Newly configured trusted publishers must complete a successful publication within two days or be recreated; a dry run does not validate the connection. Configure authorization close to the intended real publication date.

Alternatively, with npm 11.21.1 and a logged-in maintainer account, configure all seven existing packages from the terminal (this changes permissions, not package versions):

```sh
npm login --registry=https://registry.npmjs.org
for package in \
  @best-agent/cli \
  @best-agent/cli-darwin-arm64 \
  @best-agent/cli-darwin-x64 \
  @best-agent/cli-linux-arm64-gnu \
  @best-agent/cli-linux-x64-gnu \
  @best-agent/cli-win32-arm64 \
  @best-agent/cli-win32-x64
do
  npm trust github "$package" --repo Simon-He95/best-agent-releases \
    --file publish.yml --allow-publish --yes --registry=https://registry.npmjs.org || break
  sleep 2
done
```

Complete npm's 2FA prompts. Existing trusted publisher settings should be inspected before adding this connection; do not revoke other publishers as part of this setup.
