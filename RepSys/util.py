#!/usr/bin/python

from RepSys import Error, config

import subprocess
import getpass
import sys
import os
import re
import logging
from cStringIO import StringIO
#import commands

log = logging.getLogger("repsys")

# Our own version of commands' getstatusoutput(). We have a commands
# module directory, so we can't import Python's standard module
def commands_getstatusoutput(cmd):
    """Return (status, output) of executing cmd in a shell."""
    import os
    pipe = os.popen('{ ' + cmd + '; } 2>&1', 'r')
    text = pipe.read()
    sts = pipe.close()
    if sts is None: sts = 0
    if text[-1:] == '\n': text = text[:-1]
    return sts, text

def execcmd(*cmd, **kwargs):
    cmdstr = " ".join(cmd)
    if kwargs.get("show"):
        if kwargs.get("geterr"):
            err = StringIO()
            pipe = subprocess.Popen(cmdstr, shell=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            of = pipe.stdout.fileno()
            ef = pipe.stderr.fileno()
            while True:
                odata = os.read(of, 8192)
                sys.stdout.write(odata)
                edata = os.read(ef, 8192)
                err.write(edata)
                sys.stderr.write(edata)
                status = pipe.poll()
                if status is not None and not (odata and edata):
                    break
            output = err.getvalue()
        else:
            status = os.system(cmdstr)
            output = ""
    else:
        status, output = commands_getstatusoutput(
                "LANG=C LANGUAGE=C LC_ALL=C "+cmdstr)
    verbose = config.getbool("global", "verbose", 0)
    if status != 0 and not kwargs.get("noerror"):
        if kwargs.get("cleanerr") and not verbose:
            raise Error, output
        else:
            raise Error, "command failed: %s\n%s\n" % (cmdstr, output)
    if verbose:
        print cmdstr
        sys.stdout.write(output)
    return status, output

def get_auth(username=None, password=None):
    set_username = 1
    set_password = 1
    if not username:
        username = config.get("auth", "username")
        if not username:
            username = raw_input("username: ")
        else:
            set_username = 0
    if not password:
        password = config.get("auth", "password")
        if not password:
            password = getpass.getpass("password: ")
        else:
            set_password = 0
    if set_username:
        config.set("auth", "username", username)
    if set_password:
        config.set("auth", "password", password)
    return username, password


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

def rellink(src, dst):
    """Creates relative symlinks

    It will find the common ancestor and append to the src path.
    """
    asrc = os.path.abspath(src)
    adst = os.path.abspath(dst)
    csrc = asrc.split(os.path.sep)
    cdst = adst.split(os.path.sep)
    dstname = cdst.pop()
    i = 0
    l = min(len(csrc), len(cdst))
    while i < l:
        if csrc[i] != cdst[i]:
            break
        i += 1
    dstextra = len(cdst[i:])
    steps = [os.path.pardir] * dstextra
    steps.extend(csrc[i:])
    return os.path.sep.join(steps)
    

# vim:et:ts=4:sw=4
