from pathlib import Path

TARGET = Path("source/packages/capability-process-tools/src/index.ts")

HEAD = (
    "Accepted means started, not completed; use process-read with the returned handle (or the same "
    "processRef) to observe the actual exit and bounded stdout/stderr. "
)
BASELINE_SENTENCE = "A running report calls for another observation, not another start. "
CANDIDATE_SENTENCE = (
    "A running report calls for another observation of that same process, not a second start of it; "
    "a different, independent job may be started while another is still running. "
)
TAIL = "The Application selects its process environment and isolation. "

OLD = f'"{HEAD}{BASELINE_SENTENCE}{TAIL}" +'
NEW = (
    "(process.env.BEST_AGENT_BENCHMARK_INDEPENDENT_JOBS === \"1\""
    f' ? "{HEAD}{CANDIDATE_SENTENCE}{TAIL}"'
    f' : "{HEAD}{BASELINE_SENTENCE}{TAIL}") +'
)

# Both arms share one bundle and one prompt: the candidate arm changes exactly one sentence of the
# start definition, through the environment the runner wrapper sets for that arm alone. The archived
# runs never once overlapped two process operations (peak concurrency 1 in all 24 runs that used the
# process tools), including a task whose wall clock is 83% waiting on independent fits, so the
# current wording's "another observation, not another start" is the behavior under test.
original = TARGET.read_text()
if original.count(OLD) != 1:
    raise SystemExit(f"Pinned start-definition literal changed in {TARGET.name}")
TARGET.write_text(original.replace(OLD, NEW, 1))
