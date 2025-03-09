#!/usr/bin/env python

"""Helper class to handle parsing."""

import logging
import shlex
from argparse import (
    ArgumentDefaultsHelpFormatter,
    ArgumentError,
    ArgumentParser,
    Namespace,
)
from types import MethodType
from typing import Dict, IO, Optional, Protocol

LOGGER = logging.getLogger(__name__)

DUCK_PUNCH_ERROR_FLAG = "argparse flow control sucks!"


class TypingPrint(Protocol):
    # pylint: disable=missing-class-docstring,too-few-public-methods
    def __call__(
        self, *args, sep: str, end: str, file: Optional[IO[str]], flush: bool
    ): ...


class ParserHelper:
    # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """Helper class to handle parsing."""

    def __init__(
        self,
        *args,
        max_slots: int,
        _print: TypingPrint,
        stdout: Optional[IO[str]],
        **kwargs,
    ):
        # pylint: disable=unused-argument
        self.max_slots = max_slots
        self.parser_cache: Dict[str, ArgumentParser] = {}
        self.stdout = stdout

        self._print = _print

    def get_parser(self, *, cls: str, command: str) -> ArgumentParser:
        # pylint: disable=too-many-statements
        """Caches and / or retrieves and argument parser."""

        key = hash(f"{cls}{command}")

        if key not in self.parser_cache:
            argument_parser = ArgumentParser(
                add_help=False,
                exit_on_error=False,
                formatter_class=ArgumentDefaultsHelpFormatter,
                prog=command,
            )

            # DUCK PUNCH: error()
            def duck_punch_error(_self, message):
                self._print(f"{_self.prog}: error: {message}")
                _self.print_usage(file=self.stdout)
                raise RuntimeError(DUCK_PUNCH_ERROR_FLAG)

            # pylint: disable=protected-access
            argument_parser._original_error = getattr(argument_parser, "error", None)
            argument_parser.error = MethodType(duck_punch_error, argument_parser)

            match cls:
                case "LegoConsole":
                    match command:
                        case "cat":
                            argument_parser.description = (
                                "Concatenate files and print on the standard output."
                            )
                            # argument_parser.add_argument("-A", "--show-all", action="store_true", dest="TODO", help="Equivalent to -vET.",)
                            argument_parser.add_argument(
                                "-b",
                                "--number-nonblank",
                                action="store_true",
                                dest="number_nonblank",
                                help="Number nonempty output lines, overrides -n.",
                            )
                            # argument_parser.add_argument("-e", action="store_true", dest="TODO", help="Equivalent to -vE.",)
                            argument_parser.add_argument(
                                "-E",
                                "--show-ends",
                                action="store_true",
                                dest="show_ends",
                                help="Display $ at end of each line.",
                            )
                            argument_parser.add_argument(
                                "-n",
                                "--number",
                                action="store_true",
                                dest="number",
                                help="Number all output lines.",
                            )
                            argument_parser.add_argument(
                                "-r",
                                "--raw",
                                action="store_true",
                                dest="raw",
                                help="Prints the raw data, overrides all other options.",
                            )
                            argument_parser.add_argument(
                                "-s",
                                "--squeeze-blank",
                                action="store_true",
                                dest="squeeze_blank",
                                help="Suppress repeated empty output lines.",
                            )
                            # argument_parser.add_argument("-t", action="store_true", dest="TODO", help="Equivalent to -vT.",)
                            argument_parser.add_argument(
                                "-T",
                                "--show-tabs",
                                action="store_true",
                                dest="show_tabs",
                                help="Display TAB characters as ^I.",
                            )
                            argument_parser.add_argument(
                                "-v",
                                "--show-nonprinting",
                                action="store_true",
                                dest="show_nonprinting",
                                help="Use ^ and M- notation, except for LFD and TAB.",
                            )
                            argument_parser.add_argument("file", nargs="+")
                        case "cd":
                            argument_parser.description = "Change the working directory to <directory>. The default <directory> is '/'."
                            argument_parser.add_argument(
                                "directory", default="/", nargs="?"
                            )
                        case "connect":
                            argument_parser.description = "Connects to a device, prompting if one is not specified."
                            argument_parser.add_argument("device", nargs="?")
                        case "cp":
                            argument_parser.description = "Copies files."
                            argument_parser.add_argument("source", nargs="+")
                            argument_parser.add_argument("destination")
                            argument_parser.add_argument(
                                "-b",
                                action="store_true",
                                dest="backup",
                                help="Make a backup of each existing destination file.",
                            )
                            argument_parser.add_argument(
                                "-f",
                                "--force",
                                action="store_true",
                                dest="force",
                                help="Overwrite existing destination files without prompting (ignored when -n or -i are used).",
                            )
                            argument_parser.add_argument(
                                "-i",
                                "--interactive",
                                action="store_true",
                                dest="interactive",
                                help="Prompt before overwriting existing destination files (ignored when -n is used).",
                            )
                            argument_parser.add_argument(
                                "-n",
                                "--no-clobber",
                                action="store_true",
                                dest="no_clobber",
                                help="Do not overwrite existing destination files.",
                            )
                            argument_parser.add_argument(
                                "-p",
                                action="store_true",
                                dest="preserve",
                                help="Preserve mode, ownership, and timestamp attributes.",
                            )
                            argument_parser.add_argument(
                                "-s",
                                "--suffix",
                                default="~",
                                dest="suffix",
                                help="Override the backup suffix.",
                            )
                            argument_parser.add_argument(
                                "-v",
                                "--verbose",
                                action="store_true",
                                dest="verbose",
                                help="Explain what is being done.",
                            )
                        case "df":
                            argument_parser.description = (
                                "Report file system disk space usage."
                            )
                            argument_parser.add_argument("file", default="/", nargs="?")
                            argument_parser.add_argument(
                                "-B",
                                "--block-size",
                                dest="size",
                                help="Scale sizes by <size> before printing them (ignored when -k is used).",
                            )
                            argument_parser.add_argument(
                                "-h",
                                "--human-readable",
                                action="store_true",
                                dest="human_readable",
                                help="print sizes in powers of 1024.",
                            )
                            argument_parser.add_argument(
                                "-H",
                                "--si",
                                action="store_true",
                                dest="si",
                                help="print sizes in powers of 1000 (ignored when -h is used).",
                            )
                        case "download":
                            argument_parser.description = "Downloads a file to the working directory on the local machine."
                            argument_parser.add_argument("source")
                            argument_parser.add_argument("target", nargs="?")
                        case "help":
                            argument_parser.description = "Display help information."
                            argument_parser.add_argument("topic", nargs="?")
                        case "history":
                            argument_parser.description = (
                                "Display or manipulate the history list."
                            )
                            argument_parser.add_argument(
                                "-c",
                                action="store_true",
                                dest="clear",
                                help="Clear the history list by deleting all of the entries.",
                            )
                            argument_parser.add_argument(
                                "-r",
                                action="store_true",
                                dest="read",
                                help="Read the history file and append the contents to the history list.",
                            )
                            argument_parser.add_argument(
                                "-w",
                                action="store_true",
                                dest="write",
                                help="Write the current history to the history file.",
                            )
                            argument_parser.add_argument(
                                "-d",
                                dest="offset",
                                help="Delete the history entry at position <offset>. Negative offsets count back from the end of the history list.",
                            )
                        case "ls":
                            argument_parser.description = "List information about the <file>s (the working directory by default)."
                            argument_parser.add_argument(
                                "-a",
                                "--all",
                                action="store_true",
                                dest="all",
                                help="Do not ignore entries starting with '.'.",
                            )
                            argument_parser.add_argument(
                                "-l",
                                action="store_true",
                                dest="long_list",
                                help="Use a long listing format.",
                            )
                            argument_parser.add_argument(
                                "-r",
                                "--reverse",
                                action="store_true",
                                dest="sort_reverse",
                                help="Reverse order while sorting.",
                            )
                            argument_parser.add_argument(
                                "-R",
                                "--recursive",
                                action="store_true",
                                dest="recursive",
                                help="List subdirectories recursively.",
                            )
                            argument_parser.add_argument(
                                "-S",
                                action="store_true",
                                dest="sort_size",
                                help="Sort by file size, largest first.",
                            )
                            argument_parser.add_argument(
                                "-U",
                                action="store_true",
                                dest="sort_none",
                                help="Do not sort; list entries in directory order.",
                            )
                            argument_parser.add_argument("file", nargs="*")
                        case "rm":
                            argument_parser.description = "Removes a remote <file>."
                            argument_parser.add_argument("file")
                        case "status":
                            argument_parser.description = (
                                "Displays the current device status."
                            )
                            argument_parser.add_argument(
                                "-s",
                                "--slots",
                                action="store_true",
                                dest="slots",
                                help="Include slot status.",
                            )
                        case "upload":
                            argument_parser.description = (
                                "Uploads a file to the working directory on the device."
                            )
                            argument_parser.add_argument("source")
                            argument_parser.add_argument("target", nargs="?")
                        case "vim":
                            argument_parser.description = (
                                "Vi IMproved, a programmer's text editor."
                            )
                            argument_parser.add_argument("file")

                        case _:
                            raise RuntimeError(
                                f"Unable to retrieve argument parser for class, command: {cls}, {command}"
                            )
                case "Slots":
                    match command:
                        case "install":
                            argument_parser.description = (
                                "Installs a <script> to a <slot>."
                            )
                            argument_parser.add_argument("script")
                            argument_parser.add_argument(
                                "-f",
                                "--force",
                                action="store_true",
                                dest="force",
                                help="Allow existing slots to be overridden.",
                            )
                            argument_parser.add_argument(
                                "-s",
                                "--slot",
                                dest="slot",
                                help=f"0 <= slot <= {self.max_slots}",
                                required=True,
                                type=int,
                            )
                            argument_parser.add_argument(
                                "-t",
                                "--type",
                                choices=["python", "scratch"],
                                dest="type",
                                default="python",
                                nargs="?",
                            )
                        case "uninstall":
                            argument_parser.description = (
                                "Uninstalls a script from a <slot>."
                            )
                            argument_parser.add_argument(
                                "slot",
                                help=f"0 <= slot <= {self.max_slots}",
                                type=int,
                            )
                            argument_parser.add_argument(
                                "-f",
                                "--force",
                                action="store_true",
                                dest="force",
                                help="Ignore empty slots, never prompt.",
                            )

                        case "help" | "history":
                            # Align help for aliases
                            argument_parser = self.get_parser(
                                cls="LegoConsole", command=command
                            )

                        case _:
                            raise RuntimeError(
                                f"Unable to retrieve argument parser for class, command: {cls}, {command}"
                            )
                case _:
                    raise RuntimeError(
                        f"Unable to retrieve argument parser for class: {cls}"
                    )
            self.parser_cache[key] = argument_parser

        return self.parser_cache[key]

    def parse(self, *, args: str, cls: str, command: str) -> Optional[Namespace]:
        """Parses an argument string for a given command."""

        # WORKAROUND: exit_on_error is not honored ...
        try:
            return self.get_parser(cls=cls, command=command).parse_args(
                args=shlex.split(args)
            )
        except ArgumentError as e:
            self._print(f"error: {e}")
        except RuntimeError as e:
            if e.args[0] != DUCK_PUNCH_ERROR_FLAG:
                raise e
        return None
