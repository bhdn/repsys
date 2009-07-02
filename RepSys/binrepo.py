from RepSys import Error, config, mirror, layout
from RepSys.util import execcmd, rellink
from RepSys.svn import SVN

import os
import string
import stat
import shutil
import re
import tempfile
import urlparse
from cStringIO import StringIO

DEFAULT_TARBALLS_REPO = "/tarballs"
BINARIES_DIR_NAME = "SOURCES-bin"

PROP_USES_BINREPO = "mdv:uses-binrepo"
PROP_BINREPO_REV = "mdv:binrepo-rev"

BINREPOS_SECTION = "binrepos"

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

def default_repo():
    base = config.get("global", "binaries-repository", None)
    if base is None:
        default_parent = config.get("global", "default_parent", None)
        if default_parent is None:
            raise Error, "no binaries-repository nor default_parent "\
                    "configured"
        comps = urlparse.urlparse(default_parent)
        base = comps[1] + ":" + DEFAULT_TARBALLS_REPO
    return base

def translate_url(url):
    url = mirror.normalize_path(url)
    main = mirror.normalize_path(layout.repository_url())
    subpath = url[len(main)+1:]
    # [binrepos]
    # updates/2009.0 = svn+ssh://svn.mandriva.com/svn/binrepo/20090/
    ## svn+ssh://svn.mandriva.com/svn/packages/2009.0/trafshow/current
    # would translate to 
    # svn+ssh://svn.mandriva.com/svn/binrepo/20090/updates/trafshow/current/
    binbase = None
    if BINREPOS_SECTION in config.sections():
        for option, value in config.walk(BINREPOS_SECTION):
            if subpath.startswith(option):
                binbase = value
                break
    binurl = mirror._joinurl(binbase or default_repo(), subpath)
    return binurl

def translate_svndir(path):
    """Returns the URL in the binrepo from a given path inside a SVN
       checkout directory.

    @path: if specified, returns a URL in the binrepo whose path is the
           same as the path inside the main repository.
    """
    base = default_repo()
    target = mirror.normalize_path(base + "/" + svn_basedir(path))
    return target

def is_binary(path):
    raw = config.get("binrepo", "upload-match",
            "\.(gz|bz2|zip|Z|tar|xar|rpm|7z|lzma|tgz|tbz|tbz2)$")
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
        if not os.path.isdir(path) and not name.startswith("."):
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
    for destpath, linkpath in todo:
        os.symlink(linkpath, destpath)

def download(targetdir, pkgdirurl=None, export=False, show=True):
    assert not export or (export and pkgdirurl)
    svn = SVN()
    if not export and not svn.propget(PROP_USES_BINREPO, targetdir):
        return
    sourcespath = os.path.join(targetdir, "SOURCES")
    binpath = os.path.join(targetdir, BINARIES_DIR_NAME)
    if pkgdirurl:
        topurl = translate_url(pkgdirurl)
    else:
        topurl = translate_svndir(targetdir)
    binurl = mirror._joinurl(topurl, BINARIES_DIR_NAME)
    if export:
        svn.export(binurl, binpath, show=show)
    else:
        svn.checkout(binurl, binpath, show=show)
    make_symlinks(binpath, sourcespath)

def import_binaries(topdir, pkgname):
    """Import all binaries from a given package checkout

    (with pending svn adds)

    @topdir: the path to the svn checkout
    """
    svn = SVN()
    topurl = translate_svndir(topdir)
    sourcesdir = os.path.join(topdir, "SOURCES")
    bintopdir = tempfile.mktemp("repsys")
    if svn.propget(PROP_USES_BINREPO, topdir, noerror=1):
        svn.checkout(topurl, bintopdir)
        checkout = True
    else:
        bintopdir = tempfile.mkdtemp("repsys")
        checkout = False
    try:
        bindir = os.path.join(bintopdir, BINARIES_DIR_NAME)
        if not os.path.exists(bindir):
            if checkout:
                svn.mkdir(bindir)
            else:
                os.mkdir(bindir)
        for path in find_binaries([sourcesdir]):
            name = os.path.basename(path)
            binpath = os.path.join(bindir, name)
            os.rename(path, binpath)
            try:
                svn.remove(path)
            except Error:
                # file not tracked
                svn.revert(path)
            if checkout:
                svn.add(binpath)
        log = "imported binaries for %s" % pkgname
        if checkout:
            rev = svn.commit(bindir, log=log)
        else:
            rev = svn.import_(bintopdir, topurl, log=log)
        svn.propset(PROP_USES_BINREPO, "yes", topdir)
        svn.propset(PROP_BINREPO_REV, str(rev), topdir)
    finally:
        shutil.rmtree(bintopdir)

def create_package_dirs(bintopdir):
    svn = SVN()
    binurl = mirror._joinurl(bintopdir, BINARIES_DIR_NAME)
    silent = config.get("log", "ignore-string", "SILENT")
    message = "%s: created binrepo package structure" % silent
    svn.mkdir(binurl, log=message, parents=True)

def upload(path, message=None):
    from RepSys.rpmutil import getpkgtopdir
    svn = SVN()
    if not os.path.exists(path):
        raise Error, "not found: %s" % path
    # XXX check if the path is under SOURCES/
    paths = find_binaries([path])
    if not paths:
        raise Error, "'%s' does not seem to have any tarballs" % path
    topdir = getpkgtopdir()
    bintopdir = translate_svndir(topdir)
    binurl = mirror._joinurl(bintopdir, BINARIES_DIR_NAME)
    sourcesdir = os.path.join(topdir, "SOURCES")
    bindir = os.path.join(topdir, BINARIES_DIR_NAME)
    silent = config.get("log", "ignore-string", "SILENT")
    if not os.path.exists(bindir):
        try:
            download(topdir, show=False)
        except Error:
            pass
        if not os.path.exists(bindir):
            # possibly the package does not exist
            # (TODO check whether it is really a 'path not found' error)
            create_package_dirs(bintopdir)
            svn.propset(PROP_USES_BINREPO, "yes", topdir)
            svn.commit(topdir, log="%s: created binrepo structure" % silent)
            download(topdir, show=False)
    for path in paths:
        if svn.info2(path):
            raise Error, "'%s' is already tracked in svn" % path
        name = os.path.basename(path)
        binpath = os.path.join(bindir, name)
        os.rename(path, binpath)
        svn.add(binpath)
    if not message:
        message = "%s: new binary files %s" % (silent, " ".join(paths))
    rev = svn.commit(binpath, log=message)
    svn.propset(PROP_BINREPO_REV, str(rev), topdir)
    svn.commit(topdir, log=message)
    make_symlinks(bindir, sourcesdir)

def mapped_revision(url, revision):
    svn = SVN()
    binrev = svn.propget(PROP_BINREPO_REV, url)
    return binrev

def markrelease(sourceurl, releasesurl, version, release, revision):
    svn = SVN()
    if not svn.propget(PROP_USES_BINREPO, sourceurl):
        return
    binrev = mapped_revision(sourceurl, revision)
    binsource = translate_url(sourceurl)
    binreleases = translate_url(releasesurl)
    binversion = mirror._joinurl(binreleases, version)
    binrelease = mirror._joinurl(binversion, release)
    svn.mkdir(binreleases, noerror=1, log="created directory for releases")
    svn.mkdir(binversion, noerror=0, log="created directory for version %s" % version)
    svn.copy(binsource, binrelease, rev=binrev,
            log="%markrelease ver=%s rel=%s rev=%s binrev=%s" % (version, release,
                revision, binrev))
