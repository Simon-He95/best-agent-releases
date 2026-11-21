from pathlib import Path


def replace_once(path, old, new):
    path = Path("source/apps/cli/src") / path
    original = path.read_text()
    if original.count(old) != 1:
        raise SystemExit(f"Pinned CLI anchor changed in {path.name}")
    path.write_text(original.replace(old, new))


replace_once(
    "v3-run-options.ts",
    "  const requestBudgetSelection = resolveModelRequestBudget(selectedModel, ownLimits);",
    """  // This benchmark's compatibility relay receives no provider model catalog.
  // Both arms use the context/output limits from the actual Dim OAuth catalog.
  const limits = ownLimits ?? (selectedKind === "openai" && selectedModel === "deepseek-v4.1-flash"
    ? { context: 1_000_000, output: 384_000 } : undefined);
  const requestBudgetSelection = resolveModelRequestBudget(selectedModel, limits);""",
)
replace_once(
    "v3-run.ts",
    "        compactToolService,\n",
    """        // Keep the 31-tool benchmark surface in both arms.
        compactToolService: options.providerConfig.model === "deepseek-v4.1-flash"
          ? undefined : compactToolService,
""",
)
