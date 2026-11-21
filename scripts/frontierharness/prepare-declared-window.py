from pathlib import Path


def replace_once(path, old, new):
    path = Path("source/apps/cli/src") / path
    original = path.read_text()
    if original.count(old) != 1:
        raise SystemExit(f"Pinned CLI anchor changed in {path.name}")
    path.write_text(original.replace(old, new))


replace_once(
    "v3-run-options.ts",
    "  const providerConfig: V3ProviderConfig = {\n    apiKey: selectedApiKey,",
    """  const benchmarkModel = selectedKind === "openai" && selectedModel === "deepseek-v4.1-flash";
  // The upstream FrontierHarness v1.1 proxy applies this output cap.
  const benchmarkOutputCap = 131_072;
  const providerConfig: V3ProviderConfig = {
    ...(benchmarkModel ? { maxOutputTokens: benchmarkOutputCap } : {}),
    apiKey: selectedApiKey,""",
)
replace_once(
    "v3-run-options.ts",
    "  const requestBudgetSelection = resolveModelRequestBudget(selectedModel, ownLimits);",
    """  // The runner relay omits the model catalog. Only the recovery arm declares
  // the measured Dim model's window with the v1.1 output allowance reserved.
  const useRecovery = benchmarkModel && environment.BEST_AGENT_BENCHMARK_WINDOW_RECOVERY === "1";
  const limits = useRecovery ? { context: 1_000_000, output: benchmarkOutputCap } : ownLimits;
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
