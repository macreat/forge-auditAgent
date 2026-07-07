---
name: skill-creator
description: Create new Agent Skills in the open .agents/skills/ format (a folder with a SKILL.md file). Use when asked to create, scaffold, write, or package a new "skill", "agent skill", or "SKILL.md" file, or to turn a workflow/instructions into a reusable skill.
---

Use this skill to scaffold a new Agent Skill that follows the open
agentskills.io specification, so it works in VS Code, Claude Code, Codex,
Gemini CLI, and other compatible agents.

## 1. Gather what the skill needs to do

Before writing anything, figure out:

- **The task**: what capability should this give the agent?
- **The trigger phrases**: what would a user say that should activate it?
- **The steps/knowledge**: what does the agent need to know or do to complete
  the task (commands, workflows, gotchas, references)?
- **Any resources**: does it need bundled scripts, reference docs, or asset
  templates?

If any of this is unclear, ask before scaffolding — a vague skill won't
activate reliably.

## 2. Choose the folder and name

Create the skill at:

```
.agents/skills/<skill-name>/SKILL.md
```

`<skill-name>` rules (must match the `name` frontmatter field exactly):

- lowercase letters, numbers, and hyphens only
- max 64 characters
- must not start or end with a hyphen
- no consecutive hyphens

## 3. Write the frontmatter

Required fields only need `name` and `description`. Optional fields
(`license`, `metadata`, etc.) may be added but keep it minimal unless asked.

```yaml
---
name: <skill-name>
description: <what it does> + <when to use it>
---
```

**The description is the single most important part of the skill.** The
agent only sees `name` + `description` at discovery time — the body isn't
loaded until the skill activates. A weak description means the skill never
triggers, no matter how good the instructions are.

- Describe **both** what the skill does and when to use it.
- Include concrete trigger words/phrases the user is likely to type.
- Max 1024 characters. Be specific, not generic ("Roll dice using a random
  number generator. Use when asked to roll a die (d6, d20, etc.)" — not
  "Helps with dice.").
- Avoid `<` or `>` anywhere in the frontmatter — they can be misread as
  injected instructions.

## 4. Write the body

The body is plain Markdown with no required structure, but this shape works
well:

1. One-line restatement of what the skill does.
2. Numbered steps or a clear workflow the agent should follow.
3. Concrete examples, commands, or code snippets.
4. Edge cases / common mistakes to avoid.

Guidelines:

- Keep the whole `SKILL.md` under ~500 lines (ideally under ~5000 tokens) —
  the full body loads into context every time the skill activates.
- Be specific and prescriptive. Prefer "check X, then run Y, then verify Z"
  over vague advice like "handle it carefully."
- If the instructions are long, split detail into `references/*.md` and
  link to them with a relative path (one level deep only — don't chain
  references to references).
- Put executable code in `scripts/` (Python, Bash, or JS are safest bets for
  cross-agent support) and document any dependencies inline.
- Put templates/sample files in `assets/`.

Folder layout when the skill needs bundled resources:

```
.agents/skills/<skill-name>/
├── SKILL.md              # required
├── scripts/              # optional: executable code
├── references/           # optional: docs loaded on demand
└── assets/                # optional: templates, resources
```

## 5. Validate before finishing

Check the finished skill against this list:

- [ ] Path is `.agents/skills/<skill-name>/SKILL.md`
- [ ] `name` matches the folder name exactly and follows the naming rules
- [ ] `description` states both what it does and when to use it
- [ ] No `<` / `>` characters in the frontmatter
- [ ] Body is instructional and specific, not just a restatement of the
      description
- [ ] Long reference material is split out of the main body, not inlined
- [ ] Any scripts are self-contained or their dependencies are documented

## 6. Example: minimal skill

```markdown
---
name: roll-dice
description: Roll dice using a random number generator. Use when asked to roll a die (d6, d20, etc.), roll dice, or generate a random dice roll.
---

To roll a die, generate a random number from 1 to the given number of sides:

​```bash
echo $((RANDOM % <sides> + 1))
​```

Replace `<sides>` with the number of sides on the die (e.g., 6 for a
standard die, 20 for a d20).
```

That's the whole thing — one file, under 20 lines, correctly triggered by
a specific description.

## Common mistakes to avoid

- **Generic descriptions** ("Helps with documents") that never win the
  match against the user's actual phrasing.
- **Name/folder mismatch** — the skill silently fails to load.
- **Dumping everything in SKILL.md** instead of splitting long reference
  material into `references/`, bloating every activation.
- **Skipping the "when to use it" half** of the description — agents match
  on triggers, not just topic.