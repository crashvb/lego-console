#!/usr/bin/env python

"""Utility classes."""

import logging

from functools import wraps

CLASSNAME = "LegoConsole"
LOGGER = logging.getLogger(__name__)


def assert_connected(func):
    """Decorates a given function for execution only when connected."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        self = args[0]
        if not type(self).__name__ == CLASSNAME:
            raise RuntimeError(
                f"Fixture 'assert_connected' can only be used on methods of {CLASSNAME}!"
            )

        if not self.connected:
            LOGGER.error("Not connected to a device!")
            return None
        return func(*args, **kwargs)

    return wrapper


def parse_arguments(func):
    """Decorates a given function to convert 'Cmd' args to 'argparser' args."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        # pylint: disable=protected-access
        self = args[0]
        if not type(self).__name__ == CLASSNAME:
            raise RuntimeError(
                f"Fixture 'parse_arguments' can only be used on methods of {CLASSNAME}!"
            )

        command = func.__name__[3:]  # do_<command>
        arguments = self._parse(args=args[1], command=command)
        if arguments is None:
            return None
        return func(self, arguments, **kwargs)

    return wrapper
