import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const folder = dirname(fileURLToPath(import.meta.url));
const profile = process.env.FH_PROFILE;
// The arms share one bundle and one reasoning effort. They differ by exactly one behavior
// instruction, so a paired run isolates that instruction instead of mixing it with an effort change.
const instructionFile = {
  short: "short.txt",
  "short-effort-high": "short.txt",
  "short-guard": "prompt-guard.txt",
  "short-lean": "prompt-lean.txt",
}[profile];
if (!instructionFile) throw new Error("Unknown profile");

// short.txt is the instruction compiled into the bundle. A different arm rewrites that one string,
// so the delivered system message is the arm's instruction and nothing else changes.
const pinned = readFileSync(join(folder, "short.txt"), "utf8").trim();
const instruction = readFileSync(join(folder, instructionFile), "utf8").trim();

const path = join(process.env.FH_ROOT, "runtime/lib/node_modules/@best-agent/cli/dist/index.js");
// Both arms share this runtime; start from the copy build.sh kept aside so neither arm inherits the
// other's prompt.
copyFileSync(join(process.env.FH_ROOT, "runtime/pristine-index.js"), path);
const original = readFileSync(path, "utf8");
const pinnedJson = JSON.stringify(pinned);
if (original.split(pinnedJson).length !== 2) throw new Error("Expected one pinned behavior instruction");
const bundle = instruction === pinned ? original : original.replace(pinnedJson, JSON.stringify(instruction));
if (bundle.split(JSON.stringify(instruction)).length !== 2) throw new Error("Expected one delivered instruction");
if (bundle !== original) writeFileSync(path, bundle);
writeFileSync(join(process.env.FH_ROOT, "raw/runtime-index.js"), bundle);
writeFileSync(join(process.env.FH_ROOT, "report/profile.json"), JSON.stringify({
  profile,
  source_sha: process.env.SOURCE_SHA,
  prompt_sha256: createHash("sha256").update(JSON.stringify(instruction)).digest("hex"),
  bundle_sha256: createHash("sha256").update(bundle).digest("hex"),
}));
