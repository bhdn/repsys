from RepSys import Error
from RepSys.command import *
from RepSys.rpmutil import upload

HELP = """\
Usage: repsys upload [OPTIONS] [PATH]

Upload a given file to the binary sources repository.

It will also update the contents of the 'sources' file and left it
uncommited.

If the path is a directory, all the contents of the directory will be
uploaded or removed.

Options:
    -c      automatically commit the 'sources' file
    -A      do not 'svn add' the 'sources' file
    -h      help

"""

def parse_options():
    parser = OptionParser(help=HELP)
    parser.add_option("-c", dest="commit", type="string")
    parser.add_option("-A", dest="addsources", default=True,
            action="store_false")
    opts, args = parser.parse_args()
    if len(args):
        opts.path = args[0]
    else:
        raise Error, "you need to provide a path"
    return opts

def main():
    do_command(parse_options, upload)
