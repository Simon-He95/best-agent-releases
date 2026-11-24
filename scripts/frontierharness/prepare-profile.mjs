import { copyFileSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const folder = dirname(fileURLToPath(import.meta.url));
const profile = process.env.FH_PROFILE;
if (!["short", "short-effort-high"].includes(profile)) throw new Error("Unknown profile");
const baseline = readFileSync(join(folder, "short.txt"), "utf8").trim();
const path = join(process.env.FH_ROOT, "runtime/lib/node_modules/@best-agent/cli/dist/index.js");
// Both arms share this runtime; start from the copy build.sh kept aside so neither arm inherits the
// other's prompt.
copyFileSync(join(process.env.FH_ROOT, "runtime/pristine-index.js"), path);
const bundle = readFileSync(path, "utf8");
if (bundle.split(JSON.stringify(baseline)).length !== 2) throw new Error("Expected one pinned behavior instruction");
writeFileSync(join(process.env.FH_ROOT, "raw/runtime-index.js"), bundle);
writeFileSync(join(process.env.FH_ROOT, "report/profile.json"), JSON.stringify({
  profile,
  source_sha: process.env.SOURCE_SHA,
  prompt_sha256: createHash("sha256").update(JSON.stringify(baseline)).digest("hex"),
  bundle_sha256: createHash("sha256").update(bundle).digest("hex"),
}));
