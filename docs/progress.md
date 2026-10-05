# Progress log

One entry per stage or handed-back task, latest last. Format is in `.agents/skills/stage/SKILL.md`.

## Stage 00: design handoff

**Done:** architecture, critique, staged plan with acceptance checks, agent instructions, hooks, skills, Stand's harness and source material copied in unmodified.
**Not done:** no application code exists. Stage 1 starts from an empty `src/`.
**Checks:** `python3 scripts/check_discipline.py` passes on the handoff files. The handoff went through three rounds of four-lens review with a cross-model panel each round; the last round found no blocker.
**Friction:** none recorded.
**Next:** Stage 1, first task. Read `docs/architecture.md` in full before starting. Stage 3 has a human gate: Brett reviews every interpretation row in architecture section 9.7 and signs the ten lead labels.

## Stage 01, task 2: SDK and library verification (stage-01-scaffold-t0)

Checked on 2026-10-05 against Anthropic's documentation and the versions pinned in `uv.lock`: anthropic 1.11.0, httpx2 2.13.1, starlette 1.7.0. No live model call was made; the three API findings rest on the documentation and are unverified against the live API until stage 9 records an exchange.

1. **Structured output.** `client.messages.parse(model=..., max_tokens=..., messages=..., output_format=<Pydantic model>)` returns a response whose `parsed_output` is a validated instance of the model. No beta header is needed, and `claude-sonnet-5-5` is on the supported-model list. A `refusal` or `max_tokens` stop reason can leave the output off-schema, so `read_reply` checks `stop_reason` before reading `parsed_output` (A.10 maps `refusal` to the typed abstention). Source: https://platform.claude.com/docs/en/build-with-claude/structured-outputs. The installed SDK agrees: `inspect.signature(Anthropic(api_key="x").messages.parse)` lists `output_format` and `output_config`. Confidence: high.
2. **Forced `tool_choice`.** `claude-sonnet-5-5` rejects `tool_choice` of type `any` or `tool` with a 400, `tool_choice: type "tool" and "any" are not supported for this model.` §6.2 stands: structured outputs are used and forced `tool_choice` is not. Source: https://platform.claude.com/docs/en/models/sonnet-5-5/migration-guide, section "Forced tool use is not supported". Confidence: high.
3. Sampling parameters accepted by claude-sonnet-5-5: none at a non-default value. The guide says "On Claude Sonnet 5.5, a non-default value returns a 400 error" for `temperature`, `top_p` and `top_k`. `read_reply` sends none (A.10), and `messages.parse` in anthropic 1.11.0 has no `temperature`, `top_p` or `top_k` argument (same `inspect.signature` call). Source: the same migration guide, section "Migrating to Claude Sonnet 5.5 from Claude Sonnet 4.6 and earlier Sonnet models", Breaking changes. Confidence: high. Consequence for the evals: repeat agreement in the Reply reading grader (§13.3) cannot be bought with temperature 0; it has to come from the prompt and the schema.
4. **Test client.** Starlette's `TestClient` is an `httpx2.Client`: its MRO is `starlette.testclient.TestClient`, `httpx2.Client`, `httpx2._client.BaseClient`, `object`, and `TestClient(Starlette())` built under `python -W error` with `warnings.catch_warnings(record=True)` recorded no warning. Shown by `uv run python -W error` on the installed starlette 1.7.0 and httpx2 2.13.1. anthropic 1.11.0 itself depends on `httpx2<3,>=2.0.0`, so the app has one HTTP client library. Confidence: high.
