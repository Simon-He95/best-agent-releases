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
    "product-slices/thread-orchestration-root.ts",
    """    const published = foundation.publish(
      generationOptions,
      Object.freeze([""",
    """    const published = foundation.publish(
      generationOptions,
      process.env.BEST_AGENT_FH_OMIT_THREAD_TOOLS === "1" ? Object.freeze([]) : Object.freeze([""",
)
