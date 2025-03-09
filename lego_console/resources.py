#!/usr/bin/env python

"""Resource management utilities."""

from pathlib import Path
from typing import AnyStr, Union

import pkg_resources


def get_path(*, path: Union[Path, str], name: str = __name__) -> Path:
    """
    Resolves the absolute path for a given relative path in reference to a file.

    Args:
        path: The relative path to be resolved.
        name: The name of the file from which to resolve the relative path.

    Returns:
        Path: The absolute path.
    """
    top_package = name[: name.index(".")]
    return Path(pkg_resources.resource_filename(top_package, path))


def get_text(*, path: Union[Path, str]) -> AnyStr:
    """
    Retrieves the contents of a file relative to this file.

    Args:
        path: The relative path of the file for which to retrieve the contents

    Returns:
        str: The contents of the file.
    """
    return get_path(path=path).read_text(encoding="utf-8")
