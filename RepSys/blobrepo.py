from RepSys import Error, RepSysTree, config
from RepSys.util import execcmd
from RepSys.svn import SVN

import os
import string
import stat
import sha

DEFAULT_TARGET = "svn.mandriva.com:/tarballs/${svndir}"

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
    assert info is not None
    return info["Repository Root"]

class _LazyContextTargetConfig:
    #XXX add more useful information, such as "distro branch"
    def __init__(self, path):
        self.path = path

    def __getitem__(self, name):
        from RepSys.rpmutil import get_submit_info
        if not self.path:
            return ""
        if name == "svndir":
            return svn_basedir(self.path)
        elif name == "pkgname":
            return get_submit_info(self.path)[0]
        else:
            raise KeyError, name

def target_url(path, **kwargs):
    format = config.get("blobrepo", "target", DEFAULT_TARGET)
    tmpl = string.Template(format)
    if path:
        context = _LazyContextTargetConfig(path)
    else:
        # allow us to fetch get the base path of the target, without svn
        #FIXME horrible solution!
        context = _LazyContextTargetConfig(None)
    try:
        target = tmpl.safe_substitute(context)
    except KeyError, e:
        raise Error, "invalid variable in 'target' config option: %s" % e
    return target 

def file_hash(path):
    sum = sha.new()
    f = open(path)
    while True:
        block = f.read(4096)
        if not block:
            break
        sum.update(block)
    f.close()
    return sum.hexdigest()

def check_hash(path, sum):
    newsum = file_hash(path)
    if newsum != sum:
        raise Error, "different checksums for %s: %s != %s" % (path, newsum,
                sum)

def parse_sources(path, force=False):
    if not os.path.exists(path) and not force:
        return {}
    basedir = os.path.dirname(path)
    spath = os.path.join(basedir, "sources")
    entries = {}
    f = open(spath)
    for rawline in f:
        line = rawline.strip()
        try:
            sum, name = line.split(None, 1)
        except ValueError:
            # failed to unpack, line format error
            raise Error, "invalid line in sources file: %s" % rawline
        entries[name] = sum
    f.close()
    return entries

def dump_sources(path, entries):
    f = open(path, "w")
    for name in sorted(entries.keys()):
        #FIXME Unicode!
        sum = entries[name]
        f.write(sum + " " + name + "\n")
    f.close()

def sources_path(path):
    # returns the 'sources' file path for a give file path or directory
    sname = config.get("blobrepo", "sources-file", "sources")
    sdir = path
    if not os.path.isdir(path):
        sdir = os.path.dirname(path)
    spath = os.path.join(sdir, "sources")
    return spath

def get_chksum(path):
    sha1 = sha.new()
    f = open(path)
    while True:
        data = f.read(4096)
        if not data:
            break
        sha1.update(data)
    f.close()
    digest = sha1.hexdigest()
    return digest

def _update_sources(path, entries, added, deleted):
    name = os.path.basename(path)
    if os.path.exists(path):
        if os.path.isdir(path):
            for name in os.listdir(path):
                fpath = os.path.join(path, name)
                if os.path.isdir(fpath):
                    continue # we don't handle subdirs
                _update_sources(fpath, entries, added, deleted)
        else:
            sum = get_chksum(path)
            name = os.path.basename(path)
            entries[name] = sum
            added.append(name)

    else:
        deleted.append(name)
        try:
            del entries[name]
        except KeyError:
            pass

def update_sources(path):
    spath = sources_path(path)
    entries = parse_sources(spath)
    added = []
    deleted = []
    _update_sources(path, entries, added, deleted)
    dump_sources(spath, entries)
    return added, deleted

def find_blobs(paths):
    # for now match file name or size
    raw = config.get("blobrepo", "upload-match",
            "\.(gz|bz2|zip|Z|tar|xar|rpm|7z|lzma)$")
    expr = re.compile(raw)
    new = []
    for path in paths:
        if os.path.isdir(path):
            for name in os.listdir(path):
                if expr.search(name):
                    new.append(os.path.join(path, name))
                elif:
                    fpath = os.path.join(path, name)
                    st = os.stat(fpath)
                    if st[stat.ST_SIZE] > 0x100000: # 1MiB
                        new.append(fpath)
        else:
            name = os.path.basename(path)
            if expr.search(name):
                new.append(path)
    return new

def upload(paths, auto=False):
    base = config.get("blobrepo", "upload-command", 
            "/usr/share/repsys/blobrepo-upload")
    if auto:
        paths = find_blobs(paths)
    if not paths:
        raise Error, "nothing to upload" # is it an error?
    target = target_url(path)
    try:
        host, rpath = target.split(":", 1)
    except ValueError:
        host = ""
        rpath = target
    pathsline = " ".join(paths)
    cmd = "%s \"%s\" \"%s\" \"%s\" \"%s\" %s" % (base, path, target, host,
            rpath, pathsline)
    execcmd(cmd)
    ad = update_sources(paths)
    return ad

def remove(path):
    # we don't care what will happen to the sources file in the tarballs
    # repository, we just remove the reference to it
    if os.path.exists(path):
        spath = sources_path(path)
        entries = parse_sources(spath)
        name = os.path.basename(path)
        if name not in entries:
            raise Error, "the file %s is not in the sources list" % path
        try:
            os.unlink(path)
        except (OSError, IOError), e:
            raise Error, "failed to unlink file: %s" % e
    ad = update_sources(path)
    return ad

def markrelease(pkgdirurl, releaseurl, version, release, revision):
    base = config.get("blobrepo", "markrelease-command",
            "/usr/share/repsys/blobrepo-markrelease")
    target = target_url(pkgdirurl)
    root = svn_root(pkgdirurl)
    #FIXME completely wrong, should be from target_url
    newtarget = releaseurl[len(root):]
    try:
        host, path = target.split(":", 1)
    except ValueError:
        host = ""
        path = target
    try:
        ignored, newpath = newtarget.split(":", 1)
    except ValueError:
        newpath = newtarget
    cmd = "%s \"%s\" \"%s\" \"%s\" \"%s\" \"%s\"" % (base, pkgdirurl, target, host, path, newpath)
    execcmd(cmd)

def download(target, url=None):
    targeturl = target_url(url or target)
    spath = sources_path(target)
    if not os.path.exists(spath):
        # we don't have external sources
        return
    entries = parse_sources(spath)
    try:
        host, path = targeturl.split(":", 1)
    except ValueError:
        host = ""
        path = targeturl
    paths = [os.path.join(path, name) for name, sum in entries.iteritems()]
    base = config.get("blobrepo", "download-command",
            "/usr/share/repsys/blobrepo-download")
    pathsline = " ".join(paths)
    cmd = "%s \"%s\" \"%s\" \"%s\" %s" % (base, host, path, target,
            pathsline)
    execcmd(cmd)
    for name, sum in entries.iteritems():
        bpath = os.path.join(target, name)
        check_hash(bpath, sum)

