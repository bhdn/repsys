#!/usr/bin/python
from RepSys.command import *
from RepSys.rpmutil import sync

HELP = """\
Usage: repsys sync

Will add or removed from the working copy new files added or removed
from the spec file.

"No changes are commited."

Options:
    --dry-run    Print results without changing the working copy
    -c           Commit the changes, as in ci
    -h           Show this message

Examples:
    repsys sync
"""

def parse_options():
    parser = OptionParser(help=HELP)
    parser.add_option("--dry-run", dest="dryrun", default=False,
            action="store_true")
    parser.add_option("-c", dest="ci", default=False,
            action="store_true")
    opts, args = parser.parse_args()
    if len(args):
        opts.target = args[0]
    return opts

def main():
    do_command(parse_options, sync)
