#!/usr/bin/python
from RepSys import Error, config, layout, mirror
from RepSys.svn import SVN
from RepSys.command import *
from RepSys.rpmutil import get_spec, get_submit_info
from RepSys.util import get_auth, execcmd, get_helper
import urllib
import getopt
import sys
import re
import subprocess
import uuid

import xmlrpclib

HELP = """\
Usage: repsys submit [OPTIONS] [URL[@REVISION] ...]

Submits the package from URL to the submit host.

The submit host will try to build the package, and upon successful
completion will 'tag' the package and upload it to the official
repositories.

The package name can refer to an alias to a group of packages defined in
the section submit-groups of the configuration file.

The status of the submit can visualized at:

http://kenobi.mandriva.com/bs/output.php

If no URL and revision are specified, the latest changed revision in the
package working copy of the current directory will be used.

Options:
    -t TARGET  Submit given package URL to given target
    -l         Just list available targets
    -r REV     Provides a revision number (when not providing as an
               argument)
    -s         The host in which the package URL will be submitted
               (defaults to the host in the URL)
    -p         Port used to connect to the submit host
    -a         Submit all URLs at once (depends on server-side support)
    -i SID     Use the submit identifier SID
    -h         Show this message
    --distro   The distribution branch where the packages come from
    --define   Defines one variable to be used by the submit scripts 
               in the submit host

Examples:
    repsys submit
    repsys submit foo
    repsys submit 2009.1/foo
    repsys submit foo@14800 bar baz@11001
    repsys submit https://repos/svn/mdv/cooker/foo
    repsys submit -l https://repos
    repsys submit 2008.1/my-packages@11011
    repsys submit --define section=main/testing -t 2008.1
"""

DEFAULT_TARGET = "Cooker"

def parse_options():
    parser = OptionParser(help=HELP)
    parser.defaults["revision"] = None
    parser.add_option("-t", dest="target", default=None)
    parser.add_option("-l", action="callback", callback=list_targets)
    parser.add_option("-r", dest="revision", type="string", nargs=1)
    parser.add_option("-s", dest="submithost", type="string", nargs=1,
            default=None)
    parser.add_option("-p", dest="port", type="int", default=None)
    parser.add_option("-i", dest="sid", type="string", nargs=1,
            default=None)
    parser.add_option("-a", dest="atonce", action="store_true", default=False)
    parser.add_option("--distro", dest="distro", type="string",
            default=None)
    parser.add_option("--define", action="append", default=[])
    opts, args = parser.parse_args()
    if not args:
        name, url, rev = get_submit_info(".")
        if opts.revision is not None:
            rev = opts.revision
        args = ["%s@%s" % (url, str(rev))]
        print "Submitting %s at revision %s" % (name, rev)
        print "URL: %s" % url
    if opts.revision is not None:
        # backwards compatibility with the old -r usage
        if len(args) == 1:
            args[0] = args[0] + "@" + opts.revision
        else:
            raise Error, "can't use -r REV with more than one package name"
    del opts.revision
    if len(args) == 2:
        # prevent from using the old <name> <rev> syntax
        try:
            rev = int(args[1])
        except ValueError:
            # ok, it is a package name, let it pass
            pass
        else:
            raise Error, "the format <name> <revision> is deprecated, "\
                    "use <name>@<revision> instead"
    # expand group aliases
    expanded = []
    for nameurl in args:
        expanded.extend(expand_group(nameurl))
    if expanded != args:
        print "Submitting: %s" % " ".join(expanded)
        args = expanded
    # generate URLs for package names:
    opts.urls = [mirror.strip_username(
                    layout.package_url(nameurl, distro=opts.distro, mirrored=False))
            for nameurl in args]
    # find the revision if not specified:
    newurls = []
    for url in opts.urls:
        if not "@" in url:
            print "Fetching revision..."
            courl = layout.checkout_url(url)
            log = SVN().log(courl, limit=1)
            if not log:
                raise Error, "can't find a revision for %s" % courl
            ci = log[0]
            print "URL:", url
            print "Commit:",
            print "%d | %s" % (ci.revision, ci.author),
            if ci.lines:
                line = " ".join(ci.lines).strip()
                if len(line) > 57:
                    line = line[:57] + "..."
                print "| %s" % line,
            print
            url = url + "@" + str(ci.revision)
        newurls.append(url)
    opts.urls[:] = newurls
    # choose a target if not specified:
    if opts.target is None and opts.distro is None:
        target = layout.distro_branch(opts.urls[0]) or DEFAULT_TARGET
        print "Implicit target: %s" % target
        opts.target = target
    del opts.distro
    return opts

def expand_group(group):
    name, rev = layout.split_url_revision(group)
    distro = None
    if "/" in name:
        distro, name = name.rsplit("/", 1)
    found = config.get("submit-groups", name)
    packages = [group]
    if found:
        packages = found.split()
        if rev:
            packages = [("%s@%s" % (package, rev))
                    for package in packages]
        if distro:
            packages = ["%s/%s" % (distro, package)
                    for package in packages]
    return packages

def list_targets(option, opt, val, parser):
    host = config.get("submit", "host")
    if host is None:
        raise Error, "no submit host defined in repsys.conf"
    createsrpm = get_helper("create-srpm")
    #TODO make it configurable
    command = "ssh %s %s --list" % (host, createsrpm)
    execcmd(command, show=True)
    sys.exit(0)

def submit(urls, target, define=[], submithost=None, port=None,
        atonce=False, sid=None):
    if submithost is None:
        submithost = config.get("submit", "host")
        if submithost is None:
            raise Error, "no submit host defined in configuration"
    if port is None:
        port = config.getint("submit", "port", "22")

    # runs a create-srpm in the server through ssh, which will make a
    # copy of the rpm in the export directory
    createsrpm = get_helper("create-srpm")
    baseargs = ["ssh", "-p", str(port), submithost, createsrpm,
            "-t", target]
    if not sid:
        sid = uuid.uuid4()
    define.append("sid=%s" % sid)
    for entry in reversed(define):
        baseargs.append("--define")
        baseargs.append(entry)
    cmdsargs = []
    if len(urls) == 1:
        # be compatible with server-side repsys versions older than 1.6.90
        url, rev = layout.split_url_revision(urls[0])
        baseargs.append("-r")
        baseargs.append(str(rev))
        baseargs.append(url)
        cmdsargs.append(baseargs)
    elif atonce:
        cmdsargs.append(baseargs + urls)
    else:
        cmdsargs.extend((baseargs + [url]) for url in urls)
    for cmdargs in cmdsargs:
        command = subprocess.list2cmdline(cmdargs)
        status, output = execcmd(command)
        if status == 0:
            print "Package submitted!"
        else:
            sys.stderr.write(output)
            sys.exit(status)

def main():
    do_command(parse_options, submit)

# vim:et:ts=4:sw=4
