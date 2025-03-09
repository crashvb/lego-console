#!/usr/bin/env python

"""Helper class to handle aliases."""

import logging
from typing import Dict, IO, List, Optional, Protocol

LOGGER = logging.getLogger(__name__)


class TypingPrint(Protocol):
    # pylint: disable=missing-class-docstring,too-few-public-methods
    def __call__(
        self, *args, sep: str, end: str, file: Optional[IO[str]], flush: bool
    ): ...


class AliasHelper:
    # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """Helper class to handle aliases."""

    def __init__(self, *args, aliases: Dict[str, List[str]] = None, **kwargs):
        # pylint: disable=unused-argument

        # alias value -> list of alias names
        self.aliases = aliases if aliases else {}

    def get(self) -> Dict[str, str]:
        """
        Retrieves a dictionary containing all aliases.

        Returns:
            A flat dictionary containing all aliases.
        """
        result = {}
        for value, names in self.aliases.items():
            for name in names:
                result[name] = value
        return result

    def resolve(self, *, line: str) -> Optional[str]:
        """
        Resolves aliases within a line.
        Args:
            line: The line containing a potential alias.

        Returns:
            The line with the alias resolved.
        """
        args = line.split() if line else None
        if args:
            cmd = [k for k, v in self.aliases.items() if args[0] in v]
            if cmd:
                args[0] = cmd[0]
                return " ".join(args)
        return None
