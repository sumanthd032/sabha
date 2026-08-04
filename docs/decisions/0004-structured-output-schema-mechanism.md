# 0004: response_json_schema over response_schema for structured output

## Context

Section 4.2 mandates structured output on every generation call, and
the SDK offers two ways to ask for it. `response_schema` takes a
`genai.types.Schema` object, a select subset of OpenAPI 3.0 that does
not support `$ref` or `$defs`. `response_json_schema` takes a plain
JSON Schema document and supports both. Every schema in
`llm/schemas.py` is a nested `SQLModel`, chosen so the shapes exchanged
with the model are typed the same way the rest of the codebase types
its data, and `SQLModel.model_json_schema()` emits standard JSON Schema
with `$defs` and `$ref` for any nested model, which is exactly the
shape `response_schema` cannot take.

## Decision

`llm/client.call_structured` always calls `model_json_schema()` on the
caller's schema class and passes the result as `response_json_schema`,
never as `response_schema`. The reply's raw text is parsed with
`json.loads` and validated with the schema class's own
`model_validate`, rather than relying on the SDK's automatic `.parsed`
field, since that field's recognition of a `SQLModel` subclass as a
Pydantic model is undocumented behaviour this build has no reason to
depend on when parsing the JSON by hand is one line.

## Consequence

Every structured schema in this codebase can nest freely, a batch of N
results in one named field rather than a flat list, without hitting
the older mechanism's inability to express that. The cost is that a
schema change is a one line edit to `llm/schemas.py` with no
corresponding hand written `types.Schema`, which is the point: nobody
maintains two descriptions of the same shape.
