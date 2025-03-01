# lego-console

[![pypi version](https://img.shields.io/pypi/v/lego-console.svg)](https://pypi.org/project/lego-console)
[![build status](https://github.com/crashvb/lego-console/actions/workflows/main.yml/badge.svg)](https://github.com/crashvb/lego-console/actions)
[![coverage status](https://coveralls.io/repos/github/crashvb/lego-console/badge.svg)](https://coveralls.io/github/crashvb/lego-console)
[![python versions](https://img.shields.io/pypi/pyversions/lego-console.svg?logo=python&logoColor=FBE072)](https://pypi.org/project/lego-console)
[![linting](https://img.shields.io/badge/linting-pylint-yellowgreen)](https://github.com/PyCQA/pylint)
[![code style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![license](https://img.shields.io/github/license/crashvb/lego-console.svg)](https://github.com/crashvb/lego-console/blob/master/LICENSE.md)

## Overview

Console for Lego Mindstorm Inventor / Spike Prime.

Refactored from [recursivetree/spiketools](https://github.com/recursivetree/spiketools).

## Installation
### From [pypi.org](https://pypi.org/project/lego-console/)

```
$ pip install lego-console
```

### From source code

```bash
$ git clone https://github.com/crashvb/lego-console
$ cd lego-console
$ virtualenv env
$ source env/bin/activate
$ python -m pip install --editable .[dev]
```

## Usage

### Copying a python script to slot #3 ###

```bash
10:57:08 user@local-computer [~/lego-console]
$ lego-console start
Device connected.
10:57:14 MyLegoHub [/]
🤖: install -s 3 -t python my_project.py
Installed '/home/user/lego-console/my_project.py' to slot #3.
10:59:19 MyLegoHub [/]
🤖: slots
Status      : Connected
Device      : /dev/ttyACM0
Device Name : MyLegoHub
Slots       :
  0: <empty>
  1: <empty>
  2: <empty>
  3: my_project.py
    id       : 10003
    type     : python
    modified : 2025-03-01 10:58:24
  4: <empty>
  5: <empty>
  6: <empty>
  7: <empty>
  8: <empty>
  9: <empty>
10:59:22 MyLegoHub [/]
🤖: help

Documented commands (type help <topic>):
========================================
EOF  clear    disconnect  history  ls    slots      upload
cat  connect  download    install  quit  status     vi
cd   cp       exit        ll       rm    uninstall  vim

Undocumented commands:
======================
help

10:59:53 MyLegoHub [/]
🤖: exit
Device disconnected.
10:57:08 user@local-computer [~/lego-console]
$
```

### Environment Variables

| Variable | Default Value | Description |
| ---------| ------------- | ----------- |
| EDITOR | vim | The default system editor. |
| LC\_HISTFILE | ~/.lc\_history | The name of the file in which command history is saved. |
| LC\_HISTSIZE | 500 | The number of commands to remember in the command history. |

## Troubleshooting

### Unable to connect; no device provided!

Make sure the hub is powered on and connected via USB or bluetooth.

### Message: 'Unable to connect to device: /dev/...'

Make sure the user has permissions to the device.
* `/dev/ttyACM0` for  USB connections.
* `/dev/rfcomm0` for bluetooth connections.

## Development

[Source Control](https://github.com/crashvb/lego-console)
