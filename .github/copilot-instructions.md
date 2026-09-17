# Copilot instructions for this workspace

Use the Caveman skill by default for all coding tasks in this workspace.

## Default behavior
- Keep Caveman enabled unless the user explicitly asks to disable it.
- Default to the `caveman` skill for routine coding work, iterative edits, and quick answers.
- Maintain the default Caveman mode unless a task or user request requires a different mode.

## Skill routing
- Use `investigate-first` for debugging, unclear failures, or ambiguous root-cause analysis.
- Use `lean-build` for new implementation work and feature development.
- Use `surgical-patch` for small, targeted fixes.
- Use `safe-refactor` for restructuring or cleanup that must preserve behavior.
- Use `verify-and-stop` after implementation to validate the result and stop once the acceptance checks pass.
- Use `caveman-review` for code review and short reviewer feedback.

## Working style
- Prefer concise, direct responses consistent with Caveman mode.
- Keep the user’s language unless they explicitly request otherwise.
- Do not disable Caveman mode by default; only disable it when the user explicitly asks.
