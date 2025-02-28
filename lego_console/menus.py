#!/usr/bin/env python

"""Reusable menus."""

import logging

from typing import List, Optional

from consolemenu import MenuFormatBuilder, SelectionMenu

LOGGER = logging.getLogger(__name__)

DEFAULT_MENU_FORMAT = MenuFormatBuilder().show_header_bottom_border(True)


def prompt_device(
    devices: List[str], *, title: str = "Please select a device.", **kwargs
) -> Optional[str]:

    selection_menu = SelectionMenu(devices, title=title, **kwargs)
    selection_menu.show()
    if selection_menu.returned_value is None:
        LOGGER.warning("User aborted operation!")
        return None
    return devices[selection_menu.selected_item.index - 1]


def prompt_yes_no(
    title: str = "Do you want to continue?", *, no="No", yes="Yes", **kwargs
) -> bool:
    # pylint: disable=invalid-name
    selection_menu = SelectionMenu([yes], exit_option_text=no, title=title, **kwargs)
    selection_menu.show()
    return selection_menu.returned_value is not None
