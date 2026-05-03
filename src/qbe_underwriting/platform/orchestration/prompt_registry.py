from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

PROMPTS_ROOT = Path(__file__).resolve().parents[4] / "prompts"


class PromptTemplate:
    def __init__(self, agent: str, version: str, metadata: dict, body: str) -> None:
        self.agent = agent
        self.version = version
        self.metadata = metadata
        self._body = body

    def render(self, **variables: str) -> str:
        """Replace {{VAR_NAME}} placeholders with provided values."""
        result = self._body
        for key, value in variables.items():
            result = result.replace("{{" + key.upper() + "}}", str(value))

        missing = re.findall(r"\{\{([A-Z_]+)\}\}", result)
        if missing:
            raise ValueError(
                f"Prompt '{self.agent}' v{self.version} has unresolved variables: {missing}"
            )
        return result

    @property
    def input_variables(self) -> list[str]:
        return [v.split(":")[0].strip() for v in self.metadata.get("input_variables", [])]

    @property
    def output_schema(self) -> str:
        return self.metadata.get("output_schema", "")

    def __repr__(self) -> str:
        return f"<PromptTemplate agent={self.agent!r} version={self.version!r}>"


class PromptRegistry:
    """
    Loads versioned prompt templates from the prompts/ directory.

    Usage:
        prompt = PromptRegistry.load("document-ingestion-agent")
        rendered = prompt.render(
            submission_id="SUB-001",
            document_content="<raw ocr text>"
        )
    """

    @staticmethod
    @lru_cache(maxsize=64)
    def load(agent: str, version: str = "latest") -> PromptTemplate:
        agent_dir = PROMPTS_ROOT / agent
        if not agent_dir.exists():
            raise FileNotFoundError(f"No prompts directory found for agent: '{agent}'")

        if version == "latest":
            path = PromptRegistry._resolve_latest(agent_dir)
        else:
            path = agent_dir / f"v{version}.md"
            if not path.exists():
                raise FileNotFoundError(
                    f"Prompt version '{version}' not found for agent '{agent}'"
                )

        return PromptRegistry._parse(agent, path)

    @staticmethod
    def _resolve_latest(agent_dir: Path) -> Path:
        candidates = sorted(
            agent_dir.glob("v*.md"),
            key=lambda p: [int(x) for x in p.stem[1:].split(".")],
        )
        active = [
            p for p in candidates
            if PromptRegistry._read_status(p) == "active"
        ]
        if not active:
            raise RuntimeError(
                f"No active prompt version found in {agent_dir}"
            )
        return active[-1]

    @staticmethod
    def _read_status(path: Path) -> str:
        content = path.read_text(encoding="utf-8")
        match = re.search(r"^status:\s*(\w+)", content, re.MULTILINE)
        return match.group(1) if match else "unknown"

    @staticmethod
    def _parse(agent: str, path: Path) -> PromptTemplate:
        content = path.read_text(encoding="utf-8")

        # Split frontmatter (between --- markers) from prompt body
        parts = content.split("---", maxsplit=2)
        if len(parts) < 3:
            raise ValueError(f"Prompt file {path} is missing YAML frontmatter")

        metadata = yaml.safe_load(parts[1])
        body = parts[2].strip()
        version = str(metadata.get("version", path.stem[1:]))

        return PromptTemplate(
            agent=agent,
            version=version,
            metadata=metadata,
            body=body,
        )

    @staticmethod
    def list_versions(agent: str) -> list[dict]:
        """Return all versions for an agent with their status."""
        agent_dir = PROMPTS_ROOT / agent
        if not agent_dir.exists():
            return []
        results = []
        for path in sorted(agent_dir.glob("v*.md")):
            content = path.read_text(encoding="utf-8")
            parts = content.split("---", maxsplit=2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1])
                results.append({
                    "version": meta.get("version"),
                    "status": meta.get("status"),
                    "created": meta.get("created"),
                    "changed": meta.get("changed"),
                })
        return results
