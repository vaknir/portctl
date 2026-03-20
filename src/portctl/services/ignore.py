"""Parse and apply .portctlignore rules for filtering resources.

The .portctlignore file uses a syntax inspired by .gitignore:
- Blank lines and lines starting with ``#`` are ignored.
- Patterns containing ``/`` are split into ``resource_type/glob_pattern``.
- Patterns without ``/`` match any resource type.
- A ``!`` prefix negates the rule (un-ignores a previously matched resource).
- Last matching rule wins, just like .gitignore.
- Standard glob characters ``*``, ``?``, ``[seq]``, ``[!seq]`` are supported.
"""

from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from portctl.constants import IGNORE_FILE

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class IgnoreRule:
    """A single parsed ignore rule.

    Attributes:
        pattern: The glob pattern to match against resource identifiers.
        negated: True if the rule was prefixed with ``!`` (un-ignore).
        resource_type: Optional resource type prefix (e.g. ``"blueprints"``).
            When None, the rule matches any resource type.
    """

    pattern: str
    negated: bool = False
    resource_type: str | None = None


@dataclass
class IgnoreFilter:
    """Compiled set of ignore rules. Immutable after creation.

    Evaluates rules in order; the last matching rule wins (like .gitignore).
    """

    rules: list[IgnoreRule] = field(default_factory=list)

    def is_ignored(self, resource_type: str, identifier: str) -> bool:
        """Check if a resource should be ignored.

        Matching is performed against ``{resource_type}/{identifier}`` paths.
        The last matching rule wins: if it is negated the resource is kept,
        otherwise it is ignored.

        Args:
            resource_type: The resource type (e.g. ``"blueprints"``).
            identifier: The resource identifier.

        Returns:
            True if the resource should be ignored.
        """
        result = False
        for rule in self.rules:
            # Skip rules that target a different resource type
            if rule.resource_type is not None and rule.resource_type != resource_type:
                continue

            if fnmatch.fnmatch(identifier, rule.pattern):
                result = not rule.negated

        return result

    def filter_identifiers(
        self, resource_type: str, identifiers: list[str]
    ) -> list[str]:
        """Return only non-ignored identifiers from the list.

        Args:
            resource_type: The resource type (e.g. ``"blueprints"``).
            identifiers: List of resource identifiers to filter.

        Returns:
            A new list containing only identifiers that are not ignored.
        """
        return [
            ident
            for ident in identifiers
            if not self.is_ignored(resource_type, ident)
        ]


def parse_ignore_file(content: str) -> list[IgnoreRule]:
    """Parse .portctlignore file content into rules.

    Syntax rules:
    - Blank lines are ignored.
    - Lines starting with ``#`` (after stripping whitespace) are comments.
    - A ``!`` prefix marks a negation rule.
    - Patterns containing ``/`` are split as ``resource_type/glob_pattern``.
    - Patterns without ``/`` match against the identifier only (any type).
    - Standard glob: ``*``, ``?``, ``[seq]``, ``[!seq]``.

    Args:
        content: Raw text content of a .portctlignore file.

    Returns:
        Ordered list of parsed IgnoreRule instances.
    """
    rules: list[IgnoreRule] = []

    for line in content.splitlines():
        line = line.strip()

        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue

        negated = False
        if line.startswith("!"):
            negated = True
            line = line[1:]

        resource_type: str | None = None
        pattern = line

        if "/" in line:
            resource_type, pattern = line.split("/", 1)

        rules.append(
            IgnoreRule(pattern=pattern, negated=negated, resource_type=resource_type)
        )

    return rules


def load_ignore_filter(project_dir: Path) -> IgnoreFilter:
    """Load .portctlignore from project directory.

    If the file does not exist, returns an empty filter that ignores nothing.

    Args:
        project_dir: Directory to search for the .portctlignore file.

    Returns:
        An IgnoreFilter with parsed rules, or an empty filter if the file
        is missing.
    """
    ignore_path = project_dir / IGNORE_FILE

    if not ignore_path.is_file():
        return IgnoreFilter()

    content = ignore_path.read_text(encoding="utf-8")
    rules = parse_ignore_file(content)

    if rules:
        logger.debug("Loaded %d ignore rules from %s", len(rules), ignore_path)

    return IgnoreFilter(rules=rules)
