#!/usr/bin/python
from RepSys.command import *
from RepSys.rpmutil import commit

HELP = """\
Usage: repsys ci [TARGET]

Will commit recent modifications in the package.

The difference between an ordinary "svn ci" and "repsys ci" is that it
relocates the working copy to the default repository in case the option
"mirror" is set in repsys.conf.

Options:
    -h      Show this message
    -m MSG  Use the MSG as the log message
    -F FILE Read log message from FILE

Examples:
    repsys ci
    repsys ci SPECS/package.spec SPECS/package-patch.patch
"""

def parse_options():
    parser = OptionParser(help=HELP)
    parser.add_option("-m", dest="message", default=None)
    parser.add_option("-F", dest="logfile", type="string",
            default=None)
    opts, args = parser.parse_args()
    if len(args):
        opts.target = args[0]
    return opts

def main():
    do_command(parse_options, commit)
