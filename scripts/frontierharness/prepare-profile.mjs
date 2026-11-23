import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const folder = dirname(fileURLToPath(import.meta.url));
const profile = process.env.FH_PROFILE;
if (!["short", "short-compact-hint", "short-verify-to-green"].includes(profile)) throw new Error("Unknown profile");
const baseline = readFileSync(join(folder, "short.txt"), "utf8").trim();
const chosen = readFileSync(join(folder, `${profile}.txt`), "utf8").trim();
const path = join(process.env.FH_ROOT, "runtime/lib/node_modules/@best-agent/cli/dist/index.js");
// The arms of one pair share this runtime, so an earlier arm's edit would still be installed here.
// build.sh keeps the shipped bundle beside it; start from that copy so the pair differs only by
// this arm's own instruction text, whichever order the workflow runs the arms in.
copyFileSync(join(process.env.FH_ROOT, "runtime/pristine-index.js"), path);
const bundle = readFileSync(path, "utf8");
const needle = JSON.stringify(baseline);
if (bundle.split(needle).length !== 2) throw new Error("Expected one pinned behavior instruction");
if (chosen !== baseline) writeFileSync(path, bundle.replace(needle, JSON.stringify(chosen)));
writeFileSync(join(process.env.FH_ROOT, "raw/runtime-index.js"), readFileSync(path));
writeFileSync(join(process.env.FH_ROOT, "report/profile.json"), JSON.stringify({
  profile,
  source_sha: process.env.SOURCE_SHA,
  prompt_sha256: createHash("sha256").update(JSON.stringify(chosen)).digest("hex"),
  bundle_sha256: createHash("sha256").update(readFileSync(path)).digest("hex"),
}));
