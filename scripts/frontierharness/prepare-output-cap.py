import json
from pathlib import Path


def replace_once(path, old, new):
    path = Path("source/apps/cli/src") / path
    original = path.read_text()
    if original.count(old) != 1:
        raise SystemExit(f"Pinned CLI anchor changed in {path.name}")
    path.write_text(original.replace(old, new))


# The declared control cap and the fallback compiled into the bundle must be the same number, or an
# arm that declares the default would silently run with a different one.
declared = json.loads((Path(__file__).with_name("arms.json")).read_text())
control_cap = declared["short"]["output_cap"]

replace_once(
    "v3-run-options.ts",
    "  const providerConfig: V3ProviderConfig = {\n    apiKey: selectedApiKey,",
    """  const benchmarkModel = selectedKind === "openai" && selectedModel === "deepseek-v4.1-flash";
  // The upstream FrontierHarness v1.1 proxy applies this output cap. One bundle serves both arms, so an
  // arm that wants a different cap exports it through the environment its runner wrapper sets. The
  // ledger records the cap the request actually carried, and report.py compares that with the cap the
  // arm declared in arms.json.
  const benchmarkOutputCap = Number(process.env.BEST_AGENT_BENCHMARK_OUTPUT_CAP || "") || """
    + f"{control_cap}"
    + """;
  const providerConfig: V3ProviderConfig = {
    ...(benchmarkModel ? { maxOutputTokens: benchmarkOutputCap } : {}),
    apiKey: selectedApiKey,""",
)

replace_once(
    "v3-run-options.ts",
    "    connection: oauthConnection,\n    // A pinned id is admitted",
    """    connection: oauthConnection,
    // The benchmark relay serves one model. Its record set has no alternate child model.
    ...(benchmarkModel ? { records: [{ id: providerConfig.model, type: "chat" }] } : {}),
    // A pinned id is admitted""",
)
