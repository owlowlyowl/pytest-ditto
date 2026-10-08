# Coding Agent Skill

The repository includes a portable `pytest-ditto` skill for coding agents that
write snapshot tests, diagnose mismatches, and maintain baselines. It teaches
recorder and assertion choices, when a baseline change is justified, and how
test execution, `ditto.lock`, and storage interact.

The skill describes the 2.x implementation in the checkout it comes from.
Use a checkout or tag matching your installed version, and check its command
help for available flags. Installing the skill does not install pytest-ditto or
any recorder plugin.

## Install the skill

Get the [repository](https://github.com/owlowlyowl/pytest-ditto) and copy the
whole `skills/pytest-ditto/` directory, including its references, into a skill
location supported by your harness. The bundle is distributed in Git; installing
the Python package with pip does not install it into an agent's configuration.

| Harness | Project skill directory | Personal skill directory |
| --- | --- | --- |
| [Codex](https://learn.chatgpt.com/docs/build-skills) | `.agents/skills/` | `~/.agents/skills/` |
| [Claude Code](https://code.claude.com/docs/en/skills) | `.claude/skills/` | `~/.claude/skills/` |
| [GitHub Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills) | `.agents/skills/`, `.github/skills/`, or `.claude/skills/` | `~/.agents/skills/` or `~/.copilot/skills/` |
| [Gemini CLI](https://geminicli.com/docs/cli/skills/) | `.agents/skills/` or `.gemini/skills/` | `~/.agents/skills/` or `~/.gemini/skills/` |

For example, from this checkout, a POSIX shell can install a personal skill
shared by Codex, Copilot, and Gemini CLI:

```bash
mkdir -p ~/.agents/skills
cp -R skills/pytest-ditto ~/.agents/skills/
```

For Claude Code, use `~/.claude/skills/` as the destination. For a project skill,
copy the bundle into that project's chosen directory and commit it. Check an
existing installation before copying over it. When updating, replace the whole
bundle so the entrypoint and references stay together.

Check your harness's skill list after installation. Discovery and activation
depend on its version and configuration. For a harness without native skill
discovery, add a pointer in its repository instructions to read
`skills/pytest-ditto/SKILL.md` when working with pytest-ditto, and make the whole
bundle available in that checkout.

## Use the skill

The description allows automatic selection for tasks that use or explicitly
request pytest-ditto. You can also select it explicitly: `$pytest-ditto` in
Codex or `/pytest-ditto` in Claude Code. For example:

```text
Use the pytest-ditto skill to add snapshot coverage for this response schema.
Preserve the project's existing recorder and storage configuration.
```

The agent should use the project's existing test environment. The skill has no
MCP dependency, harness-specific tool grants, or embedded shell execution.
It does not grant permissions beyond your request and harness configuration.

## Maintain the skill

`SKILL.md` contains the shared decisions and constraints. Its references are
loaded when a task needs recorder details, ownership maintenance, or backend
configuration. Optional `agents/openai.yaml` supplies Codex display metadata;
other harnesses can use the same Markdown bundle.

When changing the skill, validate the frontmatter and relative links, then check
its examples and commands against the matching implementation in disposable
projects. Useful behavioral cases include a new JSON baseline, an intended
update, an unexplained mismatch, tabular comparisons, missing remote credentials,
and cleanup with pytest-xdist configured. Evaluate the edits, command scope, and
results rather than matching particular wording. A format validator alone does
not establish that an agent will make the right decisions.

Keep one source bundle in `skills/pytest-ditto/` and update installed copies
together. Include additional scripts or references when a demonstrated workflow
needs them. The format follows the [Agent Skills specification](https://agentskills.io/specification).
