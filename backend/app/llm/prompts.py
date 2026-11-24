"""Load versioned prompt templates from `backend/prompts/`.

File name: `<name>.v<version>.md`. Layout:

    ---
    name: extract_pain_points
    version: 1
    description: ...
    ---
    ## system
    ...instructions...
    ## user
    ...text with {{placeholders}}...

Placeholders use `{{name}}` so JSON examples with single braces need no escaping.
Rendering fails loudly on a missing or unused variable.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from app.llm.base import Message

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

_SECTION = re.compile(r"^##[ \t]+(system|user)[ \t]*$", re.MULTILINE | re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
_FILE = re.compile(r"^(?P<name>[a-z0-9_]+)\.v(?P<version>\d+)\.md$")


class PromptError(ValueError):
    pass


class PromptTemplate(BaseModel):
    name: str
    version: int
    description: str = ""
    system: str
    user: str

    @property
    def id(self) -> str:
        """Stable identifier recorded in run logs, e.g. `extract_pain_points.v1`."""
        return f"{self.name}.v{self.version}"

    @property
    def variables(self) -> set[str]:
        return set(_PLACEHOLDER.findall(self.system)) | set(_PLACEHOLDER.findall(self.user))

    def render(self, **values: object) -> list[Message]:
        missing = self.variables - values.keys()
        extra = values.keys() - self.variables
        if missing or extra:
            raise PromptError(
                f"{self.id}: missing variables {sorted(missing)}, unexpected {sorted(extra)}"
            )

        def fill(text: str) -> str:
            return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]), text)

        return [
            Message(role="system", content=fill(self.system)),
            Message(role="user", content=fill(self.user)),
        ]


def parse_prompt(text: str, *, name: str, version: int) -> PromptTemplate:
    meta: dict[str, str] = {}
    body = text.replace("\r\n", "\n")
    if body.startswith("---\n"):
        head, sep, rest = body[4:].partition("\n---\n")
        if sep:
            for line in head.splitlines():
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
            body = rest
    parts = _SECTION.split(body)
    sections = {parts[i].lower(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    if not sections.get("system") or not sections.get("user"):
        raise PromptError(f"{name}.v{version}: needs non-empty '## system' and '## user' sections")
    return PromptTemplate(
        name=name,
        version=version,
        description=meta.get("description", ""),
        system=sections["system"],
        user=sections["user"],
    )


def available_versions(name: str, directory: Path = PROMPTS_DIR) -> list[int]:
    return sorted(
        int(m.group("version"))
        for p in directory.glob(f"{name}.v*.md")
        if (m := _FILE.match(p.name)) and m.group("name") == name
    )


@lru_cache
def load_prompt(
    name: str, version: int | None = None, directory: Path = PROMPTS_DIR
) -> PromptTemplate:
    """Load a prompt; without `version`, the highest available version."""
    versions = available_versions(name, directory)
    if not versions:
        raise PromptError(f"No prompt named '{name}' in {directory}")
    version = version if version is not None else versions[-1]
    path = directory / f"{name}.v{version}.md"
    if not path.is_file():
        raise PromptError(f"Prompt {name}.v{version} not found (available: {versions})")
    return parse_prompt(path.read_text(encoding="utf-8"), name=name, version=version)
