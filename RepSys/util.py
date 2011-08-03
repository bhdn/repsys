#!/usr/bin/python

from RepSys import Error, config

import shlex
import subprocess
import select
import sys
import os
import re
from cStringIO import StringIO

class CommandError(Error):

    def __init__(self, cmdline, status, output):
        self.cmdline = cmdline
        self.status = status
        self.output = output

    def __str__(self):
        return "command failed: %s\n%s\n" % (self.cmdline, self.output)

def execcmd(cmd_args_or_str, show=False, collecterr=False, cleanerr=False,
        noerror=False, strip=True):
    assert (collecterr and show) or not collecterr, ("execcmd is implemented to "
            "handle collecterr=True only if show=True")

    # split command args
    if isinstance(cmd_args_or_str, basestring):
        cmdargs = shlex.split(cmd_args_or_str)
    else:
        cmdargs = cmd_args_or_str[:]

    stdout = None
    stderr = None
    env = {}
    env.update(os.environ)
    if not show or (show and collecterr):
        env.update({"LANG": "C", "LANGUAGE": "C", "LC_ALL": "C"})
        stdout = subprocess.PIPE
        if collecterr:
            stderr = subprocess.PIPE
        else:
            stderr = subprocess.STDOUT

    proc = subprocess.Popen(cmdargs, shell=False, stdout=stdout,
            stderr=stderr, env=env)

    output = ""

    if show and collecterr:
        error = StringIO()
        wl = []
        outfd = proc.stdout.fileno()
        errfd = proc.stderr.fileno()
        rl = [outfd, errfd]
        xl = wl
        while proc.poll() is None:
            mrl, _, _ = select.select(rl, wl, xl, 0.5)
            for fd in mrl:
                data = os.read(fd, 8192)
                if fd == errfd:
                    error.write(data)
                    sys.stderr.write(data)
                else:
                    sys.stdout.write(data)
        output = error.getvalue()
    else:
        proc.wait()
        if proc.stdout is not None:
            output = proc.stdout.read()
            if strip:
                output = output.rstrip()

    if (not noerror) and proc.returncode != 0:
        if cleanerr:
            msg = output
        cmdline = subprocess.list2cmdline(cmdargs)
        raise CommandError(cmdline, proc.returncode, output)

    return proc.returncode, output

def mapurl(url):
    """Maps a url following the regexp provided by the option url-map in
    repsys.conf
    """
    urlmap = config.get("global", "url-map")
    newurl = url
    if urlmap:
        try:
            expr_, replace = urlmap.split()[:2]
        except ValueError:
            log.error("invalid url-map: %s", urlmap)
        else:
            try:
                newurl = re.sub(expr_, replace, url)
            except re.error, errmsg:
                log.error("error in URL mapping regexp: %s", errmsg)
    return newurl


def get_helper(name):
    """Tries to find the path of a helper script

    It first looks if the helper has been explicitly defined in
    configuration, if not, falls back to the default helper path, which can
    also be defined in configuration file(s).
    """
    helperdir = config.get("helper", "prefix", "/usr/share/repsys")
    hpath = config.get("helper", name, None) or \
            os.path.join(helperdir, name)
    if not os.path.isfile(hpath):
        log.warn("providing unexistent helper: %s", hpath)
    return hpath
    

# vim:et:ts=4:sw=4
