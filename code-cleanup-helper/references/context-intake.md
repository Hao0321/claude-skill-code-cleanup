# Context intake: classify before loading

Keep an inventory of **host-mandatory**, **startup catalog**, **task-selected detail** and **explicit-only raw memory**. Record owner, cadence, source/hash and measured cost; unknown host injection/billing stays NOT_CHECKED. Do not infer actual request contents from local files alone.

- Startup: names, concise descriptions and paths; not every SKILL/reference body. Keep global/project instructions short and move domain procedures behind existing routes.
- Turn: obey mandatory host reads; select only applicable routes. Do not dump all topics, full indexes, unchanged logs or full JSON receipts into the conversation. Default tool output is a compact receipt; emit text only when needed.
- Resume/new conversation/compaction/task or source change: resolve live authority and select again. A disk receipt is not proof that text remains in the model's context. No skip-mandatory-read cache is provided.
- Raw learning stays local and is retrieved explicitly. Never delete history to lower context costs. Missing/ambiguous routes, critical entry omissions, private/link paths and budget overflows block, not truncate.

From the parent directory containing the two skills:

```sh
# Startup: metadata only; no selected procedure bodies.
python code-cleanup-helper/scripts/context_intake.py run-benchmark-driven-rd --event startup --emit-packet
# Selected detail: keep existing per-file/route limits; packet has a separate ceiling.
python code-cleanup-helper/scripts/context_intake.py run-benchmark-driven-rd --event turn --route rd-context-learning --emit-packet
```

Use `--output <fresh.json> --quiet` for private machine evidence, or omit `--emit-packet` for a summary. Repeat `--route` to combine known routes; shared files emit once. `--event resume` performs a cold selection. The helper reads no transcript and changes no host configuration, hook or background service. Inline scalar frontmatter is supported; unsupported YAML blocks rather than fabricating metadata.

Payload counts are exact `o200k_base` for emitted text only, not the host's full context or bill. Prompt caching is separate; require actual usage/cache telemetry before claiming savings. API cache settings do not automatically control Codex/Claude hosts.

Official sources: [skill disclosure](https://learn.chatgpt.com/docs/build-skills), [AGENTS discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).
