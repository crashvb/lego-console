#!/usr/bin/env python

# pylint: disable=too-many-lines

"""Console for Lego Mindstorms Inventor / Spike Prime."""

import logging
import os
import re
import readline
from argparse import (
    Namespace,
)
from ast import literal_eval
from cmd import Cmd
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path, PurePath
from stat import filemode, S_ISDIR, S_ISREG
from subprocess import call
from tempfile import NamedTemporaryFile
from textwrap import dedent
from typing import IO, List, Optional, Union

from ampy.files import Files
from ampy.pyboard import Pyboard, PyboardError
from serial.tools.list_ports import comports

from .consts import (
    ANSI_FG_GREEN,
    ANSI_FG_RED,
    ANSI_FG_BLUE,
    ANSI_NC,
)
from .helpers.alias_helper import AliasHelper
from .helpers.parser_helper import ParserHelper
from .menus import prompt_device, prompt_yes_no
from .paths import is_path_protected
from .subcommands.slots import Slots
from .utils import (
    assert_connected,
    check_mutually_exclusive,
    normalize_path,
    parse_arguments,
)

LOGGER = logging.getLogger(__name__)

DUCK_PUNCH_ERROR_FLAG = "argparse flow control sucks!"

EDITOR = os.environ.get("EDITOR", "vim")

FILE_EXTENSIONS = ["mpy", "py"]

MAX_SLOTS = 10

PATH_LOCAL_NAME = PurePath("/local_name.txt")
PATH_PROJECTS = PurePath("/projects")
PATH_SLOTS = PurePath(f"{PATH_PROJECTS}/.slots")

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


def _format_size_automatic(*, factor: float = 1024.0, size: int) -> str:
    for x in SIZE_UNITS:
        if size < factor:
            size = max(1.0, size)
            return f"{size:3.{0 if size >= 10 else 1}f}{x}"
        size /= factor
    return f"{size:3.0f}Y"


def _format_size_explicit(*, factor: str = "K", size: int) -> str:
    return f"{max(1, int(size / (1024.0 ** SIZE_UNITS.index(factor))))}{factor}"


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
        self.alias_helper = AliasHelper(
            aliases={
                "exit": ["EOF", "quit"],
                "help": ["man"],
                "ls -l": ["ll"],
                "vim": ["vi"],
            }
        )
        self.auto_connect: bool = auto_connect
        self.connected: bool = False
        self.cwd: PurePath = PurePath("/")
        self.cwd_old: PurePath = self.cwd
        self.device_name: Optional[str] = None
        self.files: Optional[Files] = None
        self.history_file = history_file
        self.history_size = history_size
        self.max_slots = MAX_SLOTS
        self.parser_helper = ParserHelper(
            max_slots=self.max_slots, _print=self._print, stdout=self.stdout
        )
        self.pyboard: Optional[Pyboard] = None

    @assert_connected
    def __exec(self, *, command: str) -> bytes:
        try:
            self.pyboard.enter_raw_repl()
            return self.pyboard.exec_(dedent(command))
        finally:
            self.pyboard.exit_raw_repl()

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

    def _get_slots(self):
        # TODO: Refactor sub-command prompt construction to allow caching
        return Slots(lego_console=self, parser_helper=self.parser_helper)

    @assert_connected
    def _os_stats(self, *, path: PurePath) -> Optional[List]:
        command = f"""
                import os
                path = '{str(path)}'
                print(os.stat(path))
                """
        try:
            _bytes = self.__exec(command=command)
            return literal_eval(_bytes.decode(encoding="utf-8"))
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
            _bytes = self.__exec(command=command)
            return literal_eval(_bytes.decode(encoding="utf-8"))
        except PyboardError as e:
            message = e.args[2].decode("utf-8")
            if message.find("OSError: [Errno 2] ENOENT") != -1:
                return None
            raise e

    def _print(
        self,
        *args,
        sep: str = " ",
        end: str = "\n",
        file: Optional[IO[str]] = None,
        flush: bool = False,
    ):
        file = file if file else self.stdout
        file.write(f"{sep.join(args)}{end}")
        if flush:
            file.flush()

    def _read_history(self):
        if self.history_file and self.history_file.is_file():
            LOGGER.debug("Reading history file: %s ...", self.history_file)
            readline.read_history_file(self.history_file)
            LOGGER.debug("Read %d lines.", readline.get_current_history_length())

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
        line_new = self.alias_helper.resolve(line=line)
        if line_new:
            return self.onecmd(line_new)
        self._print(f"{line}: command not found")
        return None

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

    def do_alias(self, args: str):
        """Define or display aliases."""

        for name, value in self.alias_helper.get().items():
            self._print(f"alias {name}='{value}'")

    @assert_connected
    @parse_arguments
    def do_cat(self, args: Namespace):
        # pylint: disable=too-many-branches
        """."""

        paths = list(
            map(
                lambda file: normalize_path(path=self._apply_cwd(path=file)),
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
        path = normalize_path(path=self._apply_cwd(path=args.directory))
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

        if not check_mutually_exclusive(args=args, arg_names=["backup", "no_clobber"]):
            LOGGER.error(
                "Options --backup (-b) and --no-clobber (-n) are mutually exclusive."
            )
            return

        path_dest = self._apply_cwd(path=args.destination)
        path_srcs = list(
            map(
                lambda file: normalize_path(path=self._apply_cwd(path=file)),
                args.source,
            )
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
                if is_path_protected(path=path_target):
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

        if not check_mutually_exclusive(
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

    def do_exit(self, _: str):
        """
        Usage: exit
        Cause normal process termination.
        """
        self._disconnect()
        return True

    @parse_arguments
    def do_help(self, arg: Namespace):
        # Note: "arg" instead of "args" to match prototype
        topic = arg.topic if hasattr(arg, "topic") else ""
        if topic:
            topic_new = self.alias_helper.resolve(line=topic)
            if topic_new:
                topic = topic_new
                self._print(f"alias: {topic_new}\n")
            try:
                argument_parser = self.parser_helper.get_parser(
                    cls=type(self).__name__, command=topic
                )
                argument_parser.print_help(file=self.stdout)
                return None
            except RuntimeError:
                ...
        return Cmd.do_help(self, topic)

    @parse_arguments
    def do_history(self, args: Namespace):
        """."""

        # https://github.com/bminor/bash/blob/6794b5478f660256a1023712b5fc169196ed0a22/builtins/history.def#L164
        if not check_mutually_exclusive(args=args, arg_names=["read", "write"]):
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
    def do_ls(self, args: Namespace):
        # pylint: disable=too-many-branches
        """."""

        if not args.file:
            args.file.append("")
        paths = list(
            map(
                lambda file: normalize_path(path=self._apply_cwd(path=file)),
                args.file,
            )
        )  # typing: List[PurePath]

        # try:
        #     lines = self.spike_file_system.ls(
        #         directory=str(normalize_path(path=path)), long_format=show_size, recursive=recursive
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
                    entry = normalize_path(path=PurePath(stats[0]))
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
    @parse_arguments
    def do_rm(self, args: Namespace):
        """."""

        # Note: Intentionally do not support directories, multiple files, or force.

        path = self._apply_cwd(path=args.file)
        if not self._exists_file(path=path):
            LOGGER.error("File does not exist: %s", path)
            return

        if is_path_protected(path=path):
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
        """Sub-command for interacting with slots."""
        slots = self._get_slots()
        if args:
            # Facilitate sub-command passthrough
            slots.cmdqueue.append(args)
            slots.postcmd = lambda _self, _args: True
        slots.cmdloop()

    @parse_arguments
    def do_status(self, args: Namespace):
        """."""

        self._print(
            f"Status      : {ANSI_FG_GREEN + 'C' if self.connected else ANSI_FG_RED + 'Disc'}onnected{ANSI_NC}"
        )
        if self.connected:
            self._print(f"Device      : {self.pyboard.serial.name}")
            self._print(f"Device Name : {ANSI_FG_BLUE}{self.device_name}{ANSI_NC}")

            if args.slots:
                self._get_slots().do_status("")

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
            if is_path_protected(path=path_dest):
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
    @parse_arguments
    def do_vim(self, args: Namespace):
        """."""

        path = self._apply_cwd(path=args.file)
        if not self._exists_file(path=path):
            LOGGER.error("File does not exist: %s", path)
            return

        if is_path_protected(path=path):
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
