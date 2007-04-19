import os

from RepSys import config

def relocate_path(oldpar, newpar, oldpath):
    subpath = oldurl[len(oldpar)-1:-1]
    newurl = os.path.join(newpar, subpath)
    return newurl

def enabled(url=None):
    mirror = config.get("global", "mirror")
    default_parent = config.get("global", "default_parent")
    urlok = True
    if url:
        urlok = url.startswith(mirror)
    return (mirror is not None and 
            default_parent is not None and urlok)

def mirror_relocate(oldpar, newpar, oldpath, wcpath):
    newurl = relocate_path(oldpar, newpar, oldpath)
    svn.switch(oldurl, newurl, path=wcpath, relocate="True")

def switchto_parent(svn, url, path):
    """Relocates the working copy to default_parent"""
    mirror = config.get("global", "mirror")
    default_parent = config.get("global", "default_parent")
    newurl = mirror_relocate(mirror, default_parent, url, path)
    return newurl

def switchto_mirror(svn, url, path):
    mirror = config.get("global", "mirror")
    default_parent = config.get("global", "default_parent")
    newurl = mirror_relocate(default_parent, mirror, url, path)
    return newurl

def checkout_url(url):
    mirror = config.get("global", "mirror")
    default_parent = config.get("global", "default_parent")
    if mirror is not None and default_parent is not None:
        return relocate_path(default_parent, mirror, url)
    return url
