from pathlib import Path

TARGET = Path("source/packages/capability-builtin-tools/src/index.ts")

ANCHOR = """  if (commandPolicy === "catalog" && !executableAliases.includes(command))
    return { ok: false, code: "unknown-command" };
"""

# Both arms share one bundle and one prompt. The candidate arm asks the one exec admission site,
# through the environment the runner wrapper sets for that arm alone, to state the admitted
# argv[0] domain at the rejection point. The set is the frozen catalog the canonicalizer already
# checks, not a prompt copy, and the switch only changes whether the receipt names it.
REPLACEMENT = """  if (commandPolicy === "catalog" && !executableAliases.includes(command))
    return process.env.BEST_AGENT_BENCHMARK_UNKNOWN_COMMAND_ADMITTED === "1"
      ? malformedInput<ExecVector>(
          field,
          `argv[0] must be one of the admitted command aliases: ${executableAliases.join(", ")}. ` +
            "This composition does not resolve any other executable from PATH.",
        )
      : { ok: false, code: "unknown-command" };
"""

original = TARGET.read_text()
if original.count(ANCHOR) != 1:
    raise SystemExit(f"Pinned exec admission anchor changed in {TARGET.name}")
TARGET.write_text(original.replace(ANCHOR, REPLACEMENT))
