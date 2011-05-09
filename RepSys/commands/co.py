#!/usr/bin/python
from RepSys import Error, disable_mirror
from RepSys.command import *
from RepSys.rpmutil import checkout
import getopt
import sys

HELP = """\
Usage: repsys co [OPTIONS] URL [LOCALPATH]

Checkout the package source from the Mandriva repository.

If the 'mirror' option is enabled, the package is obtained from the mirror
repository.

You can specify the distro branch to checkout from by using distro/pkgname.

Options:
    -d      The distribution branch to checkout from
    -b      The package branch
    -r REV  Revision to checkout
    -S      Do not download sources from the binaries repository
    -L      Do not make symlinks of the binaries downloaded in SOURCES/
    -s      Only checkout the SPECS/ directory
    -M      Do not use the mirror (use the main repository)
    --check Check integrity of files fetched from the binary repository
    -h      Show this message

Examples:
    repsys co pkgname
    repsys co -d 2009.0 pkgname
    repsys co 2009.0/pkgame
    repsys co http://repos/svn/cnc/snapshot/foo
    repsys co http://repos/svn/cnc/snapshot/foo foo-pkg
"""

def parse_options():
    parser = OptionParser(help=HELP)
    parser.add_option("-r", dest="revision")
    parser.add_option("-S", dest="use_binrepo", default=True,
            action="store_false")
    parser.add_option("--check", dest="binrepo_check", default=False,
            action="store_true")
    parser.add_option("-L", dest="binrepo_link", default=True,
            action="store_false")
    parser.add_option("--distribution", "-d", dest="distro", default=None)
    parser.add_option("--branch", "-b", dest="branch", default=None)
    parser.add_option("-s", "--spec", dest="spec", default=False,
            action="store_true")
    parser.add_option("-M", "--no-mirror", action="callback",
            callback=disable_mirror)
    opts, args = parser.parse_args()
    if len(args) not in (1, 2):
        raise Error, "invalid arguments"
    # here we don't use package_url in order to notify the user we are
    # using the mirror
    opts.pkgdirurl = args[0]
    if len(args) == 2:
        opts.path = args[1]
    else:
        opts.path = None
    return opts

def main():
    do_command(parse_options, checkout)

# vim:et:ts=4:sw=4
