"""Make compaction timing an arm-declared fact for the benchmark only.

Why this exists: the shipped product compacts a turn when the next request would reach a share
of the declared window (`AUTO_COMPACT_TRIGGER_RATIO`, 0.85), and the headless run compacts only
when a compact directory is supplied. Both facts are product decisions, not benchmark knobs, so
the harness cannot yet ask "what if we folded earlier?" without changing them for one arm.

This patch adds three environment reads and nothing else:

  BEST_AGENT_BENCHMARK_COMPACT_DIR          supplies the compact directory when the run was not
                                            given `--compact-dir` (the flag still wins)
  BEST_AGENT_BENCHMARK_AUTO_COMPACT_TRIGGER overrides the trigger share, in percent, and is
                                            clamped by the product's own admitted band [50, 100]
  BEST_AGENT_BENCHMARK_DECISION_WINDOW      declares the window the fold decision judges, in
                                            tokens: it lowers the threshold the decision compares
                                            against and changes nothing else — the model's real
                                            budget, its enforcement and the workspace tool limits
                                            stay the model's own

Without any of the three the bundle behaves exactly as before: no compact directory, ratio 0.85 and
the model's own window. All are recorded per arm in arms.json, and the run's own score package
carries the observable consequence (`compact_context_requests`), so an arm that never folded is
visible as a zero.

Why a decision window is a knob at all: the trigger fires when the next request would reach `ratio`
of the window, so at the shipped 1M window and 0.85 the wall sits near 850k while these tasks'
largest single request is ~650k — the fold cannot fire, and a fold timing cannot be measured.

Declaring a *smaller real* budget does not fix that, which is why this knob exists instead: the
product derives its workspace report cap from the same budget (`execReportBytes ≈ budget·3/8`), so a
400k budget also cuts every exec report to 149 KB and the transcript stops growing — the wall and the
material both shrink. Measured on gcode-to-text: 389k peak request at a 1M budget (374 KB reports)
against 121k at a 400k budget (149 KB reports), so even the 200k wall stayed out of reach. A decision
window lowers only the threshold, leaving the material these tasks produce intact.

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

# The decision itself. `window` keeps reporting the model's real window, because a caller reads it
# for more than the threshold (`native-runtime-bridge` compares a checkpoint against it to decide
# whether the source still fits), so only the threshold moves. A declared window at or above the
# real one, or one that is not a positive integer, leaves the shipped decision exactly as it was.
replace_once(
    "product-slices/auto-compact.ts",
    """  const window = requestInputWindow(budget);
  const forced = unrecoveredWall === true;
  if (window === undefined)
    return forced
      ? Object.freeze({ window: undefined, threshold: undefined, estimated, triggered: true })
      : undefined;
  const threshold = Math.floor(window * normalizeAutoCompactTriggerRatio(triggerRatio));""",
    """  const window = requestInputWindow(budget);
  const forced = unrecoveredWall === true;
  if (window === undefined)
    return forced
      ? Object.freeze({ window: undefined, threshold: undefined, estimated, triggered: true })
      : undefined;
  // The benchmark may judge the decision against a window these tasks actually fill. Only the
  // threshold moves: the reported `window` stays the model's real one, and the model's budget, its
  // enforcement and the workspace limits derived from it are untouched.
  const declaredDecisionWindow = Number(process.env.BEST_AGENT_BENCHMARK_DECISION_WINDOW);
  const decisionWindow =
    Number.isSafeInteger(declaredDecisionWindow) &&
    declaredDecisionWindow > 0 &&
    declaredDecisionWindow < window
      ? declaredDecisionWindow
      : window;
  const threshold = Math.floor(decisionWindow * normalizeAutoCompactTriggerRatio(triggerRatio));""",
)

print("compact timing patch applied")
sys.exit(0)
