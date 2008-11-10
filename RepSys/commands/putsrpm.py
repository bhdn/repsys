#!/usr/bin/python
#
# This program will append a release to the Conectiva Linux package
# repository system.  It's meant to be a startup system to include
# pre-packaged SRPMS in the repository, thus, you should not commit
# packages over an ongoing package structure (with changes in current/
# directory and etc). Also, notice that packages must be included in
# cronological order.
#
from RepSys import Error
from RepSys.command import *
from RepSys.layout import package_url
from RepSys.rpmutil import put_srpm
import getopt
import sys, os

HELP = """\
*** WARNING --- You probably SHOULD NOT use this program! --- WARNING ***

Usage: repsys putsrpm [OPTIONS] REPPKGURL

Options:
    -m LOG  Use log when commiting changes
    -t      Create version-release tag on releases/
    -h      Show this message

Examples:
    repsys putsrpm file://svn/cnc/snapshot/foo /cnc/d/SRPMS/foo-1.0.src.rpm
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
