from RepSys import Error
from RepSys.command import *
from RepSys.rpmutil import upload

HELP = """\
Usage: repsys upload [OPTIONS] [PATH]

Upload a given file to the binary sources repository.

It will also update the contents of the 'binrepo.lst' file and leave it
uncommited.

If the path is a directory, all the contents of the directory will be
uploaded or removed.

Options:
    -h      help

"""

def parse_options():
    parser = OptionParser(help=HELP)
    opts, args = parser.parse_args()
    opts.paths = args
    return opts

def main():
    do_command(parse_options, upload)
