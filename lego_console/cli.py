#!/usr/bin/env python

"""xsessionp command line interface."""

import logging
import sys

from pathlib import Path
from traceback import print_exception
from typing import NamedTuple

import click

from click.core import Context
from crashvb_logging_utilities import (
    LOGGING_DEFAULT,
    logging_options,
    set_log_levels,
)

from .lego_console import LegoConsole

DEFAULT_HISTORY_PATH = str(Path.home().joinpath(".lc_history"))
DEFAULT_HISTORY_SIZE = 500

LOGGER = logging.getLogger(__name__)


class TypingContextObject(NamedTuple):
    # pylint: disable=missing-class-docstring
    lego_console: LegoConsole
    verbosity: int


def get_context_object(*, context: Context) -> TypingContextObject:
    """Wrapper method to enforce type checking."""
    return context.obj


@click.group()
@click.option(
    "--auto-connect/--no-auto-connect",
    default=True,
    help="Toggles connecting to a device automatically.",
    show_default=True,
)
@click.option(
    "--history-file",
    default=DEFAULT_HISTORY_PATH,
    required=True,
    envvar="LC_HISTFILE",
    show_default=True,
)
@click.option(
    "--history-size",
    default=DEFAULT_HISTORY_SIZE,
    required=True,
    envvar="LC_HISTSIZE",
    show_default=True,
    type=int,
)
@logging_options
@click.pass_context
def cli(
    context: Context,
    auto_connect,
    history_file,
    history_size,
    verbosity,
):
    """A declarative window instantiation utility based on xsession."""

    if verbosity is None:
        verbosity = LOGGING_DEFAULT

    set_log_levels(verbosity)

    if history_file:
        history_file = Path(history_file)

    context.obj = TypingContextObject(
        lego_console=LegoConsole(
            auto_connect=auto_connect,
            history_file=history_file,
            history_size=history_size,
        ),
        verbosity=verbosity,
    )


@cli.command(name="start", short_help="Starts an interactive lego console.")
@click.pass_context
def start(context: Context):
    # pylint: disable=protected-access,redefined-builtin
    """Starts a lego console."""
    ctx = get_context_object(context=context)
    try:
        ctx = get_context_object(context=context)
        ctx.lego_console.cmdloop()
    except Exception as exception:  # pylint: disable=broad-except
        if ctx.verbosity > 0:
            logging.fatal(exception)
        if ctx.verbosity > LOGGING_DEFAULT:
            exc_info = sys.exc_info()
            print_exception(*exc_info)
        sys.exit(1)


@cli.command()
def version():
    """Displays the version."""

    # Note: * This cannot be imported above, as it causes a circular import!
    #       * This requires '__version__' to be defined in '__init__.py'
    from . import __version__  # pylint: disable=import-outside-toplevel

    print(__version__)


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    cli()
