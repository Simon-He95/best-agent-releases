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
if (!/^cli-v[0-9A-Za-z.-]+-[a-f0-9]{12}$/.test(tag ?? ""))
  throw new Error("Invalid diagnostic tag.");
const assets = process.env.DIAGNOSTIC_ASSETS.split(",");
if (
  !assets.length ||
  assets.some(
    (asset) =>
      !/^(darwin-arm64|darwin-x64|linux-arm64-gnu|linux-x64-gnu|win32-arm64|win32-x64|assemble)\.log\.enc$/.test(
        asset,
      ),
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
for (const asset of assets) {
  execFileSync(
    "gh",
    [
      "release",
      "download",
      tag,
      "--repo",
      process.env.GITHUB_REPOSITORY,
      "--pattern",
      asset,
      "--dir",
      input,
    ],
    { stdio: "ignore" },
  );
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
