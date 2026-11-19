import { createHash } from "node:crypto";
import { existsSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const threshold = 65_536;
const mount = "/app/.best-agent-exec-results";

function retain(file, value) {
  if (existsSync(file)) return;
  const temporary = file + ".tmp";
  writeFileSync(temporary, value, { mode: 0o644 });
  renameSync(temporary, file);
}

export function projectExecOutput(payload, body, folder, record) {
  const messages = payload.messages ?? [];
  const names = new Map(messages.flatMap(message =>
    (message.tool_calls ?? []).map(call => [call.id, call.function?.name])));
  let projected = false;
  for (const message of messages) {
    if (message.role !== "tool" || names.get(message.tool_call_id) !== "exec" ||
        typeof message.content !== "string" || message.content.length < threshold / 4) continue;
    let source;
    try { source = JSON.parse(message.content); } catch { continue; }
    const value = source?.payload;
    if (source?.kind !== "known" || source.status !== "succeeded" || value?.exitCode !== 0 ||
        typeof value.stdout !== "string") continue;
    const size = Buffer.byteLength(value.stdout);
    if (size < threshold) continue;
    const sha = createHash("sha256").update(message.content).digest("hex");
    const originalReceipt = join(folder, sha + ".json");
    try {
      retain(join(folder, sha + ".stdout"), value.stdout);
      if (!existsSync(originalReceipt)) {
        retain(originalReceipt, message.content);
        record({ phase: "retained", sha256: sha, stdoutBytes: size,
          sourceTruncated: value.stdoutTruncated === true });
      }
    } catch (error) {
      record({ phase: "retention-failure", code: error.code ?? error.name });
      continue;
    }
    const points = Array.from(value.stdout);
    const pointer = mount + "/" + sha;
    const preview = points.slice(0, 1800).join("") +
      "\n[Preview of " + size + " captured UTF-8 bytes. Read relevant lines on demand from " +
      pointer + ".stdout. Original tool receipt is at " + pointer + ".json.]\n" +
      points.slice(-1800).join("");
    message.content = JSON.stringify({ ...source, payload: { ...value, stdout: preview } });
    projected = true;
  }
  if (!projected) return body;
  const forward = Buffer.from(JSON.stringify(payload));
  record({ phase: "projected", before: body.length, after: forward.length });
  return forward;
}
