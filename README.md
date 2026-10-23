# best-agent distributions

Standalone CLI/TUI binaries for macOS, Linux (glibc), and Windows, on ARM64 and x64.
Download an archive from [Releases](https://github.com/Simon-He95/best-agent-releases/releases), verify it against `SHA256SUMS`, extract it, then run `install.sh` (macOS/Linux) or `install.ps1` (Windows). Node.js and npm are not needed to install or run these archives. Each archive includes installation instructions.

Releases are published only after all six native runners pass installation with Node absent and unusable, real PTY/ConPTY TUI interaction, native dependency checks, and CPU supervisor checks. `acceptance.json` identifies the source commit and checked targets. Seven npm tarballs are attached for later registry publication; this workflow never publishes to npm.

This repository contains distribution tooling and final artifacts. Application source remains private. A binary distribution is not a guarantee against reverse engineering.

## Maintainers

Run `pnpm distribute:cli` from a clean source checkout. It pushes the source commit, synchronizes only the public tooling and `build-request.json`, and pushes this repository to trigger CI. Watch the Actions run for completion. A failed target leaves an unpublished draft.

Only trusted pushes to `main` and manual runs on `main` can build. CI uses a read-only source deploy key. Raw build output and validation metadata are encrypted with AES-256-GCM; encrypted staging assets are removed before a successful Release is published. No source checkout, source maps, raw logs or internal build reports are uploaded as public release assets. The embedded JavaScript inside a SEA is still part of the distributed program.
