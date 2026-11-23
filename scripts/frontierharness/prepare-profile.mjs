import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const folder = dirname(fileURLToPath(import.meta.url));
const profile = process.env.FH_PROFILE;
if (!["short", "short-independent-jobs"].includes(profile)) throw new Error("Unknown profile");
const baseline = readFileSync(join(folder, "short.txt"), "utf8").trim();
const path = join(process.env.FH_ROOT, "runtime/lib/node_modules/@best-agent/cli/dist/index.js");
// Both arms of one pair share this runtime, so start from the bundle build.sh kept aside: the two
// arms differ by the wrapper's env switch, never by a previous arm's leftover edit.
copyFileSync(join(process.env.FH_ROOT, "runtime/pristine-index.js"), path);
const bundle = readFileSync(path, "utf8");
const needle = JSON.stringify(baseline);
if (bundle.split(needle).length !== 2) throw new Error("Expected one pinned behavior instruction");
writeFileSync(join(process.env.FH_ROOT, "raw/runtime-index.js"), bundle);
writeFileSync(join(process.env.FH_ROOT, "report/profile.json"), JSON.stringify({
  profile,
  source_sha: process.env.SOURCE_SHA,
  prompt_sha256: createHash("sha256").update(JSON.stringify(baseline)).digest("hex"),
  bundle_sha256: createHash("sha256").update(bundle).digest("hex"),
}));
