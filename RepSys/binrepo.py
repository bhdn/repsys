from RepSys import Error, config
from RepSys.util import execcmd
from RepSys.svn import SVN
from RepSys.mirror import same_base

import os
import string
import stat
import sha
import shutil
import re
import tempfile
import urlparse
from cStringIO import StringIO

DEFAULT_TARBALLS_REPO = "/tarballs"

def svn_basedir(target):
    svn = SVN()
    info = svn.info2(target)
    if info is None:
        # unversioned resource
        newtarget = os.path.dirname(target)
        info = svn.info2(newtarget)
        assert info is not None, "svn_basedir should not be used with a "\
                "non-versioned directory"
    root = info["Repository Root"]
    url = info["URL"]
    kind = info["Node Kind"]
    path = url[len(root):]
    if kind == "directory":
        return path
    return os.path.dirname(path)

def svn_root(target):
    svn = SVN()
    info = svn.info2(target)
    if info is None:
        newtarget = os.path.dirname(target)
        info = svn.info2(newtarget)
        assert info is not None
    return info["Repository Root"]

def enabled(url):
    #TODO use information from url to find out whether we have a binrepo
    # available for this url
    use = config.getbool("global", "use-binaries-repository", False)
    return use

def binrepo_url(path=None):
    from RepSys.rpmutil import get_submit_info
    base = config.get("global", "binaries-repository", None)
    if base is None:
        default_parent = config.get("global", "default_parent", None)
        if default_parent is None:
            raise Error, "no binaries-repository nor default_parent "\
                    "configured"
        comps = urlparse.urlparse(default_parent)
        base = comps[1] + ":" + DEFAULT_TARBALLS_REPO
    if path:
        target = os.path.normpath(base + "/" + svn_basedir(path))
    else:
        target = base
    return target

def is_binary(path):
    raw = config.get("binrepo", "upload-match",
            "\.(gz|bz2|zip|Z|tar|xar|rpm|7z|lzma)$")
    maxsize = config.getint("binrepo", "upload-match-size", "1048576") # 1MiB
    expr = re.compile(raw)
    name = os.path.basename(path)
    if expr.search(name):
        return True
    st = os.stat(path)
    if st[stat.ST_SIZE] >= maxsize:
        return True
    return False

def find_binaries(paths):
    new = []
    for path in paths:
        if os.path.isdir(path):
            for name in os.listdir(path):
                fpath = os.path.join(path, name)
                if is_binary(fpath):
                    new.append(fpath)
        else:
            if is_binary(path):
                new.append(path)
    return new

def download(target, url=None):
    sourceurl = binrepo_url(url or target)    
    #copyurl = #XXX finish
