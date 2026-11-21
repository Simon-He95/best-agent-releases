const diagnosticUse = " For conflicting observations, the task can request one independent, read-only check that distinguishes two explanations, with a concise evidence report and no edits.";

export function projectDiagnosticTools(tools, profile) {
  if (profile !== "short-independent-diagnosis" || !tools?.some((tool) => tool.function?.name === "subagent")) {
    return tools;
  }
  return tools.map((tool) => tool.function?.name === "subagent" ? {
    ...tool,
    function: { ...tool.function, description: tool.function.description + diagnosticUse },
  } : tool);
}
