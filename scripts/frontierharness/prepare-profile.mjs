import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const folder = dirname(fileURLToPath(import.meta.url));
const profile = process.env.FH_PROFILE;
if (!["short", "short-readonly-audit"].includes(profile)) throw new Error("Unknown profile");
const baseline = readFileSync(join(folder, "short.txt"), "utf8").trim();
const guidance = readFileSync(join(folder, "readonly-audit.txt"), "utf8").trim();
const instruction = profile === "short-readonly-audit" ? baseline + " " + guidance : baseline;
const path = join(process.env.FH_ROOT, "runtime/lib/node_modules/@best-agent/cli/dist/index.js");
const bundle = readFileSync(path, "utf8");
const needle = JSON.stringify(baseline);
if (bundle.split(needle).length !== 2) throw new Error("Expected one pinned behavior instruction");
writeFileSync(join(process.env.FH_ROOT, "raw/runtime-index.js"), readFileSync(path));
writeFileSync(join(process.env.FH_ROOT, "report/profile.json"), JSON.stringify({
  profile,
  source_sha: process.env.SOURCE_SHA,
  prompt_sha256: createHash("sha256").update(JSON.stringify(instruction)).digest("hex"),
  bundle_sha256: createHash("sha256").update(readFileSync(path)).digest("hex"),
}));
