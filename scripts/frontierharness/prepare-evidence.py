from pathlib import Path

source = Path("source/apps/cli/src/v3-attempt-evidence.ts")
original = source.read_text()
edited = original
for old, new in (
    ('import { open, type FileHandle } from "node:fs/promises";',
     'import { open, readFile } from "node:fs/promises";\n'
     'import { request as requestEvidence } from "node:http";'),
    ('  return new AttemptEvidenceWriter(await open(path, "wx"), clock);',
     '  const file = process.env.FH_EVIDENCE_PORT && path === "/logs/agent/best-agent-evidence.jsonl"\n'
     '    ? await openEvidenceEgress()\n'
     '    : await open(path, "wx");\n'
     '  return new AttemptEvidenceWriter(file, clock);'),
    ('readonly #file: FileHandle;',
     'readonly #file: EvidenceOutput;'),
    ('constructor(file: FileHandle, clock: AttemptEvidenceClock',
     'constructor(file: EvidenceOutput, clock: AttemptEvidenceClock'),
    ('export class AttemptEvidenceWriter implements AttemptEvidenceSink {',
     'type EvidenceOutput = {\n'
     '  write(bytes: Buffer): Promise<unknown>;\n'
     '  sync(): Promise<void>;\n'
     '  close(): Promise<void>;\n'
     '};\n\n'
     'export class AttemptEvidenceWriter implements AttemptEvidenceSink {'),
):
    if edited.count(old) != 1:
        raise SystemExit(f"Pinned evidence writer changed at {old}")
    edited = edited.replace(old, new)

egress = Path(__file__).with_name("ci-evidence-egress.ts").read_text()
source.write_text(edited + "\n" + egress)
