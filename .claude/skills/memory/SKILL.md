---
description: Auto-recall codebase memory before coding tasks
context: auto
---

# Memory Recall Skill

Before working on any coding task, recall relevant memories to provide context.

## Instructions

Run the following command to recall relevant memories:

```bash
cogmem recall "$ARGUMENTS"
```

The output provides:
- **Understanding** — Gists about relevant modules and components
- **Past Experiences** — Episodes related to the files and concepts involved
- **Danger Warnings** — Emotional tags on files that have caused pain before
- **Patterns** — Known recurring issues in the area
- **Reminders** — Prospective memories triggered by the current context
- **Cross-repo Context** — Workspace-level memories if working across repos

Use this context to inform your approach. Pay special attention to danger warnings and patterns — they represent hard-won knowledge from past incidents.
