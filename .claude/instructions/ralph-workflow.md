# Ralph Agent Workflow

## Overview
Instructions for autonomous agents implementing user stories.

---

## Start Here

Read `scripts/ralph/CLAUDE.md` for the complete workflow.

---

## Quick Reference

1. Read PRD at `scripts/ralph/prd.json`
2. Read progress log at `scripts/ralph/progress.txt` (check Codebase Patterns first!)
3. Implement ONE user story at a time
4. Run quality checks (tests, typecheck, lint)
5. Commit with format: `feat: [Story ID] - [Story Title]`
6. Update PRD to mark story as `passes: true`
7. Append progress to `progress.txt` with learnings

---

## Important Rules

- Always read the **Codebase Patterns** section in `progress.txt` before starting
- Update CLAUDE.md files when you discover reusable patterns
- Never commit broken code - all commits must pass quality checks
