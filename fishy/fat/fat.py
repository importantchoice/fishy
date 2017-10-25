"""
FAT12, FAT16 and FAT32 reader

By now FAT16 and FAT32 are not really implemented

examples:
>>> with open('testfs.dd', 'rb') as filesystem:
>>>     fs = FAT12(filesystem)

example to print all entries in root directory:
>>>     for i, v in fs.get_root_dir_entries():
>>>         if v != "":
>>>             print(v)

example to print all fat entries
>>>     for i in range(fs.entries_per_fat):
>>>         print(i,fs._get_cluster_value(i))

example to print all root directory entries
>>>     for i,v in fs.get_root_dir_entries():
>>>         if v != "":
>>>             print(v, i.start_cluster)

"""

from bootsector import FAT12_16Bootsector, FAT32Bootsector
from construct import Struct, Array, Padding, Embedded, Bytes, this
from dir_entry import DirEntry, LfnEntry
from fat_entry import FAT12Entry, FAT16Entry, FAT32Entry
from io import BytesIO, BufferedReader


FAT12PreDataRegion = Struct(
        "bootsector" / Embedded(FAT12_16Bootsector),
        Padding((this.reserved_sector_count - 1) * this.sector_size),
        # FATs. Due to 12 bit addresses in FAT12 we will parse the
        # actual structure later in __init__ method
        "fats" / Array(this.fat_count, Bytes(this.sectors_per_fat * this.sector_size)),
        # RootDir Table
        "rootdir" / Bytes(this.rootdir_entry_count * DirEntry.sizeof())
        )

FAT16PreDataRegion = Struct(
        "bootsector" / Embedded(FAT12_16Bootsector),
        Padding((this.reserved_sector_count - 1) * this.sector_size),
        # FATs
        # "fats" / Array(this.fat_count, Array(this.sectors_per_fat * this.sector_size \
        #                                      / 2, FAT16Entry)),
        "fats" / Array(this.fat_count, Bytes(this.sectors_per_fat * this.sector_size)),
        # RootDir Table
        "rootdir" / Bytes(this.rootdir_entry_count * DirEntry.sizeof())
        )

FAT32PreDataRegion = Struct(
        "bootsector" / Embedded(FAT32Bootsector),
        Padding((this.reserved_sector_count - 1) * this.sector_size),
        # FATs
        # "fats" / Array(this.fat_count, Array(this.sectors_per_fat * this.sector_size \
        #                                      / FAT32Entry.sizeof(), FAT32Entry)),
        "fats" / Array(this.fat_count, Bytes(this.sectors_per_fat * this.sector_size)),
        )


class FAT:
    def __init__(self, stream, predataregion):
        """
        :param stream: filedescriptor of a FAT filesystem
        :param predataregion: Struct that represents the PreDataRegion
                              of the concrete FAT filesystem
        """
        self.stream = stream
        self.offset = stream.tell()
        self.pre = predataregion.parse_stream(stream)
        self.start_dataregion = stream.tell()

    def _get_cluster_value(self, cluster_id):
        """
        finds the value that is written into fat
        for given cluster_id
        :param cluster_id: int, cluster that will be looked up
        :return: int or string
        """
        return self.pre.fats[0][cluster_id]

    def follow_cluster(self, start_cluster):
        """
        collect all cluster, that belong to a file
        :param start_cluster: cluster to start with
        :return: list of cluster numbers (int)
        """
        clusters = [start_cluster]
        while True:
            next_cluster_id = clusters[-1]
            next_cluster = self._get_cluster_value(next_cluster_id)
            if next_cluster == 'last_cluster':
                return clusters
            elif next_cluster == 'free_cluster':
                raise Exception("Cluster %d is a free cluster"
                                % next_cluster_id)
            elif next_cluster == 'bad_cluster':
                raise Exception("Cluster %d is a bad cluster"
                                % next_cluster_id)
            else:
                clusters.append(next_cluster)

    def get_cluster_start(self, cluster_id):
        """
        calculates the start byte of a given cluster_id
        :param cluster_id: id of the cluster
        :return: int, start byte of the given cluster_id
        """
        # offset of requested cluster to the start of dataregion in bytes
        cluster_offset = (cluster_id - 2) \
                * self.pre.sectors_per_cluster \
                * self.pre.sector_size
        # offset of requested cluster to the start of the stream
        cluster_start = self.start_dataregion + cluster_offset
        return cluster_start

    def file_to_stream(self, cluster_id, stream):
        """
        writes all clusters of a file into a given stream
        :param cluster_id: int, cluster_id of the start cluster
        :param stream: stream, the file will written into
        """
        for cluster_id in self.follow_cluster(cluster_id):
            self.cluster_to_stream(cluster_id, stream)

    def cluster_to_stream(self, cluster_id, stream, length=None):
        """
        writes a cluster to a given stream
        :param cluster_id: int, cluster_id of the cluster
                           that will be written to stream
        :param stream: stream, the cluster will written into
        :param length: int, length of the written cluster.
                       Default: cluster size
        """
        if length is None:
            length = self.pre.sectors_per_cluster * self.pre.sector_size
        start = self.get_cluster_start(cluster_id)

        self.stream.seek(start)
        while length > 0:
            read = self.stream.read(length)
            if not len(read):
                print("failed to read %s bytes at %s"
                      % (length, self.stream.tell()))
                raise EOFError()
            length -= len(read)
            stream.write(read)

    def _root_to_stream(self, stream):
        """
        write root directory into a given stream
        only aplicable to FAT12 and FAT16
        :param stream: stream, where the root directory will be written into
        """
        raise NotImplementedError

    def get_root_dir_entries(self):
        """
        iterator for reading the root directory
        """
        for de, lfn in self._get_dir_entries(0):
            yield (de, lfn)

    def get_dir_entries(self, cluster_id):
        """
        iterator for reading a cluster as directory and parse its content
        :param cluster_id: int, cluster to parse
        :return: tuple of (DirEntry, lfn)
        """
        try:
            for de, lfn in self._get_dir_entries(cluster_id):
                yield (de, lfn)
        except IOError:
            print("failed to read directory entries at %s" % cluster_id)

    def _get_dir_entries(self, cluster_id):
        """
        iterator for reading a cluster as directory and parse its content
        :param cluster_id: int, cluster to parse,
                           if cluster_id == 0, parse rootdir
        :return: tuple of (DirEntry, lfn)
        """
        lfn = ''
        de = DirEntry
        lfne = LfnEntry
        with BytesIO() as mem:
            # create an IO stream, to write the directory in it
            if cluster_id == 0:
                # write root dir into stream if cluster_id is 0
                self._root_to_stream(mem)
            else:
                # if cluster_id is != 0, write cluster into stream
                self.file_to_stream(cluster_id, mem)
            mem.seek(0)
            with BufferedReader(mem) as reader:
                while reader.peek(1):
                    # read 32 bit into variable
                    raw = reader.read(32)
                    # parse as DirEntry
                    d = de.parse(raw)
                    a = d.attributes
                    # If LFN attributes are set, parse it as LfnEntry instead
                    if a.volumeLabel and a.system and a.hidden and a.readonly:
                        # if lfn attributes set, convert it to lfnEntry
                        # and save it for later use
                        d = lfne.parse(raw)
                        lfnpart = d.name1 + d.name2 + d.name3

                        # remove non-chars after padding
                        retlfn = b''
                        for i in range(int(len(lfnpart) / 2)):
                            i *= 2
                            b = lfnpart[i:i+2]
                            if b != b'\x00\x00':
                                retlfn += b
                            else:
                                break
                        # append our lfn part to the global lfn, that will
                        # later used as the filename
                        lfn = retlfn.decode('utf-16') + lfn
                    else:
                        retlfn = lfn
                        lfn = ''
                        # add start_cluster attribute for convenience
                        d.start_cluster = int.from_bytes(d.firstCluster,
                                                         byteorder='little')
                        yield (d, retlfn)


class FAT12(FAT):
    def __init__(self, stream):
        """
        :param stream: filedescriptor of a FAT12 filesystem
        """
        super().__init__(stream, FAT12PreDataRegion)
        self.entries_per_fat = int(self.pre.sectors_per_fat
                              * self.pre.sector_size
                              * 8 / 12)

    def _get_cluster_value(self, cluster_id):
        """
        finds the value that is written into fat
        for given cluster_id
        :param cluster_id: int, cluster that will be looked up
        :return: int or string
        """
        # as python read does not allow to read simply 12 bit,
        # we need to do some fancy stuff to extract those from
        # 16 bit long reads
        # this strange layout results from the little endianess
        # which causes that:
        # * clusternumbers beginning at the start of a byte use this
        #   byte + the second nibble of the following byte.
        # * clusternumbers beginning in the middle of a byte use
        #   the first nibble of this byte + the second byte
        # because of little endianess these nibbles need to be
        # reordered as by default int() interpretes hexstrings as
        # big endian
        #
        byte = cluster_id + int(cluster_id/2)
        sl = self.pre.fats[0][byte:byte+2]
        if cluster_id % 2 == 0:
            # if cluster_number is even, we need to wipe the third nibble
            hexvalue = sl.hex()
            value = int(hexvalue[3] + hexvalue[0:2], 16)
        else:
            # if cluster_number is odd, we need to wipe the first nibble
            hexvalue = sl.hex()
            value = int(hexvalue[2:4] + hexvalue[0], 16)
        return FAT12Entry.parse(value.to_bytes(2, 'little'))

    def _root_to_stream(self, stream):
        """
        write root directory into a given stream
        :param stream: stream, where the root directory will be written into
        """
        stream.write(self.pre.rootdir)


class FAT16(FAT):
    def __init__(self, stream):
        """
        :param stream: filedescriptor of a FAT16 filesystem
        """
        super().__init__(stream, FAT16PreDataRegion)
        self.entries_per_fat = int(self.pre.sectors_per_fat
                              * self.pre.sector_size
                              / 2)

    def _get_cluster_value(self, cluster_id):
        """
        finds the value that is written into fat
        for given cluster_id
        :param cluster_id: int, cluster that will be looked up
        :return: int or string
        """
        byte = cluster_id*2
        sl = self.pre.fats[0][byte:byte+2]
        value = int.from_bytes(sl, byteorder='little')
        return FAT16Entry.parse(value.to_bytes(2, 'little'))

    def _root_to_stream(self, stream):
        """
        write root directory into a given stream
        :param stream: stream, where the root directory will be written into
        """
        stream.write(self.pre.rootdir)


class FAT32(FAT):
    def __init__(self, stream):
        """
        :param stream: filedescriptor of a FAT32 filesystem
        """
        super().__init__(stream, FAT32PreDataRegion)
        self.entries_per_fat = int(self.pre.sectors_per_fat
                              * self.pre.sector_size
                              / 4)

    def _get_cluster_value(self, cluster_id):
        """
        finds the value that is written into fat
        for given cluster_id
        :param cluster_id: int, cluster that will be looked up
        :return: int or string
        """
        byte = cluster_id*4
        # TODO: Use active FAT
        sl = self.pre.fats[0][byte:byte+2]
        value = int.from_bytes(sl, byteorder='little')
        return FAT16Entry.parse(value.to_bytes(2, 'little'))

    def _root_to_stream(self, stream):
        """
        write root directory into a given stream
        :param stream: stream, where the root directory will be written into
        """
        raise NotImplementedError

    def get_root_dir_entries(self):
        return self.get_dir_entries(self.pre.rootdir_cluster)

    def _get_dir_entries(self, cluster_id):
        """
        iterator for reading a cluster as directory and parse its content
        :param cluster_id: int, cluster to parse,
                           if cluster_id == 0, parse rootdir
        :return: tuple of (DirEntry, lfn)
        """
        lfn = ''
        de = DirEntry
        lfne = LfnEntry

        start_cluster_id = self.get_cluster_start(cluster_id)
        self.stream.seek(start_cluster_id)
        end_marker = 0xff
        while end_marker != 0x00:
        # for i in range(10):
            # read 32 bit into variable
            raw = self.stream.read(32)
            # parse as DirEntry
            d = de.parse(raw)
            a = d.attributes
            # If LFN attributes are set, parse it as LfnEntry instead
            if a.volumeLabel and a.system and a.hidden and a.readonly:
                # if lfn attributes set, convert it to lfnEntry
                # and save it for later use
                d = lfne.parse(raw)
                lfnpart = d.name1 + d.name2 + d.name3

                # remove non-chars after padding
                retlfn = b''
                for i in range(int(len(lfnpart) / 2)):
                    i *= 2
                    b = lfnpart[i:i+2]
                    if b != b'\x00\x00':
                        retlfn += b
                    else:
                        break
                # append our lfn part to the global lfn, that will
                # later used as the filename
                lfn = retlfn.decode('utf-8') + lfn
            else:
                retlfn = lfn
                lfn = ''
                end_marker = d.name[0]
                # add start_cluster attribute for convenience
                start_cluster = int.from_bytes(d.firstCluster + \
                                               d.accessRightsBitmap,
                                               byteorder='little')
                d.start_cluster = start_cluster
                yield (d, retlfn)
