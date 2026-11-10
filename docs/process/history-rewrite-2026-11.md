# Repository history rewrite of 2026-11-10

The private source repository `Simon-He95/best-agent` was rewritten on 2026-11-10 before any
public release. The goal was to publish no credential and no personal or internal document in
the history, while keeping the commit record and the commit messages.

Two things changed for every existing reference:

- Every commit has a new object name (SHA), because the rewrite removed non-source paths and
  replaced two credentials.
- Every author and committer address is now `Simon He <simon@best-agent.dev>`. The former
  addresses were a personal mailbox, a GitHub noreply address and a machine-local address.

Commit messages, authors' dates, the topological order and the tree content of the remaining
files are unchanged. Seventeen commits became empty because they only touched removed paths,
so they no longer appear; the 4084-commit `main` after the rewrite contains the same source as
the 4098-commit `main` before it, apart from the deliberate changes listed below.

## Removed from the history

| Path | Reason |
| --- | --- |
| `.work/` | Company communication redesign deck and extracted images |
| `logs/` | Runtime debug logs |
| `.tmp/`, `.tmp-*` | Local debug dumps and scratch JSON |
| `v3-threads.sqlite` | Local conversation database |
| `best-agent-arch-review-*.zip` | Code review archives |
| `docs/reviews/` | Internal review records |
| `docs/benchmarks/failures/` | Benchmark failure captures with session events |
| `docs/proposals/*.json` | Internal experiment results |
| `docs/terminal-bench-repair-log.md` | Carried a live access token |

## Credentials replaced

| Credential | Where it appeared | Status |
| --- | --- | --- |
| Dim OAuth confidential client secret | `apps/cli/src/dimsdk/core/next-api-oauth.ts`, `apps/cli/src/v3-oauth-refresh.ts`, and an earlier copy under `apps/cli/src/dimsdk/compat/` | Replaced by `***REMOVED***` in every commit and read from `NEXT_API_OAUTH_CLIENT_SECRET` at run time, so the published source carries no secret |
| HuggingFace access token | `docs/terminal-bench-repair-log.md` | File removed; the value was rotated by its owner |

Both credentials were live before the rewrite, so they must be treated as disclosed. A rewrite
does not make a disclosed secret safe; the credential has to be rotated at the provider.

## Anchor commits

| Content | Commit before the rewrite | Commit after the rewrite |
| --- | --- | --- |
| `main` head, including the TUI demo video | `6f29e8abfe3163cda4daf6305a6148d38f1203a2` | `9d5725e3f373fe305ab7e1ab93c6a998e2cb6526` |
| `chore(cli): release 0.0.26` | `48d436d585202c3ddf0a2ba4d63e9c169c08acb8` | `beec1ab4c2255490046e27336ee61092559e45d9` |

The two commits that added the TUI demo video, `55e665f6df46a63fc6321744151013a26917b2b5` and
its merge `6f29e8abfe3163cda4daf6305a6148d38f1203a2`, predate the rewrite base of the local
clone. Their content is replayed as one commit on the new `main`, byte for byte identical to
the pre-rewrite tree.

## Release tags

Tags in this repository embed the source commit in their name. The table below maps each tag to
the commit that now carries the same source. All 14 tags point at commits that still exist in
the rewritten history.

| Tag | Source before | Source after |
| --- | --- | --- |
| `cli-v0.0.16-beta.1-5ad0576e451d` | `5ad0576e451d` | `220d047f074f51fdcce529b61a29049f45907485` |
| `cli-v0.0.16-beta.1-912667203eb7` | `912667203eb7` | `b40ae7bcda4e839b236feb075b7b62255feaf053` |
| `cli-v0.0.17-36b1c8583982` | `36b1c8583982` | `5ced09921de2d7b78b50150418a1c23c26f2eca5` |
| `cli-v0.0.17-beta.2-837a4c58fbcf` | `837a4c58fbcf` | `6a7660baefbe58450b127fdc41f1f38ae30e65a2` |
| `cli-v0.0.18-871cecde8b41` | `871cecde8b41` | `b11eae6f336f55200f4c2b86d498858e30835bbb` |
| `cli-v0.0.18-beta.1-8dffd14c8808` | `8dffd14c8808` | `077d6b6da04af277b725ee77f42df95386504d6c` |
| `cli-v0.0.19-57ef5d8bc614` | `57ef5d8bc614` | `917f92c566d027643d6e5980556cbd749e1462ad` |
| `cli-v0.0.20-2224e2a67cdd` | `2224e2a67cdd` | `3ee03252a311d2e75dd4790bf19c63aa5b3e1201` |
| `cli-v0.0.21-a0b15f308aff` | `a0b15f308aff` | `ccd976860736e4b4b9c6cfe86284ff37f6446b4c` |
| `cli-v0.0.22-1eb4820c57b4` | `1eb4820c57b4` | `7ebb728f5f8b4828e223999650767748bee04dd5` |
| `cli-v0.0.23-9faf7eeb818b` | `9faf7eeb818b` | `0ad5bb5d033d720b80fc912311c45f0b55ec7914` |
| `cli-v0.0.24-608c2b1b1b17` | `608c2b1b1b17` | `a5b9275afe2d12cc11832ee5ddfba68190a47231` |
| `cli-v0.0.25-6db784cf2775` | `6db784cf2775` | `29e78d5c9b9a46c7728fece9892013e651b46579` |
| `cli-v0.0.26-48d436d58520` | `48d436d58520` | `beec1ab4c2255490046e27336ee61092559e45d9` |

## Full commit map

`history-rewrite-2026-11-commits.tsv` lists every commit that survived, one line per commit:

```
old-sha<TAB>new-sha<TAB>subject
```

The map was reconstructed by matching author date and subject, which is unique for 4051 of the
4085 commits reachable from `main`. The remaining 34 are commits that became empty and were
dropped, plus the replayed demo-video commit. A commit absent from the map was dropped for that
reason; it carried no change outside the removed paths.

## Restore sources

The pre-rewrite repository still exists as a local mirror and as a bundle on the maintainer
machine. Anyone who needs the old history for an audit can ask the maintainer for it; the
mirror holds every branch, tag and pull-request commit that existed before the rewrite.

## Residual exposure

Deleting branches and force-pushing `main` does not remove `refs/pull/<id>/head` on GitHub.
Those refs are managed by GitHub and keep the pull-request commits reachable, so the removed
files and the old credential values can still be fetched by anyone with read access to the
repository. Only deleting the repository, or a support-assisted object purge, removes them.
The credential rotation is what makes that residue harmless.

## Verification

| Check | Result |
| --- | --- |
| `gitleaks git --log-opts=--all` over the rewritten history, 4622 commits, 636 MB | no leaks |
| `gitleaks dir` over the tracked and untracked file set | no leaks |
| `pnpm typecheck`, `pnpm lint`, `pnpm format:check` | pass |
| `pnpm test` full sweep, including build, boundary, memory, docs and package checks | pass |
| Tree of the rewritten `main` against the pre-rewrite `main` | only the credential, policy and demo-video paths differ |

## Repository controls added with the rewrite

- `.gitleaks.toml` keeps every default rule and allowlists only public identifiers and fake test values.
- `pnpm check:secrets` scans the file set a commit could publish; `pnpm check:secrets:history` scans every reachable commit.
- `.github/workflows/secret-scan.yml` runs the same configuration on every push to `main` and every pull request.
- `SECURITY.md` and `CONTRIBUTING.md` state the credential rules, the report channel and the merge gate.
- `.gitignore` rejects `.env.*`, `.work/`, `*.sqlite`, `*.sqlite3` and review archives.
