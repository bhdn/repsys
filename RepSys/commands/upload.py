from RepSys import Error
from RepSys.command import *
from RepSys.rpmutil import upload

HELP = """\
Usage: repsys upload [OPTIONS] [PATH]

Upload a given file to the binary sources repository.

It will also update the contents of the 'binrepo.lst' file and left it
uncommited.

If the path is a directory, all the contents of the directory will be
uploaded or removed.

Options:
    -a      find all possible binary sources inside PATH
    -c      automatically commit the 'binrepo.lst' file
    -A      do not 'svn add' the 'binrepo.lst' file
    -h      help

"""

def parse_options():
    parser = OptionParser(help=HELP)
    parser.add_option("-c", dest="commit", default=False,
            action="store_true")
    parser.add_option("-A", dest="addsources", default=True,
            action="store_false")
    parser.add_option("-a", dest="auto", default=False, action="store_true")
    opts, args = parser.parse_args()
    if len(args):
        opts.paths = args
    else:
        raise Error, "you need to provide a path"
    return opts

def main():
    do_command(parse_options, upload)
