# Prompt Templates — AI-Underwriting-System

## Convention

Each agent has its own folder under `prompts/`. Prompts are versioned files — never hardcoded in agent code.

## Folder Structure

```
prompts/
├── README.md                        ← this file
├── document-ingestion-agent/
│   ├── v1.0.md                      ← first version
│   └── v1.1.md                      ← current (if updated)
├── claims-history-agent/
├── hazard-evaluation-agent/
├── underwriting-risk-agent/
├── pricing-agent/
└── governance_agent/
```

## Prompt File Format

Every prompt file must have this structure:

```
---
version: 1.0
agent: <agent-name>
status: active | deprecated
created: YYYY-MM-DD
changed: what changed from previous version and why
input_variables:
  - VAR_NAME: description
output_schema: <schema class name in pipeline/<agent>/schemas.py>
---

<system prompt content below>
```

## Rules

1. **Never hardcode prompts in agent code.** Agent code loads prompts via `PromptRegistry`.
2. **Never delete old versions.** Mark them `status: deprecated` and keep the file.
3. **Every change needs a `changed:` entry.** Future you needs to know why it changed.
4. **Prompt variables use `{{UPPER_SNAKE_CASE}}` syntax.** Easy to spot, easy to validate.
5. **Document content is always wrapped in `<broker_document>` tags.** Never interpolated raw.
6. **Every prompt file must have a corresponding test** in the agent's test suite.

## Loading a Prompt in Code

```python
from src/underwriting/platform.orchestration.prompt_registry import PromptRegistry

# Load latest active version
prompt = PromptRegistry.load("document-ingestion-agent")

# Load specific version (for reproducibility in audit logs)
prompt = PromptRegistry.load("document-ingestion-agent", version="1.0")

# Render with variables
rendered = prompt.render(
    class_of_business="property",
    submission_id="SUB-2024-00821"
)
```

## Why This Matters

The cost ledger records the prompt version used on every LLM call.
If a prompt change causes a cost spike or quality regression, you can pinpoint
exactly which version caused it and roll back by changing one line of config.
