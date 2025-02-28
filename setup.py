#!/usr/bin/env python

import os
import re

from setuptools import setup, find_packages


def find_version(*segments):
    root = os.path.abspath(os.path.dirname(__file__))
    abspath = os.path.join(root, *segments)
    with open(abspath, "r") as file:
        content = file.read()
    match = re.search(r"^__version__ = ['\"]([^'\"]+)['\"]", content, re.MULTILINE)
    if match:
        return match.group(1)
    raise RuntimeError("Unable to find version string!")


setup(
    author="Richard Davis",
    author_email="crashvb@gmail.com",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Operating System :: POSIX :: Linux",
    ],
    description="Console for Lego Mindstorms Inventor / Spike Prime.",
    entry_points="""
        [console_scripts]
        lego-console=lego_console.cli:cli
    """,
    extras_require={
        "dev": [
            "black",
            "coveralls",
            "pylint",
            "pytest",
            "pytest-cov",
            "twine",
            "wheel",
        ]
    },
    include_package_data=True,
    install_requires=[
        "adafruit-ampy",
        "click",
        "console-menu",
        "crashvb-logging-utilities>=0.1.1",
        "pyserial",
        "pyyaml",
    ],
    keywords="console lego inventor mindstorms primespike",
    license="Apache License 2.0",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    name="lego_console",
    packages=find_packages(),
    package_data={"": ["data/*"]},
    project_urls={
        "Bug Reports": "https://github.com/crashvb/lego-console/issues",
        "Source": "https://github.com/crashvb/lego-console",
    },
    tests_require=["pytest"],
    test_suite="tests",
    url="https://pypi.org/project/lego-console/",
    version=find_version("lego_console", "__init__.py"),
)
