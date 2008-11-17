#!/usr/bin/python
from RepSys import Error, config
from RepSys import mirror, layout, log
from RepSys.svn import SVN
from RepSys.simplerpm import SRPM
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
             strict = False):
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
        srpmsdir = os.path.join(tmpdir, "SRPMS")
        os.mkdir(srpmsdir)
        specsdir = os.path.join(tmpdir, "SPECS")
        speclist = glob.glob(os.path.join(specsdir, "*.spec"))
        if not speclist:
            raise Error, "no spec files found"
        spec = speclist[0]
        if svnlog:
            submit = not not revision
            log.specfile_svn2rpm(pkgdirurl, spec, revision, submit=submit,
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
        sourcecmd = config.get("helper", "rpmbuild", "rpmbuild")
        execcmd("%s -bs --nodeps %s %s %s %s %s %s %s %s %s %s" %
            (sourcecmd, topdir, builddir, rpmdir, sourcedir, specdir,
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

def put_srpm(srpmfile, markrelease=False, striplog=True, branch=None,
        baseurl=None, baseold=None, logmsg=None, rename=True):
    svn = SVN()
    srpm = SRPM(srpmfile)
    tmpdir = tempfile.mktemp()
    if baseurl:
        pkgurl = mirror._joinurl(baseurl, srpm.name)
    else:
        pkgurl = layout.package_url(srpm.name, distro=branch,
                mirrored=False)
    print "Importing package to %s" % pkgurl
    try:
        if srpm.epoch:
            version = "%s:%s" % (srpm.epoch, srpm.version)
        else:
            version = srpm.version
        versionurl = "/".join([pkgurl, "releases", version])
        releaseurl = "/".join([versionurl, srpm.release])
        currenturl = "/".join([pkgurl, "current"])
        currentdir = os.path.join(tmpdir, "current")
        #FIXME when pre-commit hook fails, there's no clear way to know
        # what happened
        ret = svn.mkdir(pkgurl, noerror=1, log="Created package directory")
        if ret or not svn.ls(currenturl, noerror=1):
            svn.checkout(pkgurl, tmpdir)
            svn.mkdir(os.path.join(tmpdir, "releases"))
            svn.mkdir(currentdir)
            svn.mkdir(os.path.join(currentdir, "SPECS"))
            svn.mkdir(os.path.join(currentdir, "SOURCES"))
            #svn.commit(tmpdir,log="Created package structure.")
            version_exists = 1
        else:
            if svn.ls(releaseurl, noerror=1):
                raise Error, "release already exists"
            svn.checkout("/".join([pkgurl, "current"]), tmpdir)
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

        specs = glob.glob(os.path.join(specsdir, "*.spec"))
        if not specs:
            raise Error, "no spec file found on %s" % specsdir
        if len(specs) > 1:
            raise Error, "more than one spec file found on %s" % specsdir
        specpath = specs[0]
        if rename:
            specfile = os.path.basename(specpath)
            specname = specfile[:-len(".spec")]
            if specname != srpm.name:
                newname = srpm.name + ".spec"
                newpath = os.path.join(specsdir, newname)
                sys.stderr.write("warning: renaming spec file to '%s' "
                        "(use -n to disable it)\n" % (newname))
                os.rename(specpath, newpath)
                try:
                    svn.remove(specpath)
                except Error:
                    # file not tracked
                    svn.revert(specpath)
                svn.add(newpath)
                specpath = newpath

        if striplog:
            specpath = specpath
            fspec = open(specpath)
            spec, chlog = log.split_spec_changelog(fspec)
            chlog.seek(0)
            spec.seek(0)
            fspec.close()
            fspec = open(specpath, "w")
            fspec.writelines(spec)
            fspec.close()
            oldurl = baseold or config.get("log", "oldurl")
            pkgoldurl = mirror._joinurl(oldurl, srpm.name)
            svn.mkdir(pkgoldurl, noerror=1,
                    log="created old log directory for %s" % srpm.name)
            logtmp = tempfile.mktemp()
            try:
                svn.checkout(pkgoldurl, logtmp)
                miscpath = os.path.join(logtmp, "log")
                fmisc = open(miscpath, "w+")
                fmisc.writelines(chlog)
                fmisc.close()
                svn.add(miscpath)
                svn.commit(logtmp,
                        log="imported old log for %s" % srpm.name)
            finally:
                if os.path.isdir(logtmp):
                    shutil.rmtree(logtmp)
        svn.commit(tmpdir,
                log=logmsg or ("imported package %s" % srpm.name))
    finally:
        if os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir)

    # Do revision and pristine tag copies
    pristineurl = layout.checkout_url(pkgurl, pristine=True)
    svn.remove(pristineurl, noerror=1,
               log="Removing previous pristine/ directory.")
    currenturl = layout.checkout_url(pkgurl)
    svn.copy(currenturl, pristineurl,
             log="Copying release %s-%s to pristine/ directory." %
                 (version, srpm.release))
    if markrelease:
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
    releasesurl = "/".join([pkgdirurl, "releases"])
    versionurl = "/".join([releasesurl, version])
    releaseurl = "/".join([versionurl, release])
    if svn.ls(releaseurl, noerror=1):
        raise Error, "release already exists"
    svn.mkdir(releasesurl, noerror=1,
              log="Created releases directory.")
    svn.mkdir(versionurl, noerror=1,
              log="Created directory for version %s." % version)
    pristineurl = layout.checkout_url(pkgdirurl, pristine=True)
    svn.remove(pristineurl, noerror=1,
               log="Removing previous pristine/ directory.")
    currenturl = layout.checkout_url(pkgdirurl)
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

def checkout(pkgdirurl, path=None, revision=None, branch=None,
        distro=None):
    o_pkgdirurl = pkgdirurl
    pkgdirurl = layout.package_url(o_pkgdirurl, distro=distro)
    current = layout.checkout_url(pkgdirurl, branch=branch)
    if path is None:
        path = layout.package_name(pkgdirurl)
    mirror.info(current)
    svn = SVN()
    svn.checkout(current, path, rev=revision, show=1)

def _getpkgtopdir(basedir=None):
    if basedir is None:
        basedir = os.getcwd()
    cwd = os.getcwd()
    dirname = os.path.basename(cwd)
    if dirname == "SPECS" or dirname == "SOURCES":
        topdir = os.pardir
    else:
        topdir = ""
    return topdir

def sync(dryrun=False, download=False):
    svn = SVN()
    topdir = _getpkgtopdir()
    # run svn info because svn st does not complain when topdir is not an
    # working copy
    svn.info(topdir or ".")
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
    toadd = []
    for source, url in sources.iteritems():
        sourcepath = os.path.join(sourcesdir, source)
        pst = sourcesst.get(source)
        if pst:
            if os.path.isfile(sourcepath):
                toadd.append(sourcepath)
            else:
                sys.stderr.write("warning: %s not found, skipping\n" % sourcepath)
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
                toadd.append(sourcepath)
            else:
                raise Error, "file not found: %s" % sourcepath
    # rm entries not found in sources and still in svn
    found = os.listdir(sourcesdir)
    toremove = []
    for entry in found:
        if entry == ".svn":
            continue
        status = sourcesst.get(entry)
        if status is None and entry not in sources:
            path = os.path.join(sourcesdir, entry)
            toremove.append(path)
    for path in toremove:
        print "D\t%s" % path
        if not dryrun:
            svn.remove(path, local=True)
    for path in toadd:
        print "A\t%s" % path
        if not dryrun:
            svn.add(path, local=True)

def commit(target=".", message=None, logfile=None):
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

def switch(mirrorurl=None):
    svn  = SVN()
    topdir = _getpkgtopdir()
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
        try:
            info = svn.info2(file)
        except Error:
            # possibly not tracked
            continue
        if info is None:
            continue
        rawrev = info.get("Last Changed Rev")
        if rawrev:
            rev = int(rawrev)
            if rev > max:
                max = rev
    if max == -1:
        raise Error, "revision tag not found in 'svn info' output"

    if mirror.using_on(url):
        url = mirror.switchto_parent_url(url)
    
    return name, url, max

# vim:et:ts=4:sw=4
