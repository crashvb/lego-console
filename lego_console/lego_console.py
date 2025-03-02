import logging
import os
import re
import readline
import shlex
from argparse import (
    ArgumentDefaultsHelpFormatter,
    ArgumentError,
    ArgumentParser,
    Namespace,
)
from ast import literal_eval
from base64 import b64decode, b64encode
from cmd import Cmd
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path, PurePath
from stat import filemode, S_ISDIR, S_ISREG
from subprocess import call
from tempfile import NamedTemporaryFile
from textwrap import dedent
from types import MethodType
from typing import Any, Dict, IO, List, Optional, Union

from ampy.files import Files
from ampy.pyboard import Pyboard, PyboardError
from serial.tools.list_ports import comports

from .menus import prompt_device, prompt_yes_no
from .utils import assert_connected, parse_arguments

LOGGER = logging.getLogger(__name__)

ANSI_FG_GREEN = "\033[0;32m"
ANSI_FG_RED = "\033[0;31m"
ANSI_FG_YELLOW = "\033[0;33m"
ANSI_FG_BLUE = "\033[0;34m"
ANSI_FG_GRAY = "\033[0;90m"
ANSI_NC = "\033[0m"

DUCK_PUNCH_ERROR_FLAG = "argparse flow control sucks!"

EDITOR = os.environ.get("EDITOR", "vim")

FILE_EXTENSIONS = ["mpy", "py"]

MAX_SLOTS = 10

PATH_LOCAL_NAME = PurePath("/local_name.txt")
PATH_PROJECTS = PurePath("/projects")
PATH_SLOTS = PurePath(f"{PATH_PROJECTS}/.slots")

PROTECTED_PATHS = [
    "/boot.py",
    "/bt-lk1.dat",
    "/bt-lk2.dat",
    "/commands/__init__.mpy",
    "/commands/abstract_handler.mpy",
    "/commands/hub_methods.mpy",
    "/commands/light_methods.mpy",
    "/commands/linegraphmonitor_methods.mpy",
    "/commands/motor_methods.mpy",
    "/commands/move_methods.mpy",
    "/commands/program_methods.mpy",
    "/commands/sound_methods.mpy",
    "/commands/wait_methods.mpy",
    "/event_loop/__init__.mpy",
    "/event_loop/event_loop.mpy",
    "/hub_runtime.mpy",
    "/local_name.txt",
    "/main.py",
    "mindstorms/__init__.mpy",
    "mindstorms/control.mpy",
    "mindstorms/operator.mpy",
    "mindstorms/util.mpy",
    "/programrunner/__init__.mpy",
    "/projects/.slots",
    "/projects/standalone.mpy",
    "/projects/standalone_/__init__.mpy",
    "/projects/standalone_/animation.mpy",
    "/projects/standalone_/device_helper.mpy",
    "/projects/standalone_/devices.mpy",
    "/projects/standalone_/display.mpy",
    "/projects/standalone_/priority_mapping.mpy",
    "/projects/standalone_/program.mpy",
    "/projects/standalone_/row.mpy",
    "/projects/standalone_/util.mpy",
    "/protocol/__init__.mpy",
    "/protocol/notifications.mpy",
    "/protocol/rpc_protocol.mpy",
    "/protocol/ujsonrpc.mpy",
    "/runtime/__init__.mpy",
    "/runtime/dirty_dict.mpy",
    "/runtime/extensions/__init__.mpy",
    "/runtime/extensions/abstract_extension.mpy",
    "/runtime/extensions/displaymonitor.mpy",
    "/runtime/extensions/linegraphmonitor.mpy",
    "/runtime/extensions/music.mpy",
    "/runtime/extensions/radio_broadcast.mpy",
    "/runtime/extensions/sound.mpy",
    "/runtime/extensions/weather.mpy",
    "/runtime/multimotor.mpy",
    "/runtime/stack.mpy",
    "/runtime/timer.mpy",
    "/runtime/virtualmachine.mpy",
    "/runtime/vm_store.mpy",
    "/sounds/menu_click",
    "/sounds/menu_fastback",
    "/sounds/menu_program_start",
    "/sounds/menu_program_stop",
    "/sounds/menu_shutdown",
    "/sounds/startup",
    "/spike/__init__.mpy",
    # "/spike/app.mpy",
    # "/spike/button.mpy",
    # "/spike/colorsensor.mpy",
    "/spike/control.mpy",
    # "/spike/distancesensor.mpy",
    # "/spike/forcesensor.mpy",
    # "/spike/lightmatrix.mpy",
    # "/spike/motionsensor.mpy",
    # "/spike/motor.mpy",
    # "/spike/motorpair.mpy",
    "/spike/operator.mpy",
    # "/spike/primehub.mpy",
    # "/spike/speaker.mpy",
    # "/spike/statuslight.mpy",
    "/spike/util.mpy",
    "/system/__init__.mpy",
    "/system/abstractwrapper.mpy",
    "/system/callbacks/__init__.mpy",
    "/system/callbacks/customcallbacks.mpy",
    "/system/display.mpy",
    "/system/motors.mpy",
    "/system/motorwrapper.mpy",
    "/system/move.mpy",
    "/system/movewrapper.mpy",
    "/system/simplemotorwrapper.mpy",
    "/system/simplemovewrapper.mpy",
    "/system/sound.mpy",
    "/ui/__init__.mpy",
    "/ui/hubui.mpy",
    "/util/__init__.mpy",
    "/util/adjust_motor_offset.mpy",
    "/util/animations.mpy",
    "/util/auto_connect.mpy",
    "/util/color.mpy",
    "/util/constants.mpy",
    "/util/error_handler.mpy",
    "/util/ext_sensor_data.mpy",
    "/util/log.mpy",
    "/util/motion.mpy",
    "/util/motor.mpy",
    "/util/movement.mpy",
    # "/util/parser.mpy",
    "/util/print_override.mpy",
    "/util/resetter.mpy",
    # "/util/rotation.mpy",
    "/util/schedule.mpy",
    "/util/scratch.mpy",
    "/util/sensors.mpy",
    "/util/storage.mpy",
    "/util/time.mpy",
    "/version.py",
]

SIZE_UNITS = ["B", "K", "M", "G", "T", "P", "E", "Z", "Y"]


def _cat_show_nonprinting(*, string: str) -> str:
    # https://github.com/coreutils/coreutils/blob/master/src/cat.c
    result = ""
    for c in string:
        ch = ord(str(c))
        if ch >= 32:
            if ch < 127:
                result += c
            elif ch == 127:
                result += "^?"
            else:
                result += "M-"
                if ch >= 128 + 32:
                    if ch < 128 + 127:
                        result += chr(ch - 128)
                    else:
                        result += "^?"
                else:
                    result += f"^{chr(ch - 128 + 64)}"
        else:
            result += f"^{chr(ch + 64)}"
    return result


def _check_mutually_exclusive(*, args: Namespace, arg_names: List[str]) -> bool:
    found = False
    for arg in arg_names:
        if getattr(args, arg, None):
            if found:
                return False
            found = True
    return True


def _format_size_automatic(*, factor: float = 1024.0, size: int) -> str:
    for x in SIZE_UNITS:
        if size < factor:
            size = max(1.0, size)
            return f"{size:3.{0 if size >= 10 else 1}f}{x}"
        size /= factor
    return f"{size:3.0f}Y"


def _format_size_explicit(*, factor: str = "K", size: int) -> str:
    return f"{max(1, int(size / (1024.0 ** SIZE_UNITS.index(factor))))}{factor}"


def _path_protected(*, path: Union[str, PurePath]) -> bool:
    return str(path) in PROTECTED_PATHS


def normalize(*, path: PurePath) -> PurePath:
    segments = str(path).split("/")
    result = PurePath("/")
    for segment in segments:
        if segment == "..":
            result = result.parent
        elif segment != "." and segment:
            result = PurePath.joinpath(result, segment)
    return result


class LegoConsole(Cmd):
    # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """Console for Lego Mindstorms Inventor / Spike Prime."""

    def __init__(
        self,
        *args,
        auto_connect: bool = True,
        history_file: Optional[Path] = None,
        history_size: Optional[int] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.auto_connect: bool = auto_connect
        self.connected: bool = False
        self.cwd: PurePath = PurePath("/")
        self.cwd_old: PurePath = self.cwd
        self.device_name: Optional[str] = None
        self.files: Optional[Files] = None
        self.history_file = history_file
        self.history_size = history_size
        self.parser_cache: Dict[str, ArgumentParser] = {}
        self.pyboard: Optional[Pyboard] = None

    @assert_connected
    def __exec(self, *, command: str) -> Any:
        try:
            self.pyboard.enter_raw_repl()
            output = self.pyboard.exec_(dedent(command))
        finally:
            self.pyboard.exit_raw_repl()
        return literal_eval(output.decode(encoding="utf-8"))

    def __get_parser(self, *, command) -> ArgumentParser:
        # pylint: disable=protected-access
        if command not in self.parser_cache:
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

            argument_parser._original_error = getattr(argument_parser, "error", None)
            argument_parser.error = MethodType(duck_punch_error, argument_parser)

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
                    argument_parser.add_argument("directory", default="/", nargs="?")
                case "connect":
                    argument_parser.description = (
                        "Connects to a device, prompting if one is not specified."
                    )
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
                    argument_parser.description = "Report file system disk space usage."
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
                case "install":
                    argument_parser.description = "Installs a <script> to a <slot>."
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
                        help=f"0 <= slot <= {MAX_SLOTS}",
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
                    argument_parser.description = "Displays the current device status."
                    argument_parser.add_argument(
                        "-s",
                        "--slots",
                        action="store_true",
                        dest="slots",
                        help="Include slot status.",
                    )
                case "uninstall":
                    argument_parser.description = "Uninstalls a script from a <slot>."
                    argument_parser.add_argument(
                        "slot",
                        help=f"0 <= slot <= {MAX_SLOTS}",
                        type=int,
                    )
                    argument_parser.add_argument(
                        "-f",
                        "--force",
                        action="store_true",
                        dest="force",
                        help="Ignore empty slots, never prompt.",
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
                        f"Unable to retrieve argument parser for command: {command}"
                    )
            self.parser_cache[command] = argument_parser

        return self.parser_cache[command]

    def _apply_cwd(self, *, path: Union[PurePath, str]) -> PurePath:
        return PurePath.joinpath(self.cwd, path)

    def _connect(self, *, device: str) -> bool:
        LOGGER.debug("Connecting to device: %s ...", device)
        self._disconnect()
        try:
            self.pyboard = Pyboard(device=device)
            self.files = Files(pyboard=self.pyboard)
            LOGGER.info("Device connected.")
            self.connected = True
        except PyboardError as e:
            LOGGER.error(f"Unable to connect to device: {device}", e)

        return self.connected

    def _copy_file(self, *, destination: PurePath, source: PurePath):
        self.files.put(str(destination), self.files.get(str(source)))

    def _disconnect(self):
        try:
            if self.pyboard:
                LOGGER.debug("Disconnecting from device ...")
                self.pyboard.close()
                LOGGER.info("Device disconnected.")
        finally:
            self.connected = False
            self.cwd = PurePath("/")
            self.cwd_old = self.cwd
            self.device_name = None
            self.files = None
            self.pyboard = None

    @assert_connected
    def _exists_directory(self, *, path: PurePath) -> bool:
        stats = self._os_stats(path=path)
        return stats is not None and S_ISDIR(stats[0])

    @assert_connected
    def _exists_file(self, *, path: PurePath) -> bool:
        stats = self._os_stats(path=path)
        return stats is not None and S_ISREG(stats[0])

    @assert_connected
    def _get_device_name(self) -> str:
        LOGGER.debug("Retrieving device name: %s ...", PATH_LOCAL_NAME)
        _bytes = self.files.get(PATH_LOCAL_NAME)
        self.device_name = _bytes.decode(encoding="utf-8").split("@")[1]
        LOGGER.debug("Retrieved device name: %s", self.device_name)

    @assert_connected
    def _get_slot_configuration(self) -> Dict[int, Dict[str, Any]]:
        LOGGER.debug("Retrieving slot configuration: %s ...", PATH_SLOTS)
        _bytes = self.files.get(PATH_SLOTS)
        LOGGER.debug("Retrieved slot configuration: [%d bytes]", len(_bytes))
        return literal_eval(_bytes.decode(encoding="utf-8"))

    @assert_connected
    def _os_stats(self, *, path: PurePath) -> Optional[List]:
        command = f"""
                import os
                path = '{str(path)}'
                print(os.stat(path))
                """
        try:
            return self.__exec(command=command)
        except PyboardError as e:
            message = e.args[2].decode("utf-8")
            if message.find("OSError: [Errno 2] ENOENT") != -1:
                return None
            raise e

    @assert_connected
    def _os_statvfs(self, *, path: PurePath) -> Optional[List]:
        command = f"""
                import os
                path = '{str(path)}'
                print(os.statvfs(path))
                """
        try:
            return self.__exec(command=command)
        except PyboardError as e:
            message = e.args[2].decode("utf-8")
            if message.find("OSError: [Errno 2] ENOENT") != -1:
                return None
            raise e

    def _parse(self, *, args: str, command: str) -> Optional[Namespace]:
        # WORKAROUND: exit_on_error is not honored ...
        try:
            return self.__get_parser(command=command).parse_args(args=shlex.split(args))
        except ArgumentError as e:
            self._print(f"error: {e}")
        except RuntimeError as e:
            if e.args[0] != DUCK_PUNCH_ERROR_FLAG:
                raise e
        return None

    def _print(
        self,
        *args,
        sep: str = " ",
        end: str = "\n",
        file: Optional[IO[str]] = None,
        flush=False,
    ):
        file = file if file else self.stdout
        file.write(f"{sep.join(args)}{end}")
        if flush:
            file.flush()

    @assert_connected
    def _put_slot_configuration(self, *, config: Dict[int, Dict[str, Any]]):
        LOGGER.debug("Storing slot configuration: %s ...", PATH_SLOTS)
        _bytes = str(config).encode(encoding="utf-8")
        self.files.put(PATH_SLOTS, _bytes)
        LOGGER.debug("Stored slot configuration: [%d bytes]", len(_bytes))

    def _read_history(self):
        if self.history_file and self.history_file.is_file():
            LOGGER.debug("Reading history file: %s ...", self.history_file)
            readline.read_history_file(self.history_file)
            LOGGER.debug("Read %d lines.", readline.get_current_history_length())

    @assert_connected
    def _remove_project(self, *, leave_directory: bool = False, project_id: str):
        path_project = PurePath.joinpath(PATH_PROJECTS, str(project_id))
        for extension in FILE_EXTENSIONS:
            path = PurePath.joinpath(path_project, f"__init__.{extension}")
            if self._exists_file(path=path):
                LOGGER.debug("Removing file: %s ...", path)
                self.files.rm(str(path))
                LOGGER.debug("File removed.")
        if not leave_directory:
            LOGGER.debug("Removing directory: %s ...", path_project)
            self.files.rmdir(str(path_project), missing_okay=True)
            LOGGER.debug("Directory removed.")

    def _update_prompt(self):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.prompt = timestamp
        if self.connected:
            if not self.device_name:
                self._get_device_name()
            self.prompt += f" {ANSI_FG_BLUE}{self.device_name}{ANSI_NC} [{self.cwd}]"
        else:
            self.prompt += f" [{ANSI_FG_RED}disconnected{ANSI_NC}]"
        self.prompt += "\n🤖: "

    def _write_history(self):
        if self.history_file:
            LOGGER.debug("Writing history file: %s ...", self.history_file)
            readline.write_history_file(self.history_file)
            LOGGER.debug("Wrote %d lines.", readline.get_history_length())

    # Cmd Methods

    def default(self, line):
        self._print(f"{line}: command not found")

    def emptyline(self): ...

    def preloop(self):
        super().preloop()

        if self.history_file:
            if not self.history_file.is_file():
                LOGGER.debug("Creating history file: %s ...", self.history_file)
                self.history_file.touch(exist_ok=True)
                LOGGER.debug("History file created.")
            LOGGER.debug("Setting history length: %d", self.history_size)
            readline.set_history_length(self.history_size)
        else:
            LOGGER.warning("No history file!")

        self._read_history()

        if self.auto_connect:
            self.do_connect("")

        self._update_prompt()

    def postcmd(self, stop, line):
        self._update_prompt()
        return super().postcmd(stop, line)

    def postloop(self):
        super().postloop()
        self._write_history()

    # Commands

    @assert_connected
    @parse_arguments
    def do_cat(self, args: Namespace):
        # pylint: disable=too-many-branches
        """."""

        paths = list(
            map(
                lambda file: normalize(path=self._apply_cwd(path=file)),
                args.file,
            )
        )  # typing: List[PurePath]

        for path in paths:
            if not self._exists_file(path=path):
                LOGGER.error("File does not exist: %s", path)
                continue

            data = ""
            try:
                data = self.files.get(path)
            except (RuntimeError, PyboardError) as e:
                LOGGER.error(f"Unable to read file: {path}", e)

            if args.raw:
                self._print(data)
                continue

            try:
                data = data.decode(encoding="utf-8")
            except UnicodeDecodeError as e:
                LOGGER.error(f"Unable to decode file: {path}", e)

            count_line = 0
            blank_previous = False
            for line in data.splitlines():
                blank_current = line == ""
                if args.squeeze_blank:
                    try:
                        if blank_current and blank_previous:
                            continue
                    finally:
                        blank_previous = blank_current

                if args.show_nonprinting:
                    line = _cat_show_nonprinting(string=line)

                # Note: Must be above '\t' formatting
                if args.show_tabs:
                    line = line.replace("\t", "^I")

                if (args.number_nonblank and not blank_current) or args.number:
                    count_line += 1
                    line = f"{count_line:>6}\t{line}"

                if args.show_ends:
                    line += "$"

                self._print(line)

    @assert_connected
    @parse_arguments
    def do_cd(self, args: Namespace):
        """."""
        # TODO: Implement CDPATH

        if args.directory == "-":
            args.directory = self.cwd_old
        path = normalize(path=self._apply_cwd(path=args.directory))
        if self._exists_directory(path=path):
            self.cwd_old = self.cwd
            self.cwd = path
        else:
            LOGGER.error("Directory does not exist: %s", path)

    def do_clear(self, _: str):
        """
        Usage: clear
        Clears your screen if this is possible, including its scrollback buffer.
        """
        self._print("\033c\033[3J", end="")

    @parse_arguments
    def do_connect(self, args: Namespace):
        """."""
        if not args.device:
            ports = comports(include_links=False)
            if len(ports) == 1:
                LOGGER.debug("Only 1 port found; connecting ...")
                args.device = ports[0].device
            elif ports:
                args.device = prompt_device(devices=[p.device for p in ports])
        if args.device:
            self._connect(device=args.device)
        else:
            LOGGER.error("Unable to connect; no device provided!")

    @assert_connected
    @parse_arguments
    def do_cp(self, args: Namespace):
        """."""

        if not _check_mutually_exclusive(args=args, arg_names=["backup", "no_clobber"]):
            LOGGER.error(
                "Options --backup (-b) and --no-clobber (-n) are mutually exclusive."
            )
            return

        path_dest = self._apply_cwd(path=args.destination)
        path_srcs = list(
            map(lambda file: normalize(path=self._apply_cwd(path=file)), args.source)
        )

        # Source(s) must be a file(s)
        for path_src in path_srcs:
            if not self._exists_file(path=path_src):
                LOGGER.error("Does not exist or is not a file: %s", path_src)
                return

        dest_is_dir = self._exists_directory(path=path_dest)
        if len(path_srcs) > 1 and not dest_is_dir:
            LOGGER.error("Does not exist or is not directory: %s", path_dest)
            return

        for path_src in set(path_srcs):
            path_target = (
                PurePath.joinpath(path_dest, path_src.name)
                if dest_is_dir
                else path_dest
            )

            if path_src == path_target:
                LOGGER.error("'%s' and '%s' are the same file", path_src, path_target)
                continue

            path_backup = None
            if self._exists_file(path=path_target):
                if args.no_clobber:
                    continue
                if _path_protected(path=path_target):
                    LOGGER.error("Protected Path: %s", path_dest)
                    continue
                if (args.interactive or not args.force) and not prompt_yes_no(
                    title=f"Override existing file: {path_target}?"
                ):
                    continue

                if args.backup:
                    suffix = re.sub(r"[^0-9a-zA-Z.~]+", "", args.suffix)
                    path_backup = PurePath(
                        path_target.parent, f"{path_target.name}{suffix}"
                    )
                    self._copy_file(destination=path_backup, source=path_target)

            LOGGER.debug("Copying '%s' to '%s' ...", path_src, path_target)
            if args.verbose:
                self._print(
                    f"'{path_src}' -> '{path_target}'"
                    + (f" (backup: '{path_backup}')" if path_backup else "")
                )
            self._copy_file(destination=path_target, source=path_src)
            LOGGER.info("Copy completed.")

    @assert_connected
    @parse_arguments
    def do_df(self, args: Namespace):
        """."""

        if not _check_mutually_exclusive(
            args=args, arg_names=["human_readable", "si", "size"]
        ):
            LOGGER.error(
                "Options --block-size (-B), --human-readable (-h), --si (-H), and -k are mutually exclusive."
            )
            return

        statvfs = self._os_statvfs(path=args.file)
        if not statvfs:
            LOGGER.error("No such file or directory: %s", args.file)
            return
        statvfs = os.statvfs_result(statvfs)

        total = statvfs.f_frsize * statvfs.f_blocks
        free = statvfs.f_frsize * statvfs.f_bfree
        available = statvfs.f_frsize * statvfs.f_bavail
        used = total - free
        usedp = int((used / total) * 100)

        header = ""
        row = ""
        if args.human_readable or args.si:
            factor = 1024.0 if args.human_readable else 1000.0
            total = _format_size_automatic(factor=factor, size=total)
            used = _format_size_automatic(factor=factor, size=used)
            available = _format_size_automatic(factor=factor, size=available)

            columns = OrderedDict(
                [
                    ("Filesystem", ["<", args.file]),
                    ("Size", [">", total]),
                    ("Used", [">", used]),
                    ("Avail", [">", available]),
                    ("Use%", [">", f"{usedp}%"]),
                ]
            )
        else:
            factor = args.size.upper() if args.size else "K"
            total = _format_size_explicit(factor=factor, size=total)
            used = _format_size_explicit(factor=factor, size=used)
            available = _format_size_explicit(factor=factor, size=available)

            columns = OrderedDict(
                [
                    ("Filesystem", ["<", args.file]),
                    (f"1{factor[:1]}-blocks", [">", total]),
                    ("Used", [">", used]),
                    ("Available", [">", available]),
                    ("Use%", [">", f"{usedp}%"]),
                ]
            )

        for key, value in columns.items():
            width = max(len(key), len(str(value[1])))
            header += f"{key:{value[0]}{width}} "
            row += f"{value[1]:{value[0]}{width}} "
        self._print(header, row, sep=os.linesep)

    def do_disconnect(self, _: str):
        """
        Usage: disconnect
        Disconnects from a connected device.
        """
        self._disconnect()

    @assert_connected
    @parse_arguments
    def do_download(self, args: Namespace):
        """."""

        path_src = self._apply_cwd(path=args.source)
        if not self._exists_file(path=path_src):
            LOGGER.error("File does not exist: %s", path_src)
            return

        path_dest = Path(args.target if args.target else path_src.name)
        if path_dest.exists() and not prompt_yes_no(
            title=f"Override existing file: {path_dest}?"
        ):
            LOGGER.warning("User aborted operation!")
            return

        LOGGER.debug("Downloading '%s' to '%s' ...", path_src, path_dest)
        length = path_dest.write_bytes(self.files.get(str(path_src)))
        LOGGER.info("Download completed: [%d bytes]", length)

    def do_EOF(self, args: str):
        # pylint: disable=invalid-name
        """Alias 'exit'."""
        self._print("exit")
        return self.do_exit(args)

    def do_exit(self, _: str):
        """
        Usage: exit
        Cause normal process termination.
        """
        self._disconnect()
        return True

    def do_help(self, arg: str):
        if arg:
            try:
                argument_parser = self.__get_parser(command=arg)
                argument_parser.print_help(file=self.stdout)
                return None
            except RuntimeError:
                ...
        return super().do_help(arg)

    @parse_arguments
    def do_history(self, args: Namespace):
        """."""

        # https://github.com/bminor/bash/blob/6794b5478f660256a1023712b5fc169196ed0a22/builtins/history.def#L164
        if not _check_mutually_exclusive(args=args, arg_names=["read", "write"]):
            LOGGER.error("Options -r and -w are mutually exclusive.")
            return

        if args.clear:
            LOGGER.debug("Clearing history ...")
            readline.clear_history()
            LOGGER.debug("History cleared.")
        elif args.offset:
            position = int(args.offset)
            if position == 0:
                LOGGER.error("History position out of range: %d", position)
                return
            if position > 0:
                position -= 1
            else:
                position += readline.get_current_history_length()
            LOGGER.debug("Removing history: %d", position + 1)
            readline.remove_history_item(position)
            LOGGER.debug("History removed.")
            return

        if args.write:
            self._write_history()
        elif args.read:
            self._read_history()
        else:
            length = readline.get_current_history_length()
            for i in range(length):
                index = i + 1
                self._print(f"{index:>4}  {readline.get_history_item(index)}")

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

        if not 0 <= args.slot <= MAX_SLOTS:
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
        self.files.mkdir(str(path_project), exists_okay=True)
        LOGGER.debug("Directory created.")
        LOGGER.debug("Uploading '%s' to '%s' ...", path_src, path_dest)
        _bytes = path_src.read_bytes()
        self.files.put(str(path_dest), _bytes)
        LOGGER.debug("Upload completed: [%d bytes]", len(_bytes))

        self._put_slot_configuration(config=config)
        LOGGER.info("Installed '%s' to slot #%d.", path_src, args.slot)

    @assert_connected
    def do_ll(self, args: str):
        """Alias 'ls -l'."""
        self.do_ls(f"-l {args}")

    @assert_connected
    @parse_arguments
    def do_ls(self, args: Namespace):
        # pylint: disable=too-many-branches
        """."""

        if not args.file:
            args.file.append("")
        paths = list(
            map(
                lambda file: normalize(path=self._apply_cwd(path=file)),
                args.file,
            )
        )  # typing: List[PurePath]

        # try:
        #     lines = self.spike_file_system.ls(
        #         directory=str(normalize(path=path)), long_format=show_size, recursive=recursive
        #     )
        #     for line in lines:
        #         self._print(line)
        # except RuntimeError as e:
        #     self._print("Failed to list directory contents: {}".format(e))

        # TODO: Add recursive
        for path in sorted(paths):
            # https://github.com/python/cpython/blob/main/Lib/stat.py#L36
            command = f"""
                    import os
                    r = []
                    path = '{str(path)}'
                    all = {args.all}
                    stats = os.stat(path)
                    if (stats[0] & 0o170000) == 0o040000:
                        if all:
                            r.append(['.'] + list(stats))
                            r.append(['..'] + list(os.stat(path + '/..')))
                        for entry in os.listdir(path + '/'):
                            path_entry = path + '/' + entry
                            r.append([path_entry] + list(os.stat(path_entry)))
                    else:
                        r.append([path] + list(stats))
                    print(r)
                    """
            output = None
            try:
                self.pyboard.enter_raw_repl()
                output = self.pyboard.exec_(dedent(command))
            except PyboardError as e:
                message = e.args[2].decode("utf-8")
                if message.find("OSError: [Errno 2] ENOENT") != -1:
                    LOGGER.error("File or directory does not exist: %s", path)
                    continue
            finally:
                self.pyboard.exit_raw_repl()

            if len(paths) > 1:
                self._print(f"{path}:")

            # Formatting ...
            def ls_sort(_stats: List) -> bool:
                if args.sort_size:
                    return _stats[7]
                return _stats[0]

            id_map = {"u0": "root", "g0": "root"}
            stats_array = literal_eval(
                output.decode(encoding="utf-8")
            )  # typing: List[List]
            if not args.sort_none:
                stats_array = sorted(stats_array, key=ls_sort)
            if args.sort_reverse:
                stats_array = reversed(stats_array)
            for stats in stats_array:
                modified = datetime.fromtimestamp(stats[9], tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                entry = PurePath(stats[0])
                if stats[0] != "." and stats[0] != "..":
                    entry = normalize(path=PurePath(stats[0]))
                    try:
                        entry = entry.relative_to(str(self.cwd))
                    except ValueError:
                        ...
                if args.long_list:
                    self._print(
                        f"{filemode(stats[1])} {stats[4]:>2} {id_map.get('u' + str(stats[5]), stats[5])} {id_map.get('g' + str(stats[6]), stats[6])} {stats[7]:>8} {modified} {entry}"
                    )
                else:
                    self._print(f"{entry}  ", end="")
            if not args.long_list:
                self._print("")

            if len(paths) > 1:
                self._print("")

    @assert_connected
    def do_quit(self, _: str):
        """Alias 'exit'."""
        self.do_exit("")

    @assert_connected
    @parse_arguments
    def do_rm(self, args: Namespace):
        """."""

        # Note: Intentionally do not support directories, multiple files, or force.

        path = self._apply_cwd(path=args.file)
        if not self._exists_file(path=path):
            LOGGER.error("File does not exist: %s", path)
            return

        if _path_protected(path=path):
            LOGGER.error("Protected Path: %s", path)
            return

        if not prompt_yes_no(title=f"Remove file: {path}?"):
            LOGGER.warning("User aborted operation!")
            return

        LOGGER.debug("Removing file: %s ...", path)
        self.files.rm(str(path))
        LOGGER.info("File removed.")

    @assert_connected
    def do_slots(self, args: str):
        """Alias 'status -s'."""

        self.do_status(f"-s {args}")

    @parse_arguments
    def do_status(self, args: Namespace):
        """."""

        config = None
        if self.connected and args.slots:
            config = self._get_slot_configuration()

        self._print(
            f"Status      : {ANSI_FG_GREEN + 'C' if self.connected else ANSI_FG_RED + 'Disc'}onnected{ANSI_NC}"
        )
        if self.connected:
            self._print(f"Device      : {self.pyboard.serial.name}")
            self._print(f"Device Name : {ANSI_FG_BLUE}{self.device_name}{ANSI_NC}")

            if args.slots:
                self._print("Slots       :")
                for i in range(MAX_SLOTS):
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
                        self._print(
                            f"    modified : {modified.strftime('%Y-%m-%d %H:%M:%S')}"
                        )

    @assert_connected
    @parse_arguments
    def do_uninstall(self, args: Namespace):
        """."""

        if not 0 <= args.slot <= MAX_SLOTS:
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

    @assert_connected
    @parse_arguments
    def do_upload(self, args: Namespace):
        """."""

        try:
            path_src = Path(args.source).resolve(strict=True)
        except FileNotFoundError as e:
            LOGGER.error(e.strerror)
            return

        if not path_src.is_file():
            LOGGER.error("Not a file: %s", path_src)
            return

        path_dest = self._apply_cwd(path=args.target if args.target else path_src.name)
        if self._exists_file(path=path_dest):
            if _path_protected(path=path_dest):
                LOGGER.error("Protected Path: %s", path_dest)
                return

            if not prompt_yes_no(title=f"Override existing file: {path_dest}?"):
                LOGGER.warning("User aborted operation!")
                return

        LOGGER.debug("Uploading '%s' to '%s' ...", path_src, path_dest)
        _bytes = path_src.read_bytes()
        self.files.put(str(path_dest), _bytes)
        LOGGER.info("Upload completed: [%d bytes]", len(_bytes))

    @assert_connected
    def do_vi(self, args: str):
        """Alias 'vim'."""
        self.do_vim(args)

    @assert_connected
    @parse_arguments
    def do_vim(self, args: Namespace):
        """."""

        path = self._apply_cwd(path=args.file)
        if not self._exists_file(path=path):
            LOGGER.error("File does not exist: %s", path)
            return

        if _path_protected(path=path):
            LOGGER.error("Protected Path: %s", path)
            return

        content = b""
        with NamedTemporaryFile(suffix=".tmp") as temp_file:
            path_temp_file = Path(temp_file.name)
            LOGGER.debug("Downloading '%s' to '%s' ...", path, path_temp_file)
            length = path_temp_file.write_bytes(self.files.get(path))
            temp_file.flush()
            LOGGER.info("Download completed: [%d bytes]", length)

            time_modified = path_temp_file.stat().st_mtime_ns
            return_code = call([EDITOR, "+set backupcopy=yes", temp_file.name])
            if return_code != 0:
                LOGGER.error("Editor failed: [editor=%s, rc=%d]", EDITOR, return_code)
                return
            if time_modified == path_temp_file.stat().st_mtime_ns:
                LOGGER.debug("File unchanged; aborting ...")
                return

            temp_file.seek(0)
            content = path_temp_file.read_bytes()

        LOGGER.debug("Uploading file: '%s' ...", path)
        self.files.put(str(path), content)
        LOGGER.info("Upload completed: [%d bytes]", len(content))
