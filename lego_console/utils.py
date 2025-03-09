#!/usr/bin/env python

"""Utility classes."""

import logging
from argparse import Namespace

from functools import wraps
from pathlib import PurePath
from typing import List

CLASSNAMES = ["LegoConsole", "Slots"]
LOGGER = logging.getLogger(__name__)


def assert_connected(func):
    """Decorates a given function for execution only when connected."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        self = args[0]
        classname = type(self).__name__
        if not classname in CLASSNAMES:
            raise RuntimeError(
                f"Fixture 'assert_connected' can only be used on methods of {CLASSNAMES}!"
            )
        match classname:
            case "LegoConsole":
                connected = self.connected
            case "Slots":
                connected = self.lego_console.connected
            case _:
                raise RuntimeError(f"Unsupported class: {classname}")

        if not connected:
            LOGGER.error("Not connected to a device!")
            return None
        return func(*args, **kwargs)

    return wrapper


def check_mutually_exclusive(*, args: Namespace, arg_names: List[str]) -> bool:
    """
    Checks if multiple, mutually exclusive argments are provided.
    Args:
        args: The parsed arguments' namespace.
        arg_names: List of argument names to be checked.

    Returns: True if the check fails and multiple listed arguments exist within the namespace. False otherwise.

    """
    found = False
    for arg in arg_names:
        if getattr(args, arg, None):
            if found:
                return False
            found = True
    return True


def normalize_path(*, path: PurePath) -> PurePath:
    """
    Returns a normalized path.
    Args:
        path: The path to be normalized.

    Returns: The normalized path.
    """
    segments = str(path).split("/")
    result = PurePath("/")
    for segment in segments:
        if segment == "..":
            result = result.parent
        elif segment != "." and segment:
            result = PurePath.joinpath(result, segment)
    return result


def parse_arguments(func):
    """Decorates a given function to convert 'Cmd' args to 'argparser' args."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        self = args[0]
        classname = type(self).__name__
        if not classname in CLASSNAMES:
            raise RuntimeError(
                f"Fixture 'parse_arguments' can only be used on methods of {CLASSNAMES}!"
            )

        command = func.__name__[3:]  # do_<command>
        match classname:
            case "LegoConsole":
                arguments = self.parser_helper.parse(
                    args=args[1], cls=classname, command=command
                )
            case "Slots":
                arguments = self.lego_console.parser_helper.parse(
                    args=args[1], cls=classname, command=command
                )
            case _:
                raise RuntimeError(f"Unsupported class: {classname}")
        if arguments is None:
            return None
        return func(self, arguments, **kwargs)

    return wrapper
