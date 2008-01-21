from RepSys import Error, RepSysTree, config
from RepSys.util import execcmd
from RepSys.svn import SVN

import os
import string
import sha

def svn_basedir(target):
    svn = SVN()
    info = svn.info2(target)
    root = info["Repository Root"]
    url = info["URL"]
    kind = info["Node Kind"]
    path = url[len(root):]
    if kind == "directory":
        return path
    return os.path.dirname(path)

class _LazyContextTargetConfig:
    #XXX add more useful information, such as "distro branch"
    def __init__(self, path):
        self.path = path

    def __getitem__(self, name):
        from RepSys.rpmutil import get_submit_info
        if name == "svndir":
            return svn_basedir(self.path)
        elif name == "pkgname":
            return get_submit_info(self.path)[0]
        else:
            raise KeyError, name

def target_url(path):
    format = config.get("blobrepo", "target",
            "svn.mandriva.com:/tarballs/${svndir}")
    tmpl = string.Template(format)
    try:
        target = tmpl.substitute(_LazyContextTargetConfig(path))
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
    for name, sum in entries.iteritems():
        #FIXME Unicode!
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

def upload(path):
    base = config.get("blobrepo", "upload-command", 
            "/usr/share/repsys/blobrepo-upload")
    target = target_url(path)
    try:
        host, rpath = target.split(":", 1)
    except ValueError:
        host = ""
        rpath = target
    cmd = "%s \"%s\" \"%s\" \"%s\" \"%s\"" % (base, path, target, host, rpath)
    execcmd(cmd)
    ad = update_sources(path)
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
    newtarget = target_url(releaseurl)
    try:
        host, path = target.split(":", 1)
    except ValueError:
        host = ""
        path = target
    try:
        ignored, newpath = target.split(":", 1)
    except ValueError:
        newpath = newtarget
    cmd = "%s \"%s\" \"%s\" \"%s\" \"%s\" \"%s\"" % (base, pkgdirurl, target, host, path, newpath)
    execcmd(cmd)

