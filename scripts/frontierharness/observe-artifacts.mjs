import { lstatSync, renameSync, writeFileSync } from "node:fs";
import { performance } from "node:perf_hooks";

const [parent, ledger, ...paths] = process.argv.slice(2);

function snapshot(file) {
  try {
    const stat = lstatSync(file);
    if (!stat.isFile()) return null;
    return { inode: stat.ino, bytes: stat.size, modified: stat.mtimeMs };
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

const baseline = new Map(paths.map(file => [file, snapshot(file)]));
const start = performance.now();
const first = {};

function persist() {
  const temporary = ledger + ".tmp";
  writeFileSync(temporary, JSON.stringify({ paths, poll_ms: 200, first }), { mode: 0o644 });
  renameSync(temporary, ledger);
}

function measure() {
  let changed = false;
  for (const file of paths) {
    if (Object.hasOwn(first, file)) continue;
    const current = snapshot(file);
    if (!current?.bytes) continue;
    const previous = baseline.get(file);
    if (previous && current.inode === previous.inode &&
        current.modified === previous.modified && current.bytes === previous.bytes) continue;
    first[file] = {
      elapsed_ms: Math.round(performance.now() - start), bytes: current.bytes,
      kind: previous ? "changed" : "created",
    };
    changed = true;
  }
  if (changed) persist();
}

persist();
const timer = setInterval(() => {
  measure();
  try {
    process.kill(Number(parent), 0);
  } catch (error) {
    if (error.code !== "ESRCH") throw error;
    clearInterval(timer);
  }
}, 200);
