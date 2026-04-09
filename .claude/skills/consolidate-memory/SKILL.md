---
description: Consolidate and strengthen codebase memories
context: fork
agent: Explore
---

# Memory Consolidation Skill

Run periodic consolidation to compress old episodes, extract patterns, update gists, and prune stale memories.

## Instructions

1. Run consolidation:
```bash
cogmem consolidate --scope full
```

2. If the output mentions a pending consolidation prompt, read the prompt file and process it:
   - Analyze the episodes listed in the prompt
   - Identify cross-repo patterns, gist updates, and danger zones
   - Write the results as JSON to a temporary file
   - Apply the results:
```bash
cogmem consolidate --apply <result_file>
```

3. Run decay to update memory strengths:
```bash
cogmem decay
```

4. Report a summary of what changed.
