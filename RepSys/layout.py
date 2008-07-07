""" Handles repository layout scheme and package URLs."""

import os
import urlparse

from RepSys import Error, config

__all__ = ["package_url", "package_branch_url", "repository_url"]


def package_branch_url(url, branch=None, version=None, release=None,
        pristine=False):
    """Get the URL of a branch of the package, defaults to current/"""
    parsed = list(urlparse.urlparse(url))
    path = os.path.normpath(parsed[2])
    if version:
        path = os.path.normpath(path + "/" + version + "/" + release)
    elif pristine:
        path = os.path.join(path, "pristine")
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
        package_branch=None, mirrored=True):
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

