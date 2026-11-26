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
  BEST_AGENT_BENCHMARK_INPUT_BUDGET         declares the prompt allowance the arm measures, in
                                            tokens: it only ever narrows the model's own resolved
                                            budget, and states itself as `explicit-config` instead
                                            of presenting the number as provider metadata

Without any of the three the bundle behaves exactly as before: no compact directory, ratio 0.85 and
the model's own budget. All are recorded per arm in arms.json, and the run's own score package
carries the observable consequence (`compact_context_requests`), so an arm that never folded is
visible as a zero.

Why the budget is a knob at all: the trigger fires when the next request would reach `ratio` of the
declared budget, so at the shipped 1M window and 0.85 the wall sits near 850k while these tasks'
largest single request is ~650k — the fold cannot fire, and a fold timing cannot be measured. An arm
that declares a smaller allowance moves the wall into the range the tasks actually reach.

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

# One resolution point feeds every reader of the budget (the fold trigger, the binding's own input
# ruler and the workspace tool limits), so the declaration lands here rather than beside any of
# them. It narrows only: a value at or above the model's own budget leaves the resolved record
# untouched, so a declared window can never claim more room than the provider's record states.
replace_once(
    "v3-request-budget.ts",
    """  return resolveRequestBudget(
    limits === undefined
      ? undefined
      : {
          contextWindowTokens: limits.context,
          maxPromptTokens: limits.input,
          maxOutputTokens: limits.output,
          model,
          source: "provider-model-metadata",
        },
    model,
  );""",
    """  const resolved = resolveRequestBudget(
    limits === undefined
      ? undefined
      : {
          contextWindowTokens: limits.context,
          maxPromptTokens: limits.input,
          maxOutputTokens: limits.output,
          model,
          source: "provider-model-metadata",
        },
    model,
  );
  // The benchmark may declare the prompt allowance an arm is measuring, so one bundle can compare
  // folding at a window these tasks actually fill. The declaration is a host policy laid over the
  // model's own numbers: it never widens them, and it labels itself `explicit-config` rather than
  // passing the number off as provider metadata. A model whose own budget is unknown keeps its own
  // answer, so a typo in the arm cannot silently invent a window the run then measures against.
  const declaredBudget = Number(process.env.BEST_AGENT_BENCHMARK_INPUT_BUDGET);
  if (
    resolved === undefined ||
    !Number.isSafeInteger(declaredBudget) ||
    declaredBudget <= 0 ||
    declaredBudget >= resolved.inputBudgetTokens
  ) {
    return resolved;
  }
  return Object.freeze({
    ...resolved,
    budgetSource: "explicit-config",
    inputBudgetTokens: declaredBudget,
  });""",
)

print("compact timing patch applied")
sys.exit(0)
