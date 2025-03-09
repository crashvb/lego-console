#!/usr/bin/env python

"""Sub-command: slots."""

import logging
import os
from argparse import (
    Namespace,
)
from ast import literal_eval
from base64 import b64decode, b64encode
from cmd import Cmd
from datetime import datetime
from functools import partial
from pathlib import Path, PurePath
from typing import Any, Dict, TYPE_CHECKING

from ..consts import ANSI_FG_YELLOW, ANSI_FG_GRAY, ANSI_NC
from ..helpers.alias_helper import AliasHelper
from ..helpers.parser_helper import ParserHelper
from ..menus import prompt_yes_no
from ..utils import assert_connected, parse_arguments

if TYPE_CHECKING:
    from ..lego_console import LegoConsole

LOGGER = logging.getLogger(__name__)

FILE_EXTENSIONS = ["mpy", "py"]

PATH_PROJECTS = PurePath("/projects")
PATH_SLOTS = PurePath(f"{PATH_PROJECTS}/.slots")


class Slots(Cmd):
    # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """Sub-command for interacting with slots."""

    def borrow_function(self, *, func):
        """
        Adapts a method from a similar class without using inheritance.

        Args:
            func: The function to be adapted.

        Returns:
            The adpated function.

        """
        # method -> object -> class
        cls = func.__self__.__class__
        func_new = partial(getattr(cls, func.__name__), self)
        func_new.__doc__ = func.__doc__
        return func_new

    def __init__(
        self, *args, lego_console: "LegoConsole", parser_helper: ParserHelper, **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.lego_console = lego_console
        self.parser_helper = parser_helper

        self.alias_helper = AliasHelper(
            aliases={"exit": ["EOF", "quit"], "help": ["man"]}
        )

        self.prompt = lego_console.prompt.replace("\n", "\n(slots) ")

        # pylint: disable=protected-access
        self._print = self.lego_console._print

        # Cmd Methods
        self.default = self.borrow_function(func=self.lego_console.default)
        self.emptyline = self.lego_console.emptyline
        self.postcmd = self.lego_console.postcmd

        # Commands
        self.do_alias = self.borrow_function(func=self.lego_console.do_alias)
        self.do_clear = self.lego_console.do_clear
        self.do_help = self.borrow_function(func=self.lego_console.do_help)
        self.do_history = self.lego_console.do_history

    @assert_connected
    def _get_slot_configuration(self) -> Dict[int, Dict[str, Any]]:
        LOGGER.debug("Retrieving slot configuration: %s ...", PATH_SLOTS)
        _bytes = self.lego_console.files.get(PATH_SLOTS)
        LOGGER.debug("Retrieved slot configuration: [%d bytes]", len(_bytes))
        return literal_eval(_bytes.decode(encoding="utf-8"))

    @assert_connected
    def _put_slot_configuration(self, *, config: Dict[int, Dict[str, Any]]):
        LOGGER.debug("Storing slot configuration: %s ...", PATH_SLOTS)
        _bytes = str(config).encode(encoding="utf-8")
        self.lego_console.files.put(PATH_SLOTS, _bytes)
        LOGGER.debug("Stored slot configuration: [%d bytes]", len(_bytes))

    @assert_connected
    def _remove_project(self, *, leave_directory: bool = False, project_id: str):
        # pylint: disable=protected-access
        path_project = PurePath.joinpath(PATH_PROJECTS, str(project_id))
        for extension in FILE_EXTENSIONS:
            path = PurePath.joinpath(path_project, f"__init__.{extension}")
            if self.lego_console._exists_file(path=path):
                LOGGER.debug("Removing file: %s ...", path)
                self.lego_console.files.rm(str(path))
                LOGGER.debug("File removed.")
        if not leave_directory:
            LOGGER.debug("Removing directory: %s ...", path_project)
            self.lego_console.files.rmdir(str(path_project), missing_okay=True)
            LOGGER.debug("Directory removed.")

    # Commands

    def do_exit(self, _: str):
        """
        Usage: exit
        Returns to the main console.
        """
        return True

    @assert_connected
    @parse_arguments
    def do_install(self, args: Namespace):
        """."""

        try:
            path_src = Path(args.script).resolve(strict=True)
        except FileNotFoundError as e:
            LOGGER.error(e.strerror)
            return

        if not path_src.is_file():
            LOGGER.error("Not a file: %s", path_src)
            return

        extension = path_src.suffix.replace(".", "").lower()
        if not extension:
            LOGGER.warning("Cannot detect file type; assuming uncompiled python.")
            extension = "py"

        if not extension in FILE_EXTENSIONS:
            LOGGER.error("Unsupported extension: %s", extension)
            return

        if not 0 <= args.slot <= self.lego_console.max_slots:
            LOGGER.error("Slot is out of range: %d", args.slot)
            return

        config = self._get_slot_configuration()

        if args.slot in config:
            if args.force:
                LOGGER.warning("Overriding existing slot #%d", args.slot)
                self._remove_project(
                    leave_directory=True, project_id=config[args.slot]["id"]
                )
            else:
                LOGGER.error("Slot is not empty: %d", args.slot)
                return

        project_id = 10000 + args.slot

        config[args.slot] = {
            "name": b64encode(path_src.name.encode(encoding="utf-8")).decode(
                encoding="utf-8"
            ),
            "project_id": f"prj{project_id}",
            "modified": int(os.path.getmtime(path_src) * 1000),
            "created": int(os.path.getctime(path_src) * 1000),
            "id": project_id,
            "type": args.type,
            # "size": os.stat(path_src).st_size,
        }

        path_dest = PurePath.joinpath(
            PATH_PROJECTS, f"{project_id}/__init__.{extension}"
        )
        path_project = path_dest.parent
        LOGGER.debug("Creating directory: %s ...", path_project)
        self.lego_console.files.mkdir(str(path_project), exists_okay=True)
        LOGGER.debug("Directory created.")
        LOGGER.debug("Uploading '%s' to '%s' ...", path_src, path_dest)
        _bytes = path_src.read_bytes()
        self.lego_console.files.put(str(path_dest), _bytes)
        LOGGER.debug("Upload completed: [%d bytes]", len(_bytes))

        self._put_slot_configuration(config=config)
        LOGGER.info("Installed '%s' to slot #%d.", path_src, args.slot)

    @assert_connected
    def do_status(self, args: str):
        # pylint: disable=unused-argument
        """Displays the current slot status."""

        config = self._get_slot_configuration()

        self._print("Slots       :")
        for i in range(self.lego_console.max_slots):
            if i not in config:
                self._print(f"  {i}: {ANSI_FG_GRAY}<empty>{ANSI_NC}")
            else:
                slot = config[i]
                modified = datetime.fromtimestamp(slot["modified"] / 1000)
                self._print(
                    f"  {i}: {ANSI_FG_YELLOW}{b64decode(slot['name']).decode(encoding='utf-8')}{ANSI_NC}"
                )
                self._print(f"    id       : {slot['id']}")
                self._print(f"    type     : {slot['type']}")
                self._print(f"    modified : {modified.strftime('%Y-%m-%d %H:%M:%S')}")

    @assert_connected
    @parse_arguments
    def do_uninstall(self, args: Namespace):
        """."""

        if not 0 <= args.slot <= self.lego_console.max_slots:
            LOGGER.error("Slot is out of range: %d", args.slot)
            return

        config = self._get_slot_configuration()

        if not args.slot in config:
            if not args.force:
                LOGGER.error("Slot is empty: %d", args.slot)
                return

        slot = config[args.slot]
        name = b64decode(slot["name"]).decode(encoding="utf-8")
        if not args.force and not prompt_yes_no(
            title=f"Uninstall slot #{args.slot}: {name}?"
        ):
            LOGGER.warning("User aborted operation!")
            return

        del config[args.slot]

        self._put_slot_configuration(config=config)

        self._remove_project(project_id=slot["id"])
        LOGGER.info("Uninstalled slot #%d.", args.slot)
