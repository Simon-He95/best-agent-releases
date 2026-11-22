import json
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

guidance = Path(__file__).with_name("readonly-audit.txt").read_text().strip()
conditional = Path(__file__).with_name("readonly-audit-conditional-wait.txt").read_text().strip()
replace_once(
    "v3-prompt-composition.ts",
    "          ? HEADLESS_BEHAVIOR_INSTRUCTION_TEXT",
    """          ? process.env.BEST_AGENT_FH_READONLY_AUDIT === "conditional"
            ? HEADLESS_BEHAVIOR_INSTRUCTION_TEXT + """ + json.dumps(" " + conditional) + """
            : process.env.BEST_AGENT_FH_READONLY_AUDIT === "1"
              ? HEADLESS_BEHAVIOR_INSTRUCTION_TEXT + """ + json.dumps(" " + guidance) + """
              : HEADLESS_BEHAVIOR_INSTRUCTION_TEXT""",
)
