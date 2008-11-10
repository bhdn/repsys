#!/usr/bin/python
from RepSys import Error
from RepSys.command import *
from RepSys.layout import package_url
from RepSys.rpmutil import put_srpm
import getopt
import sys, os

HELP = """\
Usage: repsys putsrpm [OPTIONS] SOURCERPMS

Will import source RPMs into the SVN repository.

If the package was already imported, it will add the new files and remove
those not present in the source RPM.

Options:
    -m LOG  Log message used when commiting changes
    -t      Create version-release tag on releases/
    -h      Show this message

Examples:
    repsys putsrpm pkg/SRPMS/pkg-2.0-1.src.rpm
"""

def parse_options():
    parser = OptionParser(help=HELP)
    parser.add_option("-l", dest="logmsg", default="")
    parser.add_option("-t", dest="markrelease", action="store_true",
            default=False)
    opts, args = parser.parse_args()
    opts.srpmfiles = args
    return opts

def put_srpm_cmd(srpmfiles, markrelease, logmsg=None):
    for path in srpmfiles:
        put_srpm(path, markrelease, logmsg)

def main():
    do_command(parse_options, put_srpm_cmd)

# vim:et:ts=4:sw=4
