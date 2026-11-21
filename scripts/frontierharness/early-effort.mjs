const fileTools = new Set(["write", "edit", "apply_patch"]);

export function createEarlyEffortPolicy(profile, digest) {
  const rootUserByTag = new Map();
  const reachedFileOperation = new Set();
  return (tag, payload) => {
    const messages = payload.messages ?? [];
    const user = messages.find((message) => message.role === "user");
    if (tag === "preflight" || !user || !payload.tools?.length) {
      return { root: false, effort: payload.reasoning_effort };
    }
    const userId = digest(user.content);
    if (!rootUserByTag.has(tag)) rootUserByTag.set(tag, userId);
    const root = rootUserByTag.get(tag) === userId;
    if (root && messages.some((message) =>
      message.tool_calls?.some((call) => fileTools.has(call.function?.name)))) {
      reachedFileOperation.add(tag);
    }
    const early = !reachedFileOperation.has(tag);
    const effort = profile === "short-early-high" && payload.reasoning_effort === "max" && root && early
      ? "high"
      : payload.reasoning_effort;
    return { root, early, effort };
  };
}
