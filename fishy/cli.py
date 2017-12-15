"""
Implementation of fishy's command line interface.
"""
import sys
import traceback
import argparse
import logging
import typing as typ
from .fat.fat_filesystem.fattools import FATtools
from .fat.fat_filesystem.fat_wrapper import create_fat
from .file_slack import FileSlack
from .cluster_allocation import ClusterAllocation
from .metadata import Metadata


LOGGER = logging.getLogger("cli")


def do_metadata(args: argparse.Namespace) -> None:
    """
    handles metadata subcommand execution
    :param args: argparse.Namespace
    """
    if args.password is None:
        meta = Metadata()
    else:
        meta = Metadata(password=args.password)
    meta.read(args.metadata)
    meta.info()


def do_fattools(args: argparse.Namespace, device: typ.BinaryIO) -> None:
    """
    handles fattools subcommand execution
    :param args: argparse.Namespace
    :param device: stream of the filesystem
    """
    fattool = FATtools(create_fat(device))
    if args.fat:
        fattool.list_fat()
    elif args.info:
        fattool.list_info()
    elif args.list is not None:
        fattool.list_directory(args.list)


def do_fileslack(args: argparse.Namespace, device: typ.BinaryIO) -> None:
    """
    hanles fileslack subcommand execution
    :param args: argparse.Namespace
    :param device: stream of the filesystem
    """
    if args.info:
        slacker = FileSlack(device, Metadata(), args.dev)
        slacker.info(args.destination)
    if args.write:
        if args.password is None:
            slacker = FileSlack(device, Metadata(), args.dev)
        else:
            slacker = FileSlack(device, Metadata(password=args.password), args.dev)
        if not args.file:
            # write from stdin into fileslack
            slacker.write(sys.stdin.buffer, args.destination)
        else:
            # write from files into fileslack
            with open(args.file, 'rb') as fstream:
                slacker.write(fstream, args.destination, args.file)
        with open(args.metadata, 'wb+') as metadata_out:
            slacker.metadata.write(metadata_out)
    elif args.read:
        # read file slack of a single hidden file to stdout
        with open(args.metadata, 'rb') as metadata_file:
            if args.password is None:
                meta = Metadata()
            else:
                meta = Metadata(password=args.password)
            meta.read(metadata_file)
            slacker = FileSlack(device, meta, args.dev)
            slacker.read(sys.stdout.buffer)
    elif args.outfile:
        # read hidden data in fileslack into outfile
        with open(args.metadata, 'rb') as metadata_file:
            if args.password is None:
                meta = Metadata()
            else:
                meta = Metadata(password=args.password)
            meta.read(metadata_file)
            slacker = FileSlack(device, meta, args.dev)
            slacker.read_into_file(args.outfile)
    elif args.clear:
        # clear fileslack
        with open(args.metadata, 'rb') as metadata_file:
            if args.password is None:
                meta = Metadata()
            else:
                meta = Metadata(password=args.password)
            meta.read(metadata_file)
            slacker = FileSlack(device, meta, args.dev)
            slacker.clear()


def do_addcluster(args: argparse.Namespace, device: typ.BinaryIO) -> None:
    """
    hanles addcluster subcommand execution
    :param args: argparse.Namespace
    :param device: stream of the filesystem
    """
    if args.write:
        if args.password is None:
            allocator = ClusterAllocation(device, Metadata(), args.dev)
        else:
            allocator = ClusterAllocation(device, Metadata(password=args.password), args.dev)
        if not args.file:
            # write from stdin into additional clusters
            allocator.write(sys.stdin.buffer, args.destination)
        else:
            # write from files into additional clusters
            with open(args.file, 'rb') as fstream:
                allocator.write(fstream, args.destination, args.file)
        with open(args.metadata, 'wb+') as metadata_out:
            allocator.metadata.write(metadata_out)
    elif args.read:
        # read file slack of a single hidden file to stdout
        with open(args.metadata, 'rb') as metadata_file:
            if args.password is None:
                meta = Metadata()
            else:
                meta = Metadata(password=args.password)
            meta.read(metadata_file)
            allocator = ClusterAllocation(device, meta, args.dev)
            allocator.read(sys.stdout.buffer)
    elif args.outfile:
        # read hidden data from additional clusters into outfile
        with open(args.metadata, 'rb') as metadata_file:
            if args.password is None:
                meta = Metadata()
            else:
                meta = Metadata(password=args.password)
            meta.read(metadata_file)
            allocator = ClusterAllocation(device, meta, args.dev)
            allocator.read_into_file(args.outfile)
    elif args.clear:
        # clear additional clusters
        with open(args.metadata, 'rb') as metadata_file:
            if args.password is None:
                meta = Metadata()
            else:
                meta = Metadata(password=args.password)
            meta.read(metadata_file)
            allocator = ClusterAllocation(device, meta, args.dev)
            allocator.clear()


def build_parser() -> argparse.ArgumentParser:
    """
    Get the cli parser

    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(description='Toolkit for filesystem based data hiding techniques.')
    # TODO: Maybe this option should be required for hiding technique
    #       subcommand but not for metadata.... needs more thoughs than I
    #       currently have
    parser.add_argument('-d', '--device', dest='dev', required=False, help='Path to filesystem')
    parser.add_argument('-p', '--password', dest='password', required=False, help='Password for encryption of metadata')
    # TODO Maybe we should provide a more fine grained option to choose between different log levels
    parser.add_argument('--verbose', '-v', action='count', help="Increase verbosity. Use it multiple times to increase verbosity further.")
    subparsers = parser.add_subparsers(help='Hiding techniques sub-commands')

    # FAT Tools
    fatt = subparsers.add_parser('fattools', help='List statistics about FAT filesystem')
    fatt.set_defaults(which='fattools')
    fatt.add_argument('-l', '--ls', dest='list', type=int, metavar='CLUSTER_ID', help='List files under cluster id. Use 0 for root directory')
    fatt.add_argument('-f', '--fat', dest='fat', action='store_true', help='List content of FAT')
    fatt.add_argument('-i', '--info', dest='info', action='store_true', help='Show some information about the filesystem')

    # Metadata info
    metadata = subparsers.add_parser('metadata', help='list information about a metadata file')
    metadata.set_defaults(which='metadata')
    metadata.add_argument('-m', '--metadata', dest='metadata', type=argparse.FileType('rb'), help="filepath to metadata file")

    # FileSlack
    fileslack = subparsers.add_parser('fileslack', help='Operate on file slack')
    fileslack.set_defaults(which='fileslack')
    fileslack.add_argument('-d', '--dest', dest='destination', action='append', required=False, help='absolute path to file or directory on filesystem, directories will be parsed recursively')
    fileslack.add_argument('-m', '--metadata', dest='metadata', required=True, help='Metadata file to use')
    fileslack.add_argument('-r', '--read', dest='read', action='store_true', help='read hidden data from slackspace to stdout')
    fileslack.add_argument('-o', '--outfile', dest='outfile', metavar='OUTFILE', help='read hidden data from slackspace to OUTFILE')
    fileslack.add_argument('-w', '--write', dest='write', action='store_true', help='write to slackspace')
    fileslack.add_argument('-c', '--clear', dest='clear', action='store_true', help='clear slackspace')
    fileslack.add_argument('-i', '--info', dest='info', action='store_true', help='print file slack information of given files')
    fileslack.add_argument('file', metavar='FILE', nargs='?', help="File to write into slack space, if nothing provided, use stdin")

    # Additional Cluster Allocation
    addcluster = subparsers.add_parser('addcluster', help='Allocate more clusters for a file')
    addcluster.set_defaults(which='addcluster')
    addcluster.add_argument('-d', '--dest', dest='destination', required=False, help='absolute path to file or directory on filesystem, directories will be parsed recursively')
    addcluster.add_argument('-m', '--metadata', dest='metadata', required=True, help='Metadata file to use')
    addcluster.add_argument('-r', '--read', dest='read', action='store_true', help='read hidden data from allocated clusters to stdout')
    addcluster.add_argument('-o', '--outfile', dest='outfile', metavar='OUTFILE', help='read hidden data from allocated clusters to OUTFILE')
    addcluster.add_argument('-w', '--write', dest='write', action='store_true', help='write to additional allocated clusters')
    addcluster.add_argument('-c', '--clear', dest='clear', action='store_true', help='clear allocated clusters')
    addcluster.add_argument('file', metavar='FILE', nargs='?', help="File to write into additionally allocated clusters, if nothing provided, use stdin")

    return parser


def main():
    # set exception handler
    sys.excepthook = general_excepthook
    # Parse cli arguments
    parser = build_parser()
    args = parser.parse_args()

    # Set logging level (verbosity)
    if args.verbose is None: args.verbose = 0
    if args.verbose == 1:
        logging.basicConfig(level=logging.INFO)
    elif args.verbose >= 2:
        logging.basicConfig(level=logging.DEBUG)
    if args.verbose > 2:
        fish = """
                   .|_-
             ___.-´  /_.
        .--´`    `´`-,/     .
       ..--.-´-.      ´-.  /|
      (o( o( o )         ./.
      `       ´             -
   (               `.       /
    -....--   .\    \--..-  \\
        `--´    -.-´      \.-
                           \|
        """
        LOGGER.debug(fish)
        LOGGER.debug("Thank you for debugging so hard! We know it is "
                     "a mess. So, here is a friend, who will support you :)")


    # if 'metadata' was chosen
    if args.which == 'metadata':
        do_metadata(args)
    else:
        with open(args.dev, 'rb+') as device:
            # if 'fattools' was chosen
            if args.which == "fattools":
                do_fattools(args, device)

            # if 'fileslack' was chosen
            if args.which == 'fileslack':
                do_fileslack(args, device)

            # if 'addcluster' was chosen
            if args.which == 'addcluster':
                do_addcluster(args, device)


def general_excepthook(errtype, value, tb):
    """
    This function serves as a general exception handler, who catches all
    exceptions, that were not handled at a higher lever
    """
    LOGGER.critical("Error: %s: %s.", errtype, value)
    LOGGER.info("".join(traceback.format_exception(type, value, tb)))
    sys.exit(1)

if __name__ == "__main__":
    main()

