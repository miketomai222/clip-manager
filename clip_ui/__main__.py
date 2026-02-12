"""Entry point for the clip-manager UI."""

import argparse
import sys

from clip_common import __version__


def main():
    parser = argparse.ArgumentParser(description="Clip Manager UI")
    parser.add_argument("--version", action="version", version=f"clip-ui {__version__}")
    args = parser.parse_args()


if __name__ == "__main__":
    main()
