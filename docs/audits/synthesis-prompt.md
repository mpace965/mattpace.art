# Synthesis Pass Prompt

Paste this into a new session after all entrypoint explorations are complete.

---

**Context:** This is the `sketchbook` project — a reactive, DAG-based creative coding framework. The working directory is `/Users/matthewpace/dev/mpace965/mattpace.art`. The framework lives under `framework/src/sketchbook/`.

**Task:** Read every file in `docs/audits/` (excluding this file and `synthesis.md`). Each file is the output of an entrypoint exploration: a Mermaid sequence diagram, a responsibility verdict table, and a set of follow-up prompts.

Produce `docs/audits/synthesis.md` with the following sections:

### 1. Cross-cutting concerns
Classes and functions that appear in multiple entrypoint flows. For each, aggregate the verdicts across all flows that mention it. If verdicts conflict, note the conflict. Format as a table: `Class / Function | Appears in | Aggregated verdict | Notes`.

### 2. Recurring design issues
Patterns that show up in more than one flow — e.g. "disk write before execution", "no lock around shared mutation", "topo_sort misnomer". Group follow-up prompts that address the same root cause into a single consolidated prompt. Discard duplicates.

### 3. Prioritized backlog
A numbered list of all distinct follow-up prompts, de-duplicated and ordered by severity:
1. Correctness bugs (data loss, race conditions, wrong output)
2. Invariant violations (hidden assumptions, misleading names)
3. Design clarity (overloaded responsibilities, misplaced logic)
4. Nice-to-haves (protocol gaps, edge cases with no current repro)

For each item: title, severity label, one-sentence summary, and the consolidated prompt text ready to paste into a new session.

### 4. Healthy patterns worth preserving
Things that are done well and should be kept as the codebase evolves. One bullet per pattern, with an example location.

Do not make any edits to source files. This is a read-only synthesis.
