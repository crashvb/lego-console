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

    def get_all(self) -> Dict[str, str]:
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

    def get_names(self, *, value: str) -> List[str]:
        """
        Retrieves a list of alias names by value.

        Args:
            value: Alias value for which to retrieve the list of names.

        Returns:
            The corresponding list of alias names.
        """
        return self.aliases[value] if value in self.aliases else []

    def get_value(self, *, name: str) -> Optional[str]:
        """
        Retrieves an alias value by name.

        Args:
            name: Alias name for which to retrieve the value.

        Returns:
            The corresponding alias value, or None
        """
        value = [k for k, v in self.aliases.items() if name in v]
        return value[0] if value else None

    def put(self, *, name: str, value: str):
        """
        Assign an alias name to an alias value.

        Args:
            name: Alias name to be assigned to the value.
            value: Alias value to which to assign the name.
        """
        self.remove(name=name)
        names = self.aliases.get(value, [])
        names.append(name)
        self.aliases[value] = names

    def remove(self, *, name: str):
        """
        Remove an alias name.

        Args:
            name: Name of the alias to be removed.
        """
        for value, names in self.aliases.items():
            self.aliases[value] = [x for x in names if x != name]

    def remove_all(self):
        """Removes all alias values."""
        self.aliases = {}

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
            cmd = self.get_value(name=args[0])
            if cmd:
                args[0] = cmd
                return " ".join(args)
        return None
