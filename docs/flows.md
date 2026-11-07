# User-defined agent flows

A run follows a **flow**: the research pipeline as data.

1. **Find programmes** (`discover_programs`)
2. **Find faculty** (`research_professor`)
3. **Research each professor** (`research_one_professor`)
4. **Draft outreach** (`draft_email`)

*Standard research* is built in and read-only. Duplicate it in
**Settings → Flows**, then per step you can:

* turn it off (the step's tasks finish immediately as "Skipped"),
* narrow its tools by tool group (#9) and/or individual tools,
* add up to 1,500 characters of instructions.

Pick a flow when starting a run (New run → *Flow*). A run's flow is set
at launch; deleting a flow makes its runs fall back to Standard.

## Guardrails: no privileged paths

All enforcement is in `api/flows/service.py`, applied by the agent loop
(`run_agent_task`) for every task:

* Tool lists are **intersected** with the account's enabled tools and the
  task's allowlist, never widened. A flow can't add a tool you disabled in
  Agents & tools.
* Dispatch enforces exactly the tools the model was shown: a tool name the
  model emits without being offered it is refused ("outside this task's
  allowlist"), not run.
* Each task type has a least-privilege default allowlist
  (`DEFAULT_TASK_TOOLS` in `api/agents/registry.py`). Drafting gets only
  `save_email_draft`; a single-professor task can't save programmes.
* Instructions are appended under a delimited header *after* the built-in
  prompt and can't replace it; the model is told the built-in rules win.
* Budgets, plan quotas (#30) and confirm gates apply exactly as for
  Standard. Flows have no budget fields.
* Fallback chains (#31) sit behind each capability and apply unchanged.

## Failure is actionable

* Saving validates steps (known steps/tools/groups, instruction length,
  at least one research step on) and returns a message naming the problem.
* If a step ends up with no usable tools (e.g. you disabled them after
  saving the flow), its task fails with: *"Flow 'X': step 'Y' allows no
  tools that are enabled for your account. Edit the flow in Settings >
  Flows, or turn the tools back on in Agents & tools."*
