"""Make compaction timing an arm-declared fact for the benchmark only.

Why this exists: the shipped product compacts a turn when the next request would reach a share
of the declared window (`AUTO_COMPACT_TRIGGER_RATIO`, 0.85), and the headless run compacts only
when a compact directory is supplied. Both facts are product decisions, not benchmark knobs, so
the harness cannot yet ask "what if we folded earlier?" without changing them for one arm.

This patch adds two environment reads and nothing else:

  BEST_AGENT_BENCHMARK_COMPACT_DIR          supplies the compact directory when the run was not
                                            given `--compact-dir` (the flag still wins)
  BEST_AGENT_BENCHMARK_AUTO_COMPACT_TRIGGER overrides the trigger share, in percent, and is
                                            clamped by the product's own admitted band [50, 100]

Without either variable the bundle behaves exactly as before: no compact directory, ratio 0.85.
Both are recorded per arm in arms.json, and the run's own score package carries the observable
consequence (`compact_context_requests`), so an arm that never folded is visible as a zero.

Run from the harness root, whose `source/` is the checked-out private tree.
"""

import sys
from pathlib import Path

SOURCE = Path("source/apps/cli/src")


def replace_once(relative, old, new):
    path = SOURCE / relative
    original = path.read_text()
    if original.count(old) != 1:
        raise SystemExit(f"Pinned anchor changed in {path.name}: {old!r}")
    path.write_text(original.replace(old, new))
    print(f"patched {relative}")


# The candidate's early share must still pass through the product's own normalizer, so this only
# substitutes the default the normalizer falls back to when a host states no preference.
replace_once(
    "product-slices/auto-compact.ts",
    "export const AUTO_COMPACT_TRIGGER_RATIO = 0.85;",
    """/**
 * The share of the declared window at which a host folds before requesting. The benchmark exports
 * `BEST_AGENT_BENCHMARK_AUTO_COMPACT_TRIGGER` (percent) so one bundle can compare two fold timings;
 * every other host keeps 0.85. The value is still clamped by `normalizeAutoCompactTriggerRatio`.
 */
export const AUTO_COMPACT_TRIGGER_RATIO = (() => {
  const declared = Number(process.env.BEST_AGENT_BENCHMARK_AUTO_COMPACT_TRIGGER);
  return Number.isFinite(declared) && declared > 0 ? declared / 100 : 0.85;
})();""",
)

# `--compact-dir` still wins: an explicit flag is a host decision, not a benchmark default.
replace_once(
    "v3-run-options.ts",
    "  let compactDir: string | undefined;",
    """  // A benchmark arm may supply the directory through its environment. An explicit flag is
  // parsed later and overwrites this, so the CLI contract is unchanged.
  let compactDir: string | undefined =
    process.env.BEST_AGENT_BENCHMARK_COMPACT_DIR || undefined;""",
)

print("compact timing patch applied")
sys.exit(0)
