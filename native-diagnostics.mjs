import { createHash, createPublicKey, publicEncrypt, randomBytes } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { seal, unseal } from "./build.mjs";

if (
  process.env.GITHUB_REPOSITORY !== "Simon-He95/best-agent-releases" ||
  process.env.GITHUB_REF !== "refs/heads/main" ||
  process.env.GITHUB_EVENT_NAME !== "workflow_dispatch"
)
  throw new Error("Manual main-only diagnostic export required.");
const tag = process.env.DIAGNOSTIC_TAG;
const run = process.env.DIAGNOSTIC_RUN;
if (Boolean(tag) === Boolean(run)) throw new Error("Provide one diagnostic tag or Actions run.");
if (tag && !/^cli-v[0-9A-Za-z.-]+-[a-f0-9]{12}$/.test(tag))
  throw new Error("Invalid diagnostic tag.");
if (run && !/^[1-9][0-9]{0,19}$/.test(run)) throw new Error("Invalid diagnostic Actions run.");
const assets = (process.env.DIAGNOSTIC_ASSETS ?? "").split(",");
const targetLog =
  /^(darwin-arm64|darwin-x64|linux-arm64-gnu|linux-x64-gnu|win32-arm64|win32-x64)\.log\.enc$/;
const rustEvidence =
  /^rust-(darwin-arm64|darwin-x64|linux-arm64-gnu|linux-x64-gnu|win32-arm64|win32-x64)\.(?:log|metadata|archive)\.enc$/;
const npmReplay = /^rust-npm-(win32-arm64|win32-x64|stage)\.(?:log|receipt)\.enc$/;
if (
  assets.some(
    (asset) =>
      !targetLog.test(asset) &&
      !(run
        ? rustEvidence.test(asset) || npmReplay.test(asset)
        : /^(assemble|source-gate)\.log\.enc$/.test(asset)),
  )
)
  throw new Error("Invalid diagnostic asset selection.");
const recipient = createPublicKey(process.env.RECIPIENT_KEY);
if (recipient.asymmetricKeyType !== "rsa") throw new Error("RSA recipient required.");
const fingerprint = createHash("sha256")
  .update(recipient.export({ type: "spki", format: "der" }))
  .digest("hex");
const key = Buffer.from(process.env.BUILD_ENCRYPTION_KEY, "base64");
if (key.length !== 32) throw new Error("Invalid build encryption key.");
const input = path.join(process.env.RUNNER_TEMP, "native-private-diagnostics");
const output = path.join(process.env.RUNNER_TEMP, "native-resealed-diagnostics");
mkdirSync(input, { recursive: true, mode: 0o700 });
mkdirSync(output, { recursive: true, mode: 0o700 });
const repository = process.env.GITHUB_REPOSITORY;
if (run) {
  const workflow = JSON.parse(
    execFileSync("gh", ["api", `repos/${repository}/actions/runs/${run}`], { encoding: "utf8" }),
  );
  if (
    workflow.path !== ".github/workflows/native-read-helper.yml" ||
    workflow.event !== "workflow_dispatch" ||
    workflow.head_branch !== "main"
  )
    throw new Error("Rust diagnostics require a manual verification run on main.");
  if (
    assets.some((asset) => asset.endsWith(".archive.enc")) &&
    (workflow.status !== "completed" || workflow.conclusion !== "success")
  )
    throw new Error("Rust archives require a successful verification run.");
  const bundles = new Set(
    assets.map((asset) => {
      const npm = npmReplay.exec(asset);
      if (npm) return `rust-npm-verification-${npm[1]}`;
      const [, target] = rustEvidence.exec(asset) ?? targetLog.exec(asset);
      return `rust-verification-${target}`;
    }),
  );
  for (const bundle of bundles) {
    execFileSync(
      "gh",
      ["run", "download", run, "--repo", repository, "--name", bundle, "--dir", input],
      {
        stdio: ["ignore", "ignore", "inherit"],
      },
    );
  }
}
for (const asset of assets) {
  if (tag) {
    execFileSync(
      "gh",
      ["release", "download", tag, "--repo", repository, "--pattern", asset, "--dir", input],
      {
        stdio: ["ignore", "ignore", "inherit"],
      },
    );
  }
  const plaintext = unseal(readFileSync(path.join(input, asset)), key);
  const transferKey = randomBytes(32);
  writeFileSync(
    path.join(output, `${asset}.json`),
    JSON.stringify({
      recipient: fingerprint,
      key: publicEncrypt({ key: recipient, oaepHash: "sha256" }, transferKey).toString("base64"),
      payload: seal(plaintext, transferKey).toString("base64"),
    }) + "\n",
    { mode: 0o600 },
  );
}
console.log("Diagnostic ciphertext re-sealed to the requested public key; no plaintext exported.");
