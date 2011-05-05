#!/usr/bin/python
from RepSys.util import execcmd

class SRPM:
    def __init__(self, filename):
        self.filename = filename
        self._getinfo()

    def _getinfo(self):
        args = ["rpm", "-qp", "--qf", "%{name} %{epoch} %{release} %{version}",
                self.filename]
        status, output = execcmd(args)
        self.name, self.epoch, self.release, self.version = output.split()
        if self.epoch == "(none)":
            self.epoch = None

    def unpack(self, topdir):
        args = ["rpm", "-i", "--define", "_topdir %s" % (topdir),
                self.filename]
        execcmd(args)

# vim:et:ts=4:sw=4
