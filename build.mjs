import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";
import {
  appendFileSync,
  closeSync,
  copyFileSync,
  existsSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

export function readRequest(file) {
  const request = JSON.parse(readFileSync(file, "utf8"));
  if (
    Object.keys(request).sort().join(",") !== "sourceRepository,sourceSha,version" ||
    request.sourceRepository !== "Simon-He95/best-agent" ||
    !/^[a-f0-9]{40}$/.test(request.sourceSha) ||
    !/^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$/.test(request.version)
  ) {
    throw new Error("Invalid distribution request.");
  }
  return { ...request, tag: `cli-v${request.version}-${request.sourceSha.slice(0, 12)}` };
}

export function seal(bytes, key) {
  const nonce = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, nonce);
  const encrypted = Buffer.concat([cipher.update(bytes), cipher.final()]);
  return Buffer.concat([nonce, cipher.getAuthTag(), encrypted]);
}

export function unseal(bytes, key) {
  const decipher = createDecipheriv("aes-256-gcm", key, bytes.subarray(0, 12));
  decipher.setAuthTag(bytes.subarray(12, 28));
  return Buffer.concat([decipher.update(bytes.subarray(28)), decipher.final()]);
}

const root = process.cwd();
const source = path.join(root, "source");
const output = path.join(root, "output");
const log = path.join(process.env.RUNNER_TEMP || root, "private-build.log");

function run(command, args, cwd = source, privateOutput = true) {
  const env = { ...process.env };
  delete env.GH_TOKEN;
  delete env.BUILD_ENCRYPTION_KEY;
  const fd = privateOutput ? openSync(log, "a") : undefined;
  const result = spawnSync(command, args, {
    cwd,
    env: command === "gh" ? process.env : env,
    shell: process.platform === "win32" && command !== "gh",
    stdio: privateOutput ? ["ignore", fd, fd] : ["ignore", "pipe", "pipe"],
    encoding: "utf8",
  });
  if (fd !== undefined) closeSync(fd);
  if (result.error || result.status !== 0) {
    if (result.error) appendFileSync(log, `${result.error.stack}\n`);
    if (!privateOutput) appendFileSync(log, `${result.stdout || ""}${result.stderr || ""}`);
    throw new Error(
      `${command} failed (exit ${result.status ?? "spawn"}); diagnostics are encrypted.`,
    );
  }
  return result.stdout;
}

function gh(args) {
  return run("gh", args, root, false);
}

function key() {
  const value = Buffer.from(process.env.BUILD_ENCRYPTION_KEY || "", "base64");
  if (value.length !== 32)
    throw new Error("BUILD_ENCRYPTION_KEY must contain a 32-byte base64 key.");
  return value;
}

function digest(file) {
  return createHash("sha256").update(readFileSync(file)).digest("hex");
}

function install() {
  run("corepack", ["enable"]);
  run("corepack", ["install"]);
  run("pnpm", ["install", "--frozen-lockfile"]);
}

function upload(request, files) {
  gh([
    "release",
    "upload",
    request.tag,
    ...files,
    "--repo",
    process.env.GITHUB_REPOSITORY,
    "--clobber",
  ]);
}

async function main() {
  const [mode, target, destination] = process.argv.slice(2);
  if (mode === "decrypt") {
    writeFileSync(destination, unseal(readFileSync(target), key()), { mode: 0o600 });
    return;
  }
  const request = readRequest(path.join(root, "build-request.json"));
  if (mode === "request") {
    appendFileSync(process.env.GITHUB_OUTPUT, `sha=${request.sourceSha}\ntag=${request.tag}\n`);
    return;
  }
  mkdirSync(output, { recursive: true });
  if (mode === "prepare") {
    const view = spawnSync(
      "gh",
      [
        "release",
        "view",
        request.tag,
        "--repo",
        process.env.GITHUB_REPOSITORY,
        "--json",
        "isDraft",
      ],
      { encoding: "utf8" },
    );
    if (view.status === 0) {
      if (!JSON.parse(view.stdout).isDraft)
        throw new Error(
          "This source commit already has a published distribution; refusing to replace it.",
        );
    } else {
      gh([
        "release",
        "create",
        request.tag,
        "--repo",
        process.env.GITHUB_REPOSITORY,
        "--draft",
        "--prerelease",
        "--target",
        process.env.GITHUB_SHA,
        "--title",
        `best-agent ${request.version} (${request.sourceSha.slice(0, 12)})`,
        "--notes",
        "Six-platform standalone binaries and npm tarballs. npm registry publication is disabled. Acceptance pending.",
      ]);
    }
    return;
  }
  let published = false;
  try {
    install();
    const { cliSeaTargets } = await import(
      pathToFileURL(path.join(source, "scripts/cli-sea-targets.mjs"))
    );
    if (
      JSON.parse(readFileSync(path.join(source, "apps/cli/package.json"))).version !==
      request.version
    )
      throw new Error("Source version does not match request.");
    if (mode === "build") {
      const platform = cliSeaTargets.find((item) => item.id === target);
      if (!platform || platform.platform !== process.platform || platform.arch !== process.arch)
        throw new Error("Runner does not match requested target.");
      console.log(`Building and exercising ${target} with Node absent and unusable.`);
      run("pnpm", ["pack:tui"]);
      run("pnpm", [
        "exec",
        "vitest",
        "run",
        "apps/cli/test/tui-cpu-pressure.test.ts",
        "--reporter=dot",
      ]);
      const dir = path.join(source, ".tmp/sea", target);
      const name = `best-agent-${request.version}-${target}.${platform.platform === "win32" ? "zip" : "tar.gz"}`;
      const archive = path.join(dir, name);
      const metadata = {
        sourceSha: request.sourceSha,
        target,
        archive: { name, sha256: digest(archive) },
        report: readFileSync(path.join(dir, "build-report.json"), "utf8"),
        evidence: readFileSync(path.join(dir, "acceptance-evidence.json"), "utf8"),
      };
      const sealed = path.join(output, `${target}.metadata.enc`);
      writeFileSync(sealed, seal(Buffer.from(JSON.stringify(metadata)), key()));
      upload(request, [archive, `${archive}.sha256`, sealed]);
      console.log(
        `${target}: installed native dependencies, Node-free TUI interaction and CPU supervisor checks passed.`,
      );
    } else if (mode === "assemble") {
      const downloads = path.join(output, "downloads");
      mkdirSync(downloads, { recursive: true });
      gh([
        "release",
        "download",
        request.tag,
        "--repo",
        process.env.GITHUB_REPOSITORY,
        "--dir",
        downloads,
      ]);
      const accepted = [];
      for (const platform of cliSeaTargets) {
        const metadata = JSON.parse(
          unseal(readFileSync(path.join(downloads, `${platform.id}.metadata.enc`)), key()),
        );
        const extension = platform.platform === "win32" ? "zip" : "tar.gz";
        const name = `best-agent-${request.version}-${platform.id}.${extension}`;
        if (
          metadata.sourceSha !== request.sourceSha ||
          metadata.target !== platform.id ||
          metadata.archive.name !== name ||
          metadata.archive.sha256 !== digest(path.join(downloads, name))
        )
          throw new Error(`Artifact binding failed for ${platform.id}.`);
        const extracted = path.join(output, platform.id);
        mkdirSync(extracted, { recursive: true });
        if (extension === "zip") run("unzip", ["-q", path.join(downloads, name), "-d", extracted]);
        else run("tar", ["-xzf", path.join(downloads, name), "-C", extracted]);
        const dir = path.join(source, ".tmp/sea", platform.id);
        mkdirSync(dir, { recursive: true });
        const bin = path.join(extracted, name.slice(0, -extension.length - 1), "bin");
        const supervisor = platform.platform === "win32" ? "cpu-supervisor.exe" : "cpu-supervisor";
        copyFileSync(path.join(bin, platform.binary), path.join(dir, platform.binary));
        copyFileSync(path.join(bin, supervisor), path.join(dir, supervisor));
        writeFileSync(path.join(dir, "build-report.json"), metadata.report);
        writeFileSync(path.join(dir, "acceptance-evidence.json"), metadata.evidence);
        accepted.push({
          target: platform.id,
          standaloneSha256: metadata.archive.sha256,
          nodeAbsent: true,
          unusableNode: true,
          nativeDependencySmoke: true,
          interactiveTui: true,
          cpuSupervisor: true,
        });
      }
      run("pnpm", ["release:cli", "--artifact-root", ".tmp/sea", "--dry-run"]);
      const stage = path.join(source, ".tmp/npm/release-stage");
      for (const id of [...cliSeaTargets.map((item) => item.id), "cli"])
        run("pnpm", ["pack", "--pack-destination", output], path.join(stage, id));
      const files = readdirSync(output)
        .filter((name) => name.endsWith(".tgz"))
        .map((name) => path.join(output, name));
      if (files.length !== 7) throw new Error("Expected exactly seven npm tarballs.");
      const summary = path.join(output, "acceptance.json");
      writeFileSync(
        summary,
        `${JSON.stringify({ version: request.version, sourceSha: request.sourceSha, npmPublished: false, targets: accepted }, null, 2)}\n`,
      );
      const sums = path.join(output, "SHA256SUMS");
      const archives = readdirSync(downloads)
        .filter((name) => name.endsWith(".tar.gz") || name.endsWith(".zip"))
        .map((name) => path.join(downloads, name));
      writeFileSync(
        sums,
        [...files, ...archives, summary]
          .map((file) => `${digest(file)}  ${path.basename(file)}`)
          .join("\n") + "\n",
      );
      upload(request, [...files, summary, sums]);
      for (const name of readdirSync(downloads).filter((name) => name.endsWith(".enc")))
        gh([
          "release",
          "delete-asset",
          request.tag,
          name,
          "--repo",
          process.env.GITHUB_REPOSITORY,
          "--yes",
        ]);
      gh([
        "release",
        "edit",
        request.tag,
        "--repo",
        process.env.GITHUB_REPOSITORY,
        "--draft=false",
        "--notes",
        `All six matching runners passed native installed dependency checks, Node-free and unusable-Node PTY/ConPTY TUI interaction, and CPU supervisor checks. Source commit: ${request.sourceSha}. Seven npm tarballs are provided for download; nothing was published to the npm registry.`,
      ]);
      published = true;
      console.log(
        `Distribution ready: https://github.com/${process.env.GITHUB_REPOSITORY}/releases/tag/${request.tag}`,
      );
    } else throw new Error("Unknown distribution command.");
  } catch (error) {
    appendFileSync(log, `${error.stack}\n`);
    throw error;
  } finally {
    const diagnostics = path.join(output, `${mode === "build" ? target : "assemble"}.log.enc`);
    if (existsSync(log)) {
      writeFileSync(diagnostics, seal(readFileSync(log), key()));
      // Successful assembly has already published its allowlisted assets.
      if (!published) {
        try {
          upload(request, [diagnostics]);
        } catch {
          console.error("Encrypted diagnostic upload failed; inspect this runner before retrying.");
        }
      }
    }
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
