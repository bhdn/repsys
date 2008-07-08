""" Handles repository layout scheme and package URLs."""

import os
import urlparse

from RepSys import Error, config

__all__ = ["package_url", "checkout_url", "repository_url", "get_url_revision"]

def get_url_revision(url, retrieve=True):
    """Get the revision from a given URL

    If the URL contains an explicit revision number (URL@REV), just use it
    without even checking if the revision really exists.

    The parameter retrieve defines whether it must ask the SVN server for
    the revision number or not when it is not found in the URL.
    """
    url, rev = split_url_revision(url)
    if rev is None and retrieve:
        # if no revspec was found, ask the server
        svn = SVN()
        rev = svn.revision(url)
    return rev

def unsplit_url_revision(url, rev):
    if rev is None:
        newurl = url
    else:
        parsed = list(urlparse.urlparse(url))
        path = os.path.normpath(parsed[2])
        parsed[2] = path + "@" + str(rev)
        newurl = urlparse.urlunparse(parsed)
    return newurl

def split_url_revision(url):
    """Returns a tuple (url, rev) from an subversion URL with @REV
    
    If the revision is not present in the URL, rev is None.
    """
    parsed = list(urlparse.urlparse(url))
    path = os.path.normpath(parsed[2])
    dirs = path.rsplit("/", 1)
    lastname = dirs[-1]
    newname = lastname
    index = lastname.rfind("@")
    rev = None
    if index != -1:
        newname = lastname[:index]
        rawrev = lastname[index+1:]
        if rawrev:
            try:
                rev = int(rawrev)
                if rev < 0:
                    raise ValueError
            except ValueError:
                raise Error, "invalid revision specification on URL: %s" % url
    dirs[-1] = newname
    newpath = "/".join(dirs)
    parsed[2] = newpath
    newurl = urlparse.urlunparse(parsed)
    return newurl, rev

def checkout_url(url, branch=None, version=None, release=None,
        releases=False, pristine=False, append_path=None):
    """Get the URL of a branch of the package, defaults to current/
    
    It tries to preserve revisions in the format @REV.
    """
    parsed = list(urlparse.urlparse(url))
    path, rev = split_url_revision(parsed[2])
    if releases:
        path = os.path.normpath(path + "/releases")
    elif version:
        assert release is not None
        path = os.path.normpath(path + "/releases/" + version + "/" + release)
    elif pristine:
        path = os.path.join(path, "pristine")
    elif branch:
        path = os.path.join(path, "branches", branch)
    else:
        path = os.path.join(path, "current")
    if append_path:
        path = os.path.join(path, append_path)
    path = unsplit_url_revision(path, rev)
    parsed[2] = path
    newurl = urlparse.urlunparse(parsed)
    return newurl

def convert_default_parent(url):
    """Removes the cooker/ component from the URL"""
    parsed = list(urlparse.urlparse(url))
    path = os.path.normpath(parsed[2])
    rest, last = os.path.split(path)
    parsed[2] = rest
    newurl = urlparse.urlunparse(parsed)
    return newurl

def remove_current(url):
    parsed = list(urlparse.urlparse(url))
    path = os.path.normpath(parsed[2])
    rest, last = os.path.split(path)
    if last == "current":
        # FIXME this way we will not allow packages to be named "current"
        path = rest
    parsed[2] = path
    newurl = urlparse.urlunparse(parsed)
    return newurl

def repository_url(mirrored=False):
    url = None
    if mirrored and config.get("global", "use-mirror"):
        url = config.get("global", "mirror")
    if url is None:
        url = config.get("global", "repository")
        if not url:
            # compatibility with the default_parent configuration option
            default_parent = config.get("global", "default_parent")
            if default_parent is None:
                raise Error, "you need to set the 'repository' " \
                        "configuration option on repsys.conf"
            url = convert_default_parent(default_parent)
    return url

def package_url(name_or_url, version=None, release=None, distro=None,
        mirrored=True):
    """Returns a tuple with the absolute package URL and its name

    @name_or_url: name, relative path, or URL of the package. In case it is
                  a URL, the URL will just be 'normalized'.
    @version: the version to be fetched from releases/ (requires release)
    @release: the release number to be fetched from releases/$version/
    @distro: the name of the repository branch inside updates/
    @mirrored: return an URL based on the mirror repository, if enabled
    """
    from RepSys.mirror import normalize_path
    if "://" in name_or_url:
        url = normalize_path(name_or_url)
        url = remove_current(url)
    else:
        name = name_or_url
        devel_branch = config.get("global", "trunk-dir", "/cooker/")
        branches_dir = config.get("global", "branches-dir", "/updates/")
        if distro or "/" in name:
            default_branch = branches_dir
        else:
            default_branch = devel_branch # cooker
        path = os.path.join(distro or default_branch, name)
        parsed = list(urlparse.urlparse(repository_url(mirrored=mirrored)))
        parsed[2] = os.path.normpath(parsed[2] + "/" + path)
        url = urlparse.urlunparse(parsed)
    return url

def package_name(url):
    """Returns the package name from a package URL
    
    It takes care of revision numbers"""
    parsed = urlparse.urlparse(url)
    path, rev = split_url_revision(parsed[2])
    rest, name = os.path.split(path)
    return name

def package_spec_url(url, *args, **kwargs):
    """Returns the URL of the specfile of a given package URL

    The parameters are the same used by checkout_url, except append_path.
    """
    kwargs["append_path"] = "SPECS/" + package_name(url) + ".spec"
    specurl = checkout_url(url, *args, **kwargs)
    return specurl

