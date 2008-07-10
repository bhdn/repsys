#!/usr/bin/python
from RepSys import Error, config
from RepSys import mirror, layout, binrepo
from RepSys.svn import SVN
from RepSys.simplerpm import SRPM
from RepSys.log import specfile_svn2rpm
from RepSys.util import execcmd
from RepSys.command import default_parent
import rpm
import urlparse
import tempfile
import shutil
import string
import glob
import sys
import os

def get_spec(pkgdirurl, targetdir=".", submit=False):
    svn = SVN()
    tmpdir = tempfile.mktemp()
    try:
        geturl = layout.checkout_url(pkgdirurl, append_path="SPECS")
        svn.export("'%s'" % geturl, tmpdir)
        speclist = glob.glob(os.path.join(tmpdir, "*.spec"))
        if not speclist:
            raise Error, "no spec files found"
        spec = speclist[0]
        shutil.copy(spec, targetdir)
    finally:
        if os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir)

def rpm_macros_defs(macros):
    defs = ("--define \"%s %s\"" % macro for macro in macros)
    args = " ".join(defs)
    return args

#FIXME move it to another module
def rev_touched_url(url, rev):
    svn = SVN()
    info = svn.info2(url)
    if info is None:
        raise Error, "can't fetch svn info about the URL: %s" % url
    root = info["Repository Root"]
    urlpath = url[len(root):]
    touched = False
    entries = svn.log(root, start=rev, limit=1)
    entry = entries[0]
    for change in entry.changed:
        path = change.get("path")
        if path and path.startswith(urlpath):
            touched = True
    return touched

def get_srpm(pkgdirurl,
             mode = "current",
             targetdirs = None,
             version = None,
             release = None,
             revision = None,
             packager = "",
             revname = 0,
             svnlog = 0,
             scripts = [], 
             submit = False,
             template = None,
             macros = [],
             verbose = 0,
             strict = False,
             use_binrepo = False,
             binrepo_check = True):
    svn = SVN()
    tmpdir = tempfile.mktemp()
    topdir = "--define '_topdir %s'" % tmpdir
    builddir = "--define '_builddir %s/%s'" % (tmpdir, "BUILD")
    rpmdir = "--define '_rpmdir %s/%s'" % (tmpdir, "RPMS")
    sourcedir = "--define '_sourcedir %s/%s'" % (tmpdir, "SOURCES")
    specdir = "--define '_specdir %s/%s'" % (tmpdir, "SPECS")
    srcrpmdir = "--define '_srcrpmdir %s/%s'" % (tmpdir, "SRPMS")
    patchdir = "--define '_patchdir %s/%s'" % (tmpdir, "SOURCES")

    try:
        if mode == "version":
            geturl = layout.checkout_url(pkgdirurl, version=version,
                    release=release)
        elif mode == "pristine":
            geturl = layout.checkout_url(pkgdirurl, pristine=True)
        elif mode == "current" or mode == "revision":
            #FIXME we should handle revisions specified using @REV
            geturl = layout.checkout_url(pkgdirurl)
        else:
            raise Error, "unsupported get_srpm mode: %s" % mode
        strict = strict or config.getbool("submit", "strict-revision", False)
        if strict and not rev_touched_url(geturl, revision):
            #FIXME would be nice to have the revision number even when
            # revision is None
            raise Error, "the revision %s does not change anything "\
                    "inside %s" % (revision or "HEAD", geturl)
        mirror.info(geturl)
        svn.export(geturl, tmpdir, rev=revision)
        if use_binrepo:
            download_binaries(tmpdir, geturl, check=binrepo_check)
        srpmsdir = os.path.join(tmpdir, "SRPMS")
        os.mkdir(srpmsdir)
        specsdir = os.path.join(tmpdir, "SPECS")
        speclist = glob.glob(os.path.join(specsdir, "*.spec"))
        if not speclist:
            raise Error, "no spec files found"
        spec = speclist[0]
        if svnlog:
            submit = not not revision
            specfile_svn2rpm(pkgdirurl, spec, revision, submit=submit,
                    template=template, macros=macros, exported=tmpdir)
        for script in scripts:
            #FIXME revision can be "None"
            status, output = execcmd(script, tmpdir, spec, str(revision),
                                     noerror=1)
            if status != 0:
                raise Error, "script %s failed" % script
        if packager:
            packager = " --define 'packager %s'" % packager

        defs = rpm_macros_defs(macros)
        execcmd("rpm -bs --nodeps %s %s %s %s %s %s %s %s %s %s" %
            (topdir, builddir, rpmdir, sourcedir, specdir, 
             srcrpmdir, patchdir, packager, spec, defs))

        # copy the generated SRPMs to their target locations
        targetsrpms = []
        urlrev = None
        if revname:
            urlrev = revision or layout.get_url_revision(geturl)
        if not targetdirs:
            targetdirs = (".",)
        srpms = glob.glob(os.path.join(srpmsdir, "*.src.rpm"))
        if not srpms:
            # something fishy happened
            raise Error, "no SRPMS were found at %s" % srpmsdir
        for srpm in srpms:
            name = os.path.basename(srpm)
            if revname:
                name = "@%s:%s" % (urlrev, name)
            for targetdir in targetdirs:
                newpath = os.path.join(targetdir, name)
                targetsrpms.append(newpath)
                if os.path.exists(newpath):
                    # should we warn?
                    os.unlink(newpath)
                shutil.copy(srpm, newpath)
                if verbose:
                    sys.stderr.write("Wrote: %s\n" %  newpath)
        return targetsrpms
    finally:
        if os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir)

def patch_spec(pkgdirurl, patchfile, log=""):
    #FIXME use get_spec
    svn = SVN()
    tmpdir = tempfile.mktemp()
    try:
        geturl = layout.checkout_url(pkgdirurl, append_path="SPECS")
        svn.checkout(geturl, tmpdir)
        speclist = glob.glob(os.path.join(tmpdir, "*.spec"))
        if not speclist:
            raise Error, "no spec files found"
        spec = speclist[0]
        status, output = execcmd("patch", spec, patchfile)
        if status != 0:
            raise Error, "can't apply patch:\n%s\n" % output
        else:
            svn.commit(tmpdir, log="")
    finally:
        if os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir)

def put_srpm(pkgdirurl, srpmfile, appendname=0, log=""):
    srpm = SRPM(srpmfile)
    if appendname:
        pkgdirurl = "/".join([pkgdirurl, srpm.name])
    svn = SVN()
    tmpdir = tempfile.mktemp()
    try:
        if srpm.epoch:
            version = "%s:%s" % (srpm.epoch, srpm.version)
        else:
            version = srpm.version
        versionurl = "/".join([pkgdirurl, "releases", version])
        releaseurl = "/".join([versionurl, srpm.release])
        #FIXME when pre-commit hook fails, there's no clear way to know
        # what happened
        ret = svn.mkdir(pkgdirurl, noerror=1, log="Created package directory")
        if ret:
            svn.checkout(pkgdirurl, tmpdir)
            svn.mkdir(os.path.join(tmpdir, "releases"))
            svn.mkdir(os.path.join(tmpdir, "releases", version))
            svn.mkdir(os.path.join(tmpdir, "current"))
            svn.mkdir(os.path.join(tmpdir, "current", "SPECS"))
            svn.mkdir(os.path.join(tmpdir, "current", "SOURCES"))
            #svn.commit(tmpdir,log="Created package structure.")
            version_exists = 1
            currentdir = os.path.join(tmpdir, "current")
        else:
            if svn.ls(releaseurl, noerror=1):
                raise Error, "release already exists"
            svn.checkout("/".join([pkgdirurl, "current"]), tmpdir)
            svn.mkdir(versionurl, noerror=1,
                      log="Created directory for version %s." % version)
            currentdir = tmpdir
         
        specsdir = os.path.join(currentdir, "SPECS")
        sourcesdir = os.path.join(currentdir, "SOURCES")

        unpackdir = tempfile.mktemp()
        os.mkdir(unpackdir)
        try:
            srpm.unpack(unpackdir)

            uspecsdir = os.path.join(unpackdir, "SPECS")
            usourcesdir = os.path.join(unpackdir, "SOURCES")
            
            uspecsentries = os.listdir(uspecsdir)
            usourcesentries = os.listdir(usourcesdir)
            specsentries = os.listdir(specsdir)
            sourcesentries = os.listdir(sourcesdir)

            # Remove old entries
            for entry in [x for x in specsentries
                             if x not in uspecsentries]:
                if entry == ".svn":
                    continue
                entrypath = os.path.join(specsdir, entry)
                os.unlink(entrypath)
                svn.remove(entrypath)
            for entry in [x for x in sourcesentries
                             if x not in usourcesentries]:
                if entry == ".svn":
                    continue
                entrypath = os.path.join(sourcesdir, entry)
                os.unlink(entrypath)
                svn.remove(entrypath)

            # Copy all files
            execcmd("cp -rf", uspecsdir, currentdir)
            execcmd("cp -rf", usourcesdir, currentdir)
            
            # Add new entries
            for entry in [x for x in uspecsentries
                             if x not in specsentries]:
                entrypath = os.path.join(specsdir, entry)
                svn.add(entrypath)
            for entry in [x for x in usourcesentries
                             if x not in sourcesentries]:
                entrypath = os.path.join(sourcesdir, entry)
                svn.add(entrypath)
        finally:
            if os.path.isdir(unpackdir):
                shutil.rmtree(unpackdir)

        svn.commit(tmpdir, log=log)
    finally:
        if os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir)

    # Do revision and pristine tag copies
    pristineurl = layout.checkout_url(pkgdirurl, pristine=True)
    svn.remove(pristineurl, noerror=1,
               log="Removing previous pristine/ directory.")
    currenturl = layout.checkout_url(pkgdirurl)
    svn.copy(currenturl, pristineurl,
             log="Copying release %s-%s to pristine/ directory." %
                 (version, srpm.release))
    svn.copy(currenturl, releaseurl,
             log="Copying release %s-%s to releases/ directory." %
                 (version, srpm.release))

def create_package(pkgdirurl, log="", verbose=0):
    svn = SVN()
    tmpdir = tempfile.mktemp()
    try:
        basename = layout.package_name(pkgdirurl)
        if verbose:
            print "Creating package directory...",
        sys.stdout.flush()
        ret = svn.mkdir(pkgdirurl,
                        log="Created package directory for '%s'." % basename)
        if verbose:
            print "done"
            print "Checking it out...",
        svn.checkout(pkgdirurl, tmpdir)
        if verbose:
            print "done"
            print "Creating package structure...",
        svn.mkdir(os.path.join(tmpdir, "current"))
        svn.mkdir(os.path.join(tmpdir, "current", "SPECS"))
        svn.mkdir(os.path.join(tmpdir, "current", "SOURCES"))
        if verbose:
            print "done"
            print "Committing...",
        svn.commit(tmpdir,
                   log="Created package structure for '%s'." % basename)
        print "done"
    finally:
        if os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir)


def create_markrelease_log(version, release, revision):
    log = """%%repsys markrelease
version: %s
release: %s
revision: %s

%s""" % (version, release, revision, 
        ("Copying %s-%s to releases/ directory." % (version, release)))
    return log

def mark_release(pkgdirurl, version, release, revision):
    svn = SVN()
    releasesurl = layout.checkout_url(pkgdirurl, releases=True)
    versionurl = "/".join([releasesurl, version])
    releaseurl = "/".join([versionurl, release])
    currenturl = layout.checkout_url(pkgdirurl)
    cursources = layout.checkout_url(pkgdirurl, append_path="SOURCES")
    relsources = layout.checkout_url(pkgdirurl, releases=True,
            append_path="SOURCES")
    binrepo.markrelease(cursources, relsources, version, release, revision)
    if svn.ls(releaseurl, noerror=1):
        raise Error, "release already exists"
    svn.mkdir(releasesurl, noerror=1,
              log="Created releases directory.")
    svn.mkdir(versionurl, noerror=1,
              log="Created directory for version %s." % version)
    pristineurl = layout.checkout_url(pkgdirurl, pristine=True)
    svn.remove(pristineurl, noerror=1,
               log="Removing previous pristine/ directory.")
    svn.copy(currenturl, pristineurl,
             log="Copying release %s-%s to pristine/ directory." %
                 (version, release))
    markreleaselog = create_markrelease_log(version, release, revision)
    svn.copy(currenturl, releaseurl, rev=revision,
             log=markreleaselog)

def check_changed(pkgdirurl, all=0, show=0, verbose=0):
    svn = SVN()
    if all:
        baseurl = pkgdirurl
        packages = []
        if verbose:
            print "Getting list of packages...",
            sys.stdout.flush()
        packages = [x[:-1] for x in svn.ls(baseurl)]
        if verbose:
            print "done"
        if not packages:
            raise Error, "couldn't get list of packages"
    else:
        baseurl, basename = os.path.split(pkgdirurl)
        packages = [basename]
    clean = []
    changed = []
    nopristine = []
    nocurrent = []
    for package in packages:
        pkgdirurl = os.path.join(baseurl, package)
        current = layout.checkout_url(pkgdirurl)
        pristine = layout.checkout_url(pkgdirurl, pristine=True)
        if verbose:
            print "Checking package %s..." % package,
            sys.stdout.flush()
        if not svn.ls(current, noerror=1):
            if verbose:
                print "NO CURRENT"
            nocurrent.append(package)
        elif not svn.ls(pristine, noerror=1):
            if verbose:
                print "NO PRISTINE"
            nopristine.append(package)
        else:
            diff = svn.diff(pristine, current)
            if diff:
                changed.append(package)
                if verbose:
                    print "CHANGED"
                if show:
                    print diff
            else:
                if verbose:
                    print "clean"
                clean.append(package)
    if verbose:
        if not packages:
            print "No packages found!"
        elif all:
            print "Total clean packages: %s" % len(clean)
            print "Total CHANGED packages: %d" % len(changed)
            print "Total NO CURRENT packages: %s" % len(nocurrent)
            print "Total NO PRISTINE packages: %s" % len(nopristine)
    return {"clean": clean,
            "changed": changed,
            "nocurrent": nocurrent,
            "nopristine": nopristine}

def checkout(pkgdirurl, path=None, revision=None, branch=None, distro=None,
        use_binrepo=False, binrepo_check=True):
    o_pkgdirurl = pkgdirurl
    pkgdirurl = layout.package_url(o_pkgdirurl, distro=distro)
    current = layout.checkout_url(pkgdirurl, branch=branch)
    if path is None:
        path = layout.package_name(pkgdirurl)
    mirror.info(current)
    svn = SVN()
    svn.checkout(current, path, rev=revision, show=1)
    if use_binrepo:
        download_binaries(path, check=binrepo_check)
    
def getpkgtopdir(basedir=None):
    #FIXME this implementation doesn't work well with relative path names,
    # which is something we need in order to have a friendlier output
    if basedir is None:
        basedir = os.path.curdir
    while not ispkgtopdir(basedir):
        if os.path.abspath(basedir) == "/":
            raise Error, "can't find top package directories SOURCES and SPECS"
        basedir = os.path.join(basedir, os.path.pardir)
    if basedir.startswith("./"):
        basedir = basedir[2:]
    return basedir

def ispkgtopdir(path=None):
    if path is None:
        path = os.getcwd()
    names = os.listdir(path)
    return (".svn" in names and "SPECS" in names and "SOURCES" in names)

def sync(dryrun=False, ci=False, download=False):
    svn = SVN()
    topdir = getpkgtopdir()
    # run svn info because svn st does not complain when topdir is not an
    # working copy
    svn.info(topdir)
    specsdir = os.path.join(topdir, "SPECS/")
    sourcesdir = os.path.join(topdir, "SOURCES/")
    for path in (specsdir, sourcesdir):
        if not os.path.isdir(path):
            raise Error, "%s directory not found" % path
    specs = glob.glob(os.path.join(specsdir, "*.spec"))
    if not specs:
        raise Error, "no .spec files found in %s" % specsdir
    specpath = specs[0] # FIXME better way?
    try:
        rpm.addMacro("_topdir", os.path.abspath(topdir))
        spec = rpm.TransactionSet().parseSpec(specpath)
    except rpm.error, e:
        raise Error, "could not load spec file: %s" % e
    sources = dict((os.path.basename(name), name)
            for name, no, flags in spec.sources())
    sourcesst = dict((os.path.basename(path), (path, st))
            for st, path in svn.status(sourcesdir, noignore=True))
    toadd_br = []
    toadd_svn = []
    toremove_svn = []
    toremove_br = []
    for source, url in sources.iteritems():
        sourcepath = os.path.join(sourcesdir, source)
        if sourcesst.get(source):
            if os.path.isfile(sourcepath):
                if not binrepo.is_tracked(sourcepath):
                    if binrepo.is_binary(sourcepath):
                        toadd_br.append(sourcepath)
                    else:
                        toadd_svn.append(sourcepath)
            else:
                sys.stderr.write("warning: %s not found\n" % sourcepath)
        elif download and not os.path.isfile(sourcepath):
            print "%s not found, downloading from %s" % (sourcepath, url)
            fmt = config.get("global", "download-command",
                    "wget -c -O '$dest' $url")
            context = {"dest": sourcepath, "url": url}
            try:
                cmd = string.Template(fmt).substitute(context)
            except KeyError, e:
                raise Error, "invalid variable %r in download-command "\
                        "configuration option" % e
            execcmd(cmd, show=True)
            if os.path.isfile(sourcepath):
                if binrepo.is_binary(sourcepath):
                    toadd_br.append(sourcepath)
                else:
                    toadd_svn.append(sourcepath)
            else:
                raise Error, "file not found: %s" % sourcepath
    # rm entries not found in sources and still in svn
    found = os.listdir(sourcesdir)
    for entry in found:
        if entry == ".svn" or entry == "sources":
            continue
        status = sourcesst.get(entry)
        path = os.path.join(sourcesdir, entry)
        if entry not in sources:
            if status is None: # file is tracked by svn
                toremove_svn.append(path)
            elif binrepo.is_tracked(path):
                toremove_br.append(path)
    for path in toremove_svn:
        print "D\t%s" % path
        if not dryrun:
            svn.remove(path, local=True)
    for path in toremove_br:
        print "DB\t%s" % path
        if not dryrun:
            binrepo.delete_pending(path)
    for path in toadd_svn:
        print "A\t%s" % path
        if not dryrun:
            svn.add(path, local=True)
    for path in toadd_br:
        print "AB\t%s" % path
        if not dryrun:
            binrepo.upload_pending(path)
    if commit:
        commit(topdir)

def commit(target=".", message=None, logfile=None):
    topdir = getpkgtopdir(target)
    sourcesdir = os.path.join(topdir, "SOURCES")
    binrepo.commit(sourcesdir) #TODO make it optional
    svn = SVN()
    status = svn.status(target, quiet=True)
    if not status:
        print "nothing to commit"
        return
    info = svn.info2(target)
    url = info.get("URL")
    if url is None:
        raise Error, "working copy URL not provided by svn info"
    mirrored = mirror.using_on(url)
    if mirrored:
        newurl = mirror.switchto_parent(svn, url, target)
        print "relocated to", newurl
    # we can't use the svn object here because svn --non-interactive option
    # hides VISUAL
    opts = []
    if message is not None:
        opts.append("-m \"%s\"" % message)
    if logfile is not None:
        opts.append("-F \"%s\"" % logfile)
    mopts = " ".join(opts)
    os.system("svn ci %s %s" % (mopts, target))
    if mirrored:
        print "use \"repsys switch\" in order to switch back to mirror "\
                "later"

def spec_sources(topdir):
    specs = glob.glob(os.path.join(topdir, "SPECS/*.spec"))
    spec_path = specs[0] # FIXME use svn info to ensure which one
    ts = rpm.ts()
    spec = ts.parseSpec(spec_path)
    sources = [name for name, x, y in spec.sources()]
    return sources
    
def download_binaries(target, pkgdirurl=None, check=True):
    refurl = pkgdirurl
    if refurl is None:
        refurl = binrepo.svn_root(target)
    if binrepo.enabled(refurl):
        download = []
        sourcesdir = "SOURCES"
        sources = spec_sources(target)
        for source in sources:
            path = os.path.join(target, sourcesdir, source)
            if not os.path.exists(path):
                # try to download those files that are referred in the spec
                # but were not found in the svn working copy
                download.append(source)
        url = None
        bintarget = os.path.join(target, sourcesdir)
        if pkgdirurl:
            url = os.path.join(pkgdirurl, sourcesdir)
        for status in binrepo.download(bintarget, url, download, check):
            print status

def update(target=None):
    svn = SVN()
    info = None
    svn_target = None
    br_target = None
    if target:
        svn_target = target
    else:
        top = getpkgtopdir()
        svn_target = top
        br_target = top
    if svn_target:
        svn.update(svn_target, show=True)
    if br_target:
        info = svn.info2(svn_target) 
        if not br_target and not svn_target:
            raise Error, "target not in SVN nor in binaries "\
                    "repository: %s" % target
        url = info["URL"]
        download_binaries(br_target, url)

def _sources_log(added, deleted):
    lines = ["SILENT: changed sources list:\n"]
    for name in added:
        lines.append("A\t" + name)
    for name in deleted:
        lines.append("D\t" + name)
    log = "\n".join(lines)
    return log

def upload(paths, auto=False, commit=False, addsources=False):
    if auto and not paths:
        topdir = getpkgtopdir()
        paths = [os.path.join(topdir, "SOURCES")]
    added, deleted = binrepo.upload(paths, auto)
    if addsources or commit:
        svn = SVN()
        spath = binrepo.sources_path(paths[0])
        if addsources:
            svn.add(spath)
        if commit:
            log = _sources_log(added, deleted)
            svn.commit(spath, log=log)

def binrepo_delete(paths, commit=False):
    #TODO handle files tracked by svn
    refurl = binrepo.svn_root(paths[0])
    if not binrepo.enabled(refurl):
        raise Error, "binary repository is not enabled for %s" % refurl
    added, deleted = binrepo.remove(paths)
    if commit:
        svn = SVN()
        spath = binrepo.sources_path(paths[0])
        log = _sources_log(added, deleted)
        svn.commit(spath, log=log)

def switch(mirrorurl=None):
    svn  = SVN()
    topdir = getpkgtopdir()
    info = svn.info2(topdir)
    wcurl = info.get("URL")
    if wcurl is None:
        raise Error, "working copy URL not provided by svn info"
    newurl = mirror.autoswitch(svn, topdir, wcurl, mirrorurl)
    print "switched to", newurl

def get_submit_info(path):
    path = os.path.abspath(path)

    # First, look for SPECS and SOURCES directories.
    found = False
    while path != "/":
        if os.path.isdir(path):
            specsdir = os.path.join(path, "SPECS")
            sourcesdir = os.path.join(path, "SOURCES")
            if os.path.isdir(specsdir) and os.path.isdir(sourcesdir):
                found = True
                break
        path = os.path.dirname(path)
    if not found:
        raise Error, "SPECS and/or SOURCES directories not found"

    # Then, check if this is really a subversion directory.
    if not os.path.isdir(os.path.join(path, ".svn")):
        raise Error, "subversion directory not found"
    
    svn = SVN()

    # Now, extract the package name.
    info = svn.info2(path)
    url = info.get("URL")
    if url is None:
        raise Error, "missing URL from svn info %s" % path
    toks = url.split("/")
    if len(toks) < 2 or toks[-1] != "current":
        raise Error, "unexpected URL received from 'svn info'"
    name = toks[-2]
    url = "/".join(toks[:-1])

    # Finally, guess revision.
    max = -1
    files = []
    files.extend(glob.glob("%s/*" % specsdir))
    files.extend(glob.glob("%s/*" % sourcesdir))
    for file in files:
        info = svn.info2(file)
        if info is None:
            continue
        rawrev = info.get("Last Changed Rev")
        if rawrev:
            rev = int(rawrev)
            if rev > max:
                max = rev
    if max == -1:
        raise Error, "revision tag not found in 'svn info' output"
    
    return name, url, max

# vim:et:ts=4:sw=4
