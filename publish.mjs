import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { appendFileSync, mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const repository = "Simon-He95/best-agent-releases";
const repositoryUrl = `git+https://github.com/${repository}.git`;
const registry = "https://registry.npmjs.org";
const targets = [
  "darwin-arm64",
  "darwin-x64",
  "linux-arm64-gnu",
  "linux-x64-gnu",
  "win32-arm64",
  "win32-x64",
];

function run(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8" });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} failed: ${result.stderr || result.stdout}`);
  return result.stdout;
}

function api(endpoint) {
  return JSON.parse(run("gh", ["api", `repos/${repository}/${endpoint}`]));
}

function hash(file, algorithm = "sha256", encoding = "hex") {
  return createHash(algorithm).update(readFileSync(file)).digest(encoding);
}

async function main() {
  if (
    process.env.GITHUB_REPOSITORY !== repository ||
    process.env.GITHUB_REF !== "refs/heads/main" ||
    process.env.GITHUB_EVENT_NAME !== "workflow_dispatch"
  )
    throw new Error("npm publication requires a manual run on the distribution repository's main.");
  const tag = process.env.RELEASE_TAG;
  if (!/^cli-v\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?-[a-f0-9]{12}$/.test(tag || ""))
    throw new Error("Invalid release tag.");
  const npmTag = process.env.NPM_TAG;
  if (!["beta", "latest"].includes(npmTag)) throw new Error("Invalid npm tag.");
  if (!["true", "false"].includes(process.env.PUBLISH_DRY_RUN))
    throw new Error("PUBLISH_DRY_RUN must explicitly be true or false.");
  const dryRun = process.env.PUBLISH_DRY_RUN === "true";
  const release = api(`releases/tags/${tag}`);
  if (release.draft || release.tag_name !== tag) throw new Error("Release is not published.");
  const commit = api(`commits/${tag}`).sha;
  const requestFile = api(`contents/build-request.json?ref=${commit}`);
  const request = JSON.parse(Buffer.from(requestFile.content, "base64").toString("utf8"));
  if (
    request.sourceRepository !== "Simon-He95/best-agent" ||
    !/^[a-f0-9]{40}$/.test(request.sourceSha || "") ||
    tag !== `cli-v${request.version}-${request.sourceSha.slice(0, 12)}`
  )
    throw new Error("Release does not match its source build request.");
  if (npmTag === "latest" && request.version.includes("-"))
    throw new Error("A prerelease version cannot be published as latest.");

  const runs = api(
    `actions/workflows/build.yml/runs?head_sha=${commit}&status=success&per_page=100`,
  ).workflow_runs;
  const build = runs.find(
    (run) =>
      run.head_sha === commit &&
      run.head_branch === "main" &&
      ["push", "workflow_dispatch"].includes(run.event) &&
      run.conclusion === "success",
  );
  if (!build) throw new Error("No successful trusted six-platform build for this release.");
  const jobs = api(`actions/runs/${build.id}/jobs?per_page=100`).jobs;
  if (
    !["prepare", "distribute"].every((name) =>
      jobs.some((job) => job.name === name && job.conclusion === "success"),
    ) ||
    !targets.every((target) =>
      jobs.some((job) => job.name.startsWith(`build (${target}, `) && job.conclusion === "success"),
    )
  )
    throw new Error("All six native build jobs and distribution must succeed.");

  const archives = targets.map(
    (target) =>
      `best-agent-${request.version}-${target}.${target.startsWith("win32") ? "zip" : "tar.gz"}`,
  );
  const packages = [...targets.map((target) => `cli-${target}`), "cli"].map((name) => ({
    name: `@best-agent/${name}`,
    file: `best-agent-${name}-${request.version}.tgz`,
  }));
  const checkedFiles = [...archives, ...packages.map(({ file }) => file), "acceptance.json"];
  const expectedAssets = [
    ...checkedFiles,
    ...archives.map((file) => `${file}.sha256`),
    "SHA256SUMS",
  ].sort();
  if (
    JSON.stringify(release.assets.map(({ name }) => name).sort()) !== JSON.stringify(expectedAssets)
  )
    throw new Error("Release asset set does not match a complete six-platform distribution.");

  const directory = path.resolve("npm-release", tag);
  mkdirSync(directory, { recursive: true });
  run("gh", ["release", "download", tag, "--repo", repository, "--dir", directory]);
  for (const asset of release.assets)
    if (asset.digest !== `sha256:${hash(path.join(directory, asset.name))}`)
      throw new Error(`GitHub asset digest mismatch: ${asset.name}`);
  const expectedSums = checkedFiles.map((file) => `${hash(path.join(directory, file))}  ${file}`);
  const actualSums = readFileSync(path.join(directory, "SHA256SUMS"), "utf8").trim().split("\n");
  if (JSON.stringify(actualSums.sort()) !== JSON.stringify(expectedSums.sort()))
    throw new Error("Release checksum manifest does not match downloaded files.");
  const acceptance = JSON.parse(readFileSync(path.join(directory, "acceptance.json"), "utf8"));
  const checks = [
    "nodeAbsent",
    "unusableNode",
    "nativeDependencySmoke",
    "interactiveTui",
    "cpuSupervisor",
  ];
  if (
    acceptance.version !== request.version ||
    acceptance.sourceSha !== request.sourceSha ||
    acceptance.npmPublished !== false ||
    !Array.isArray(acceptance.targets) ||
    JSON.stringify(acceptance.targets.map(({ target }) => target).sort()) !==
      JSON.stringify([...targets].sort()) ||
    !acceptance.targets.every(
      (entry) =>
        checks.every((check) => entry[check] === true) &&
        entry.standaloneSha256 ===
          hash(path.join(directory, archives[targets.indexOf(entry.target)])),
    )
  )
    throw new Error("Release acceptance does not prove all six platforms passed for these bytes.");

  // Validate every package before the first registry write, including the launcher published last.
  for (const entry of packages) {
    entry.file = path.join(directory, entry.file);
    const manifest = JSON.parse(run("tar", ["-xOf", entry.file, "package/package.json"]));
    if (
      manifest.name !== entry.name ||
      manifest.version !== request.version ||
      manifest.private === true ||
      manifest.repository?.type !== "git" ||
      manifest.repository?.url !== repositoryUrl
    )
      throw new Error(`Package identity or OIDC repository mismatch: ${entry.name}`);
    if (
      entry.name === "@best-agent/cli" &&
      JSON.stringify(Object.entries(manifest.optionalDependencies || {}).sort()) !==
        JSON.stringify(
          targets.map((target) => [`@best-agent/cli-${target}`, request.version]).sort(),
        )
    )
      throw new Error("Launcher must depend on all six exact platform versions.");
  }

  // A failed multi-package publish may be resumed only with byte-identical registry versions.
  for (const entry of packages) {
    const result = spawnSync(
      "npm",
      [
        "view",
        `${entry.name}@${request.version}`,
        "dist.integrity",
        "--json",
        `--registry=${registry}`,
      ],
      { encoding: "utf8" },
    );
    if (result.error) throw result.error;
    const response = JSON.parse(result.stdout || "{}");
    entry.exists = result.status === 0;
    if (entry.exists) {
      if (response !== `sha512-${hash(entry.file, "sha512", "base64")}`)
        throw new Error(
          `Registry already contains different bytes: ${entry.name}@${request.version}`,
        );
      const currentTag = JSON.parse(
        run("npm", [
          "view",
          entry.name,
          `dist-tags.${npmTag}`,
          "--json",
          `--registry=${registry}`,
        ]) || "null",
      );
      if (currentTag !== request.version)
        throw new Error(
          `Existing ${entry.name}@${request.version} is not tagged ${npmTag}; update its dist-tag explicitly.`,
        );
    } else if (response.error?.code !== "E404") {
      throw new Error(
        `Registry preflight failed: ${entry.name}: ${result.stderr || result.stdout}`,
      );
    }
  }
  for (const entry of packages) {
    if (entry.exists) {
      console.log(`Already published with matching integrity: ${entry.name}@${request.version}`);
      continue;
    }
    console.log(`${dryRun ? "Preview" : "Publish"}: ${entry.name}@${request.version}`);
    const args = [
      "publish",
      entry.file,
      `--registry=${registry}`,
      "--access=public",
      `--tag=${npmTag}`,
      "--ignore-scripts",
    ];
    if (dryRun) args.push("--dry-run");
    console.log(run("npm", args));
  }
  const summary = `${dryRun ? "Previewed" : "Published"} seven npm packages for ${tag} (${npmTag}). Build: https://github.com/${repository}/actions/runs/${build.id}\n`;
  console.log(summary);
  if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary);
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
