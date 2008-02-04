from RepSys import Error, RepSysTree, config
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

#TODO logging for markrelease

DEFAULT_TARBALLS_REPO = "/tarballs"
BINLIST_PENDING = "repsys-upload"
BINLIST_DELETE = "repsys-delete"

class ChecksumError(Error):
    pass

def copy_rsync(sources, dest, sourcehost=None, desthost=None,
        archive=False, recurse=False):
    """Simple inteface for rsync"""
    args = ["rsync", "-i", "--log-format=\"%i %n\""]
    if archive:
        args.append("-a")
    if recurse:
        args.append("-r")
    if sourcehost:
        # "svn.mandriva.com:/foo/a /foo/b"
        #TODO space escaping needed for sources
        args.append("\"" + sourcehost + ":" + " ".join(sources) + "\"")
    else:
        args.extend(sources)
    if desthost:
        args.append(desthost + ":" + dest)
    else:
        args.append(dest)
    execcmd(show=True, *args)

def makedirs_remote(path, host):
    tmpdir = tempfile.mkdtemp(prefix="repsys-makedirs")
    try:
        newpath = os.path.normpath(tmpdir + "/" + path)
        os.makedirs(newpath)
        copy_rsync(sources=[tmpdir + "/"], dest="/", desthost=host, recurse=True)
    finally:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)

def copy(sources, dest, sourcehost=None, desthost=None, makedirs=False):
    """rsync-like copy

    Note that a copy between two dirs will result in overwriting the
    latter.
    """
    if desthost is None:
        # we only need dest to contain the host name
        try:
            desthost, dpath = dest.split(":", 1)
        except ValueError:
            dpath = dest
    if makedirs:
        if desthost:
            makedirs_remote(dpath, desthost)
        else:
            try:
                os.makedirs(dpath)
            except OSError, e:
                if e.errno != 17: # already exists
                    raise
    if sourcehost or desthost:
        copy_rsync(sources=sources, sourcehost=sourcehost, dest=dpath,
                desthost=desthost, recurse=True, archive=True)
    else:
        for source in sources:
            if os.path.isdir(source) and os.path.exists(dpath):
                #FIXME ugly workaround to behave consistently between
                # remote and local copies:
                try:
                    os.rmdir(dpath)
                except OSError, e:
                    raise Error, "can't overwrite directory: %s" % e
            execcmd("cp -al %s %s" % (source, dpath))

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
    use = config.getbool("global", "use-binaries-repository", False)
    default_parent = config.get("global", "default_parent", None)
    if url and use and default_parent and same_base(url, default_parent):
        return True
    return False

def target_url(path=None):
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
        raise ChecksumError, "different checksums for %s: expected %s, "\
                "but %s was found" % (path, sum, newsum)

def parse_sources_stream(stream):
    entries = {}
    for rawline in stream:
        line = rawline.strip()
        try:
            sum, name = line.split(None, 1)
        except ValueError:
            # failed to unpack, line format error
            raise Error, "invalid line in sources file: %s" % rawline
        entries[name] = sum
    return entries

def parse_sources(path, force=False):
    if not os.path.exists(path) and not force:
        return {}
    basedir = os.path.dirname(path)
    spath = os.path.join(basedir, "sources")
    f = open(spath)
    entries = parse_sources_stream(f)
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
    sname = config.get("binrepo", "sources-file", "sources")
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

def update_sources(paths):
    spath = sources_path(paths[0])
    entries = parse_sources(spath)
    added = []
    deleted = []
    for path in paths:
        name = os.path.basename(path)
        if os.path.exists(path):
            entries[name] = get_chksum(path)
            added.append(name)
        else:
            deleted.append(name)
            entries.pop(name, None)
    dump_sources(spath, entries)
    return added, deleted

def is_binary(path):
    raw = config.get("binrepo", "upload-match",
            "\.(gz|bz2|zip|Z|tar|xar|rpm|7z|lzma)$")
    maxsize = config.getint("binrepo", "upload-match-size", "1048576")
    expr = re.compile(raw)
    name = os.path.basename(path)
    if expr.search(name):
        return True
    st = os.stat(path)
    if st[stat.ST_SIZE] >= maxsize: # 1MiB
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

def is_tracked(path):
    spath = sources_path(path)
    entries = parse_sources(spath)
    name = os.path.basename(path)
    return name in entries

def upload(paths, auto=False):
    base = config.get("binrepo", "upload-command", 
            "/usr/share/repsys/binrepo-upload")
    if auto:
        paths = find_binaries(paths)
    else:
        for path in paths:
            if os.path.isdir(path):
                raise Error, "can't upload directories, try with -a"
    if not paths:
        raise Error, "nothing to upload" # is it an error?
    target = target_url(paths[0])
    copy(sources=paths, dest=target, makedirs=True)
    ad = update_sources(paths)
    return ad

def _binary_list_path(dirpath, name):
    fpath = os.path.join(dirpath, ".svn", name)
    return fpath

def _append_binary_list(path, listname):
    if os.path.isdir(path):
        raise Error, "only files can be uploaded"
    basedir = os.path.dirname(path)
    ppath = _binary_list_path(basedir, listname)
    f = open(ppath, "a+")
    f.write(os.path.basename(path) + "\n")
    f.close()

def _get_binary_list(dirpath, listname):
    ppath = _binary_list_path(dirpath, listname)
    if not os.path.exists(ppath):
        return []
    f = open(ppath)
    entries = [line.rstrip() for line in f]
    f.close()
    return entries

def _delete_binary_list(dirpath, listname):
    ppath = _binary_list_path(dirpath, listname)
    if os.path.exists(ppath):
        os.unlink(ppath)

def upload_pending(path):
    _append_binary_list(path, BINLIST_PENDING)

def delete_pending(path):
    _append_binary_list(path, BINLIST_DELETE)

def commit(dirpath):
    pending = [os.path.join(dirpath, name) for name in
                        _get_binary_list(dirpath, BINLIST_PENDING)]
    if pending:
        upload(pending)
        _delete_binary_list(dirpath, BINLIST_PENDING)
    delete = [os.path.join(dirpath, name) for name in
                        _get_binary_list(dirpath, BINLIST_DELETE)]
    if delete:
        remove(delete)
        _delete_binary_list(dirpath, BINLIST_DELETE)

def remove(paths):
    # we don't care what will happen to the sources file in the tarballs
    # repository, we just remove the reference to it
    spath = sources_path(paths[0])
    entries = parse_sources(spath)
    for path in paths:
        if os.path.exists(path):
            name = os.path.basename(path)
            if name not in entries:
                raise Error, "the file %s is not in the sources list" % path
            try:
                os.unlink(path)
            except (OSError, IOError), e:
                raise Error, "failed to unlink file: %s" % e
    ad = update_sources(paths)
    return ad

def remove_from_sources(path):
    #FIXME merge with remove() and update_sources()
    spath = sources_path(path)
    entries = parse_sources(spath)
    name = os.path.basename(path)
    try:
        del entries[name]
    except KeyError:
        pass
    dump_sources(spath, entries)

def markrelease(srcurl, desturl, version, release, revision):
    svn = SVN()
    target_root = target_url()
    source = target_url(srcurl)
    root = svn_root(srcurl)
    relpath = desturl[len(root):]
    target = os.path.normpath(target_root + "/" + relpath)
    #XXX rsync doesn't support remote paths in both src and dest, so we
    # assume we can do it only locally
    # so we strip the hostname:
    spath = source[source.find(":")+1:]
    tpath = target[target.find(":")+1:]
    tmproot = target_root[target_root.find(":")+1:]
    sname = config.get("binrepo", "sources-file", "sources")
    sourcesurl = os.path.join(srcurl, sname)
    try:
        stream = StringIO(svn.cat(sourcesurl, rev=revision))
    except Error:
        # we don't have a sources file, so there is nothing to copy
        return
    entries = parse_sources_stream(stream)
    paths = [os.path.join(spath, name) for name in entries]
    # we use target_url as tmproot trying to be 'hardlink friendly'
    tmpdir = tempfile.mkdtemp(prefix="repsys-markrelease-", dir=tmproot)
    try:
        # Check if the files we are going to markrelease are the right
        # ones.
        # We copy them to a temporary directory in order to be sure it will
        # not be changed after we have checked it. Note the comment about
        # being 'hardlink friendly': we are assuming rsync will also be
        # hardlink friendly and will create another file even to just
        # change some file in current/. Of course a dangerous assumption.
        copy(paths, tmpdir, makedirs=True)
        tmppaths = []
        for name, sum in entries.iteritems():
            path = os.path.join(tmpdir, name)
            try:
                check_hash(path, sum)
            except ChecksumError, e:
                raise Error, "can't create release: %s" % e
            tmppaths.append(path)
        copy(tmppaths, tpath, makedirs=True)
    finally:
        shutil.rmtree(tmpdir)

def download(target, url=None, check=True):
    targeturl = target_url(url or target)
    spath = sources_path(target)
    if not os.path.exists(spath):
        # we don't have external sources
        return
    entries = parse_sources(spath)
    try:
        host, path = targeturl.split(":", 1)
    except ValueError:
        host = None
        path = targeturl
    if os.path.isdir(target):
        paths = [os.path.join(path, name) for name, sum in entries.iteritems()]
        targetdir = target
    else:
        paths = [os.path.join(path, os.path.basename(target))]
        name = os.path.basename(target)
        targetdir = os.path.dirname(target)
        if name not in entries:
            raise Error, "file not uploaded yet (not found in "\
                    "sources file): %s" % target
    copy(sources=paths, sourcehost=host, dest=targetdir)
    yield "Checking files"
    if check:
        for path in paths:
            name = os.path.basename(path)
            bpath = os.path.join(targetdir, name)
            sum = entries[name]
            check_hash(bpath, sum)
    yield "Done"

