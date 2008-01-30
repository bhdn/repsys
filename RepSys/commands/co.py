#!/usr/bin/python
from RepSys import Error
from RepSys.command import *
from RepSys.rpmutil import checkout
import getopt
import sys

HELP = """\
Usage: repsys co [OPTIONS] URL [LOCALPATH]

Checkout the package source from the Mandriva repository.

If the 'mirror' option is enabled, the package is obtained from the mirror
repository.

Options:
    -r REV  Revision to checkout
    -o      Do not use the mirror (use official server)
    -S      Do not download sources from the binaries repository
    -h      Show this message

Examples:
    repsys co pkgname
    repsys co http://repos/svn/cnc/snapshot/foo
    repsys co http://repos/svn/cnc/snapshot/foo foo-pkg
"""

def parse_options():
    parser = OptionParser(help=HELP)
    parser.add_option("-r", dest="revision")
    parser.add_option("-o", dest="use_mirror", default=True,
            action="store_false")
    parser.add_option("-S", dest="use_binrepo", default=True,
            action="store_false")
    opts, args = parser.parse_args()
    if len(args) not in (1, 2):
        raise Error, "invalid arguments"
    opts.pkgdirurl = args[0]
    if len(args) == 2:
        opts.path = args[1]
    else:
        opts.path = None
    return opts

def main():
    do_command(parse_options, checkout)

# vim:et:ts=4:sw=4
