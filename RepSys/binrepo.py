from RepSys import Error, config, mirror
from RepSys.util import execcmd, rellink
from RepSys.svn import SVN

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
BINARIES_DIR_NAME = "SOURCES-bin"

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
        target = mirror.normalize_path(base + "/" + svn_basedir(path))
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

def make_symlinks(source, dest):
    todo = []
    tomove = []
    for name in os.listdir(source):
        path = os.path.join(source, name)
        if not os.path.isdir(path) and not path.startswith("."):
            destpath = os.path.join(dest, name)
            linkpath = rellink(path, destpath)
            if os.path.exists(destpath):
                if os.path.islink(destpath):
                    if os.readlink(destpath) == linkpath:
                        continue
                movepath = destpath + ".repsys-moved"
                if os.path.exists(movepath):
                    raise Error, "cannot create symlink, %s already "\
                            "exists (%s too)" % (destpath, movepath)
                tomove.append((destpath, movepath))
            todo.append((destpath, linkpath))
    for destpath, movepath in tomove:
        os.rename(destpath, movepath)
        yield "moved", destpath, movepath
    for destpath, linkpath in todo:
        os.symlink(linkpath, destpath)
        yield "symlink", destpath, linkpath

def download(target, pkgdirurl):
    sourcespath = os.path.join(target, "SOURCES")
    binpath = os.path.join(target, BINARIES_DIR_NAME)
    topurl = binrepo_url(target)
    binurl = mirror._joinurl(topurl, BINARIES_DIR_NAME)
    svn = SVN()
    svn.checkout(binurl, binpath, show=1)
    for status in make_symlinks(binpath, sourcespath):
        yield status
