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
  statSync,
  readdirSync,
  rmSync,
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
  delete env.SOURCE_SSH_KEY;
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
    if (mode === "checkout") {
      const identity = path.join(process.env.RUNNER_TEMP, "source-build.key");
      const knownHosts = path.join(process.env.RUNNER_TEMP, "source-build.known_hosts");
      writeFileSync(identity, `${process.env.SOURCE_SSH_KEY.trim()}\n`, { mode: 0o600 });
      try {
        run(
          "icacls.exe",
          [
            identity,
            "/inheritance:r",
            "/grant:r",
            `${process.env.USERDOMAIN}\\${process.env.USERNAME}:F`,
            "/remove:g",
            "*S-1-5-11",
            "*S-1-5-32-545",
            "*S-1-1-0",
          ],
          root,
        );
        const { ssh_keys: hosts } = JSON.parse(gh(["api", "meta"]));
        writeFileSync(knownHosts, hosts.map((host) => `github.com ${host}`).join("\n") + "\n");
        process.env.GIT_SSH_COMMAND = `ssh -i "${identity.replaceAll("\\", "/")}" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${knownHosts.replaceAll("\\", "/")}"`;
        run("git", ["init", "source"], root);
        run("git", ["remote", "add", "origin", `git@github.com:${request.sourceRepository}.git`]);
        run("git", ["fetch", "--depth=1", "origin", request.sourceSha]);
        run("git", ["checkout", "--detach", "FETCH_HEAD"]);
      } finally {
        delete process.env.GIT_SSH_COMMAND;
        rmSync(identity, { force: true });
        rmSync(knownHosts, { force: true });
      }
      return;
    }
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
      if (platform.platform === "win32") {
        run("node", ["scripts/build-cpu-supervisor.mjs"]);
        const probe = spawnSync(
          path.join(source, "apps/cli/dist/cpu-supervisor.exe"),
          ["--probe"],
          { encoding: "utf8", windowsHide: true },
        );
        appendFileSync(
          log,
          `${JSON.stringify({ probeExit: probe.status, probeStdout: probe.stdout, probeStderr: probe.stderr, probeError: probe.error?.message })}\n`,
        );
        if (probe.error || probe.status !== 0 || probe.stdout !== "cpu-supervisor-v2\n")
          throw new Error(
            "Native CPU supervisor probe preflight failed; diagnostics are encrypted.",
          );
        console.log(`${target}: native CPU supervisor preflight passed.`);
      }
      run("pnpm", ["pack:tui"]);
      if (/^Error: AttachConsole failed\r?$/m.test(readFileSync(log, "utf8")))
        throw new Error("ConPTY cleanup emitted an exception; diagnostics are encrypted.");
      run("pnpm", [
        "exec",
        "vitest",
        "run",
        "apps/cli/test/tui-cpu-pressure.test.ts",
        "apps/cli/test/tui-cpu-drain.test.ts",
        "apps/cli/test/tui-cpu-startup-seats.test.ts",
        "apps/cli/test/tui-cpu-feedback.test.ts",
        "apps/cli/test/tui-cpu-seat-directory.test.ts",
        "apps/cli/src/worktree-application-service.test.ts",
        "apps/cli/test/v3-tui-worktree.test.ts",
        "apps/cli/src/dimsdk/core/home-shell-mode.integration.test.ts",
        "apps/cli/src/dimsdk/core/worktree-settings.test.ts",
        "apps/cli/src/dimsdk/pages/HomePage/logic/prompt-layout.test.ts",
        "--maxWorkers=2",
        "--minWorkers=1",
        "--reporter=dot",
      ]);
      run("pnpm", [
        "exec",
        "vitest",
        "run",
        "packages/model-binding-ai-sdk/tests/input-window.test.ts",
        "packages/model-binding-ai-sdk/tests/tool-text-budget.test.ts",
        "packages/model-binding-ai-sdk/tests/tool-call-wire-boundaries.test.ts",
        "--maxWorkers=1",
        "--minWorkers=1",
      ]);
      run("node", ["scripts/experiments/rust-boundaries/bench.mjs", "prepare-node"]);
      const textSemanticsFile = path.join(source, ".tmp/rust-boundaries/text-semantics.json");
      const textResourcesFile = path.join(source, ".tmp/rust-boundaries/text-resources.json");
      run("node", [
        "scripts/experiments/rust-boundaries/bench.mjs",
        "verify-node",
        "nodeFast",
        "text-small",
        textSemanticsFile,
      ]);
      run("node", [
        "scripts/experiments/rust-boundaries/bench.mjs",
        "campaign-node",
        "3",
        "40",
        textResourcesFile,
      ]);
      const textEstimator = {
        status: "passed",
        semantics: JSON.parse(readFileSync(textSemanticsFile, "utf8")),
        ...JSON.parse(readFileSync(textResourcesFile, "utf8")),
      };
      const dir = path.join(source, ".tmp/sea", target);
      const name = `best-agent-${request.version}-${target}.${platform.platform === "win32" ? "zip" : "tar.gz"}`;
      const archive = path.join(dir, name);
      let nativeReadHelper;
      let resourcePairs;
      let nativeLargeReads;
      let largeReadResources;
      let readRegressionResources;
      let readCopyResources;
      if (platform.platform !== "win32") {
        process.env.RUST_READ_HELPER = path.join(source, "apps/cli/dist/workspace-read-helper");
        try {
          run("pnpm", [
            "exec",
            "vitest",
            "run",
            "packages/sandbox-host/tests/rust-read-helper.test.ts",
            "--maxWorkers=1",
            "--minWorkers=1",
          ]);
        } finally {
          delete process.env.RUST_READ_HELPER;
        }
        const installed = path.join(source, ".tmp/native-helper-installed");
        mkdirSync(installed, { recursive: true });
        run("tar", ["-xzf", archive, "-C", installed]);
        const capture = path.join(dir, "native-helper-installed.json");
        run("node", [
          "scripts/experiments/rust-read-helper/installed.mjs",
          path.join(installed, `best-agent-${request.version}-${target}`, "bin", platform.binary),
          "-",
          capture,
        ]);
        const largeInstalled = path.join(dir, "large-read-installed.json");
        const largeBridge = path.join(dir, "large-read-bridge.json");
        run("node", [
          "scripts/experiments/rust-boundaries/installed-large.mjs",
          path.join(installed, `best-agent-${request.version}-${target}`, "bin", platform.binary),
          "-",
          largeInstalled,
        ]);
        run("node", [
          "scripts/experiments/rust-boundaries/installed-large.mjs",
          "bridge",
          "-",
          largeBridge,
        ]);
        nativeLargeReads = {
          installed: JSON.parse(readFileSync(largeInstalled, "utf8")).verification,
          bridge: JSON.parse(readFileSync(largeBridge, "utf8")).verification,
        };
        const largeMeasurements = path.join(dir, "large-read-resources.jsonl");
        process.env.BENCH_WORKLOADS = "full-small,full-unicode,full-escaped,bytes-binaryLimit";
        try {
          run("python3", [
            "-c",
            "import subprocess,sys; f=open(sys.argv[1],'w'); subprocess.run(['python3',sys.argv[2],'3','40'],stdout=f,check=True)",
            largeMeasurements,
            platform.platform === "darwin"
              ? "scripts/experiments/rust-boundaries/resources.py"
              : "scripts/experiments/rust-boundaries/linux-resources.py",
          ]);
        } finally {
          delete process.env.BENCH_WORKLOADS;
        }
        largeReadResources = readFileSync(largeMeasurements, "utf8")
          .trim()
          .split("\n")
          .map((line) => JSON.parse(line))
          .filter((row) => row.arm);
        if (largeReadResources.length !== 24)
          throw new Error("Incomplete large-read resource campaign.");
        for (const workload of new Set(largeReadResources.map((row) => row.workload))) {
          if (
            new Set(
              largeReadResources
                .filter((row) => row.workload === workload)
                .map((row) => row.first.resultHash),
            ).size !== 1
          )
            throw new Error(`Large-read reports differ for ${workload}.`);
        }
        // Build the exact current source with only the read-range writer restored
        // to its prior form, so runner measurements isolate the proposed change.
        const baselineDir = path.join(source, ".tmp/read-regression-baseline");
        const helperDir = path.join(source, "packages/sandbox-host/native/read-helper");
        mkdirSync(path.join(baselineDir, "src"), { recursive: true });
        for (const file of ["Cargo.toml", "Cargo.lock"])
          copyFileSync(path.join(helperDir, file), path.join(baselineDir, file));
        const helperSource = readFileSync(path.join(helperDir, "src/main.rs"), "utf8");
        const candidateWriter = `        if args[2] == "read-range" && report.get("residentError").is_none() {
            let mut output = io::BufWriter::new(io::stdout().lock());
            serde_json::to_writer(&mut output, &report).unwrap();
            output.flush().unwrap();
        } else {
            serde_json::to_writer(io::stdout().lock(), &report).unwrap();
        }`;
        if (helperSource.split(candidateWriter).length !== 2)
          throw new Error("Cannot isolate the prior read-range writer.");
        writeFileSync(
          path.join(baselineDir, "src/main.rs"),
          helperSource.replace(
            candidateWriter,
            "        serde_json::to_writer(io::stdout().lock(), &report).unwrap();",
          ),
        );
        run("cargo", [
          "build",
          "--release",
          "--locked",
          "--manifest-path",
          path.join(baselineDir, "Cargo.toml"),
        ]);
        const regressionMeasurements = path.join(dir, "read-regressions.jsonl");
        process.env.BENCH_BASELINE_HELPER = path.join(
          baselineDir,
          "target/release/best-agent-workspace-read-helper",
        );
        process.env.BENCH_ARMS = "rust-baseline,rust";
        process.env.BENCH_WORKLOADS = "full-small,full-unicode,full-escaped,bytes-binaryLimit";
        try {
          run("python3", [
            "-c",
            "import subprocess,sys; f=open(sys.argv[1],'w'); subprocess.run(['python3',sys.argv[2],'3','40'],stdout=f,check=True)",
            regressionMeasurements,
            platform.platform === "darwin"
              ? "scripts/experiments/rust-boundaries/resources.py"
              : "scripts/experiments/rust-boundaries/linux-resources.py",
          ]);
        } finally {
          delete process.env.BENCH_BASELINE_HELPER;
          delete process.env.BENCH_ARMS;
          delete process.env.BENCH_WORKLOADS;
        }
        readRegressionResources = readFileSync(regressionMeasurements, "utf8")
          .trim()
          .split("\n")
          .map((line) => JSON.parse(line))
          .filter((row) => row.arm);
        if (readRegressionResources.length !== 24)
          throw new Error("Incomplete current-vs-candidate resource campaign.");
        for (const workload of new Set(readRegressionResources.map((row) => row.workload))) {
          if (
            new Set(
              readRegressionResources
                .filter((row) => row.workload === workload)
                .map((row) => row.first.resultHash),
            ).size !== 1
          )
            throw new Error(`Current-vs-candidate reports differ for ${workload}.`);
        }
        const copyMeasurements = path.join(dir, "read-copy-resources.jsonl");
        process.env.BENCH_ARMS = "copy-baseline,rust";
        process.env.BENCH_WORKLOADS = "bytes-small,bytes-binary,bytes-binaryLimit";
        try {
          run("python3", [
            "-c",
            "import subprocess,sys; f=open(sys.argv[1],'w'); subprocess.run(['python3',sys.argv[2],'3','40'],stdout=f,check=True)",
            copyMeasurements,
            platform.platform === "darwin"
              ? "scripts/experiments/rust-boundaries/resources.py"
              : "scripts/experiments/rust-boundaries/linux-resources.py",
          ]);
        } finally {
          delete process.env.BENCH_ARMS;
          delete process.env.BENCH_WORKLOADS;
        }
        readCopyResources = readFileSync(copyMeasurements, "utf8")
          .trim()
          .split("\n")
          .map((line) => JSON.parse(line))
          .filter((row) => row.arm);
        if (readCopyResources.length !== 18)
          throw new Error("Incomplete byte-copy resource campaign.");
        for (const workload of new Set(readCopyResources.map((row) => row.workload))) {
          if (
            new Set(
              readCopyResources
                .filter((row) => row.workload === workload)
                .map((row) => row.first.resultHash),
            ).size !== 1
          )
            throw new Error(`Byte-copy reports differ for ${workload}.`);
        }
        nativeReadHelper = JSON.parse(readFileSync(capture, "utf8")).verification;
        if (nativeReadHelper?.status !== "passed")
          throw new Error("Installed native helper verification receipt is missing.");
        run("node", ["scripts/experiments/rust-read-helper/bench.mjs", "freeze", "current"]);
        run("node", ["scripts/experiments/rust-read-helper/bench.mjs", "prepare"]);
        const measurements = path.join(dir, "read-helper-resources.jsonl");
        process.env.BENCH_WORKLOADS = "small,unicode,list-large,search-sparse";
        try {
          run("python3", [
            "-c",
            "import subprocess,sys; f=open(sys.argv[1],'w'); subprocess.run(['python3',sys.argv[2],'3','100'],stdout=f,check=True)",
            measurements,
            platform.platform === "darwin"
              ? "scripts/experiments/rust-read-helper/resources.py"
              : "scripts/experiments/rust-read-helper/linux-resources.py",
          ]);
        } finally {
          delete process.env.BENCH_WORKLOADS;
        }
        resourcePairs = readFileSync(measurements, "utf8")
          .trim()
          .split("\n")
          .map((line) => JSON.parse(line))
          .filter((row) => row.arm);
        if (resourcePairs.length !== 24)
          throw new Error("Incomplete paired native-helper resource campaign.");
        for (const workload of new Set(resourcePairs.map((row) => row.workload))) {
          const rows = resourcePairs.filter((row) => row.workload === workload);
          if (
            new Set(rows.map((row) => row.first.resultHash)).size !== 1 ||
            new Set(rows.map((row) => row.first.resultBytes)).size !== 1
          ) {
            throw new Error(`Paired native-helper reports differ for ${workload}.`);
          }
        }
      }
      const metadata = {
        sourceSha: request.sourceSha,
        target,
        archive: { name, sha256: digest(archive) },
        report: readFileSync(path.join(dir, "build-report.json"), "utf8"),
        evidence: readFileSync(path.join(dir, "acceptance-evidence.json"), "utf8"),
        standaloneSize: JSON.parse(readFileSync(path.join(dir, "standalone-size.json"), "utf8")),
        ...(nativeReadHelper === undefined ? {} : { nativeReadHelper }),
        textEstimator,
        ...(nativeLargeReads === undefined ? {} : { nativeLargeReads, largeReadResources }),
        ...(resourcePairs === undefined ? {} : { resourcePairs }),
        ...(readRegressionResources === undefined ? {} : { readRegressionResources }),
        ...(readCopyResources === undefined ? {} : { readCopyResources }),
      };
      const sealed = path.join(output, `${target}.metadata.enc`);
      writeFileSync(sealed, seal(Buffer.from(JSON.stringify(metadata)), key()));
      upload(request, [archive, `${archive}.sha256`, sealed]);
      console.log(
        `${target}: installed native dependencies, Node-free TUI interaction and CPU supervisor checks passed.`,
      );
    } else if (mode === "assemble" || mode === "verify") {
      run("pnpm", [
        "exec",
        "vitest",
        "run",
        "scripts/tests/cli-public-distribution.test.ts",
        "--reporter=dot",
      ]);
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
      const standaloneAssets = [];
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
        const size = metadata.standaloneSize;
        if (
          size?.target !== platform.id ||
          size.archiveBytes !== statSync(path.join(downloads, name)).size ||
          !(size.baselineArchiveBytes > size.archiveBytes) ||
          size.retainedBytesAndModesIdentical !== true ||
          size.executableBytesAndModesIdentical !== true ||
          size.pairedRenderingOutputs !== 21 ||
          size.malformedSourceUnchanged !== true ||
          (platform.platform === "win32" && size.pairedConptyText !== true)
        )
          throw new Error(`Missing paired standalone size/render evidence for ${platform.id}.`);
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
        if (JSON.parse(metadata.report).artifact.workspaceReadHelperBytes > 0) {
          copyFileSync(
            path.join(bin, "workspace-read-helper"),
            path.join(dir, "workspace-read-helper"),
          );
        }
        if (
          mode === "verify" &&
          platform.platform !== "win32" &&
          metadata.nativeReadHelper?.status !== "passed"
        ) {
          throw new Error(`Missing native helper execution evidence for ${platform.id}.`);
        }
        if (
          mode === "verify" &&
          platform.platform !== "win32" &&
          (!Array.isArray(metadata.resourcePairs) || metadata.resourcePairs.length !== 24)
        ) {
          throw new Error(`Missing paired native resource evidence for ${platform.id}.`);
        }
        if (
          mode === "verify" &&
          (metadata.textEstimator?.status !== "passed" ||
            metadata.textEstimator.semantics?.cases !== 2556 ||
            metadata.textEstimator.semantics.rawAndProjectionExact !== true ||
            metadata.textEstimator.rows?.length !== 12)
        )
          throw new Error(`Missing text-estimator boundary evidence for ${platform.id}.`);
        if (
          mode === "verify" &&
          platform.platform !== "win32" &&
          (metadata.nativeLargeReads?.installed?.status !== "passed" ||
            metadata.nativeLargeReads.installed.terminalSnapshotExact !== true ||
            metadata.nativeLargeReads.installed.nativeObservedAtRequests?.join(",") !== "2,3" ||
            metadata.nativeLargeReads.bridge?.status !== "passed" ||
            metadata.nativeLargeReads.bridge.reopenedRawStoreExact !== true ||
            metadata.largeReadResources?.length !== 24 ||
            metadata.readRegressionResources?.length !== 24 ||
            metadata.readCopyResources?.length !== 18)
        )
          throw new Error(`Missing large-read boundary evidence for ${platform.id}.`);
        writeFileSync(path.join(dir, "build-report.json"), metadata.report);
        writeFileSync(path.join(dir, "acceptance-evidence.json"), metadata.evidence);
        standaloneAssets.push(name, `${name}.sha256`);
        accepted.push({
          target: platform.id,
          standaloneSha256: metadata.archive.sha256,
          nodeAbsent: true,
          unusableNode: true,
          nativeDependencySmoke: true,
          standaloneSize: metadata.standaloneSize,
          interactiveTui: true,
          cpuSupervisor: true,
          textEstimator: metadata.textEstimator,
          ...(metadata.nativeLargeReads === undefined
            ? {}
            : {
                nativeLargeReads: metadata.nativeLargeReads,
                readRegressionResources: metadata.readRegressionResources,
                readCopyResources: metadata.readCopyResources,
                largeReadResources: metadata.largeReadResources.map((row) => ({
                  workload: row.workload,
                  arm: row.arm,
                  round: row.round,
                  iterations: row.iterations,
                  firstHash: row.first.resultHash,
                  p50Ms: row.p50Ms,
                  p95Ms: row.p95Ms,
                  treeCpuMs: row.treeCpuMs,
                  treeRssPeak: row.treeRssPeak,
                  ...(row.treePssPeak === undefined
                    ? { treeFootprintPeak: row.treeFootprintPeak }
                    : { treePssPeak: row.treePssPeak }),
                })),
              }),
          ...(metadata.nativeReadHelper === undefined
            ? {}
            : { nativeReadHelper: metadata.nativeReadHelper }),
          ...(metadata.resourcePairs === undefined
            ? {}
            : {
                resources: metadata.resourcePairs.map((row) => ({
                  workload: row.workload,
                  arm: row.arm,
                  round: row.round,
                  iterations: row.iterations,
                  p50Ms: row.p50Ms,
                  p95Ms: row.p95Ms,
                  treeCpuMs: row.treeCpuMs,
                  treeRssPeak: row.treeRssPeak,
                  ...(row.unavailableChildSamples === undefined
                    ? {}
                    : { unavailableChildSamples: row.unavailableChildSamples }),
                  ...(row.treePssPeak === undefined
                    ? { treeFootprintPeak: row.treeFootprintPeak }
                    : { treePssPeak: row.treePssPeak }),
                })),
              }),
        });
      }
      run("pnpm", [
        "release:cli",
        "--artifact-root",
        ".tmp/sea",
        "--tag",
        "beta",
        mode === "verify" ? "--verify-only" : "--dry-run",
      ]);
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
        `${JSON.stringify({ version: request.version, sourceSha: request.sourceSha, ...(process.env.VERIFIER_SOURCE_SHA ? { verifierSourceSha: process.env.VERIFIER_SOURCE_SHA } : {}), npmPublished: false, targets: accepted }, null, 2)}\n`,
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
      const expectedAssets = [
        ...standaloneAssets,
        ...files.map((file) => path.basename(file)),
        path.basename(summary),
        path.basename(sums),
      ].sort();
      const actualAssets = JSON.parse(
        gh([
          "release",
          "view",
          request.tag,
          "--repo",
          process.env.GITHUB_REPOSITORY,
          "--json",
          "assets",
        ]),
      )
        .assets.map((asset) => asset.name)
        .sort();
      if (JSON.stringify(actualAssets) !== JSON.stringify(expectedAssets)) {
        appendFileSync(log, `${JSON.stringify({ expectedAssets, actualAssets })}\n`);
        throw new Error(
          "Release asset set does not match the distribution; diagnostics are encrypted.",
        );
      }
      if (mode === "verify") {
        console.log(
          `Six-platform candidate verified; Release remains draft and npm publication is disabled: ${request.tag}`,
        );
        return;
      }
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
    if (mode === "build") {
      const smokes = path.join(source, ".tmp/sea", target, "standalone-smoke");
      if (existsSync(smokes)) {
        const directories = [
          smokes,
          ...readdirSync(smokes, { withFileTypes: true })
            .filter((entry) => entry.isDirectory() && /^(?:no-node|old-node)-/.test(entry.name))
            .map((entry) => path.join(smokes, entry.name)),
        ];
        for (const directory of directories)
          for (const name of [
            "terminal.ansi",
            "requests.json",
            "receipt.json",
            "results.json",
            "summary.json",
          ]) {
            const file = path.join(directory, name);
            if (existsSync(file)) {
              appendFileSync(log, `\n${path.relative(smokes, file)}\n`);
              appendFileSync(log, readFileSync(file));
            }
          }
      }
    }
    const diagnostics = path.join(
      output,
      `${mode === "build" || mode === "checkout" ? target : "assemble"}.log.enc`,
    );
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
