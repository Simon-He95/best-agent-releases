from pathlib import Path


def replace_once(path, old, new):
    path = Path("source/apps/cli/src") / path
    original = path.read_text()
    if original.count(old) != 1:
        raise SystemExit(f"Pinned CLI anchor changed in {path.name}")
    path.write_text(original.replace(old, new))


# Both arms share one bundle and one prompt. The candidate arm asks the CLI, through the
# environment the runner wrapper sets for that arm alone, to bound one captured exec stream to
# the same 256 KiB the `read` tool already uses instead of 1 MiB. That constant is the single
# owner of both the capture bound and the model-facing payload bound, so one patch changes one
# variable: how much text one exec result can add to the next request.
replace_once(
    "product-slices/workspace-tool-limits.ts",
    "  stdoutBytes: 1_048_576,\n  stderrBytes: 1_048_576,",
    """  stdoutBytes:
    process.env.BEST_AGENT_BENCHMARK_EXEC_STREAM_BUDGET === "1" ? 262_144 : 1_048_576,
  stderrBytes:
    process.env.BEST_AGENT_BENCHMARK_EXEC_STREAM_BUDGET === "1" ? 262_144 : 1_048_576,""",
)
