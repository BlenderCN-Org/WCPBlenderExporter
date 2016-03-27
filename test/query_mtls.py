#!/usr/bin/env python3
# Query MTLs - a little side project of mine.
# Copyright © 2013-2016 Kevin Caccamo
# E-mail: kevin@ciinet.org
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, see <http://www.gnu.org/licenses/>.
# -*- coding: utf8 -*-

import argparse
import struct
from os import getcwd
from os.path import abspath
from sys import path
import json
path.append(abspath(getcwd() + "/.."))
from iff_read import IffReader
import iff_mesh


class IffMeshReader:

    FACE_FMT = "<ifiiiii"
    HARD_FMT = "<ffffffffffff"

    def __init__(self, iff_fname):
        self.iff = IffReader(iff_fname)
        # self.out_mode = out_mode
        self.lods = {}
        self.hardpoints = []

    def parse_rang_chunk(self, rang_data):
        # The RANG chunk is just a bunch of floats
        num_ranges = len(rang_data["data"]) // 4
        ranges = struct.unpack("<" + ("f" * num_ranges), rang_data["data"])
        return ranges

    def parse_deta_form(self, deta_form):
        deta_read = 4
        while deta_read < deta_form["length"]:

            mdata = self.iff.read_data()
            if mdata["type"] == "chunk" and mdata["name"] == b"RANG":
                self.parse_rang_chunk(mdata)
            elif mdata["type"] == "form" and mdata["name"] == b"MESH":
                self.parse_mesh_form(mdata)
            elif mdata["type"] == "form" and mdata["name"] == b"HARD":
                self.parse_hard_form(mdata)
            elif mdata["type"] == "form" and mdata["name"] == b"COLL":
                self.parse_coll_form(mdata)

            deta_read += mdata["length"]
            # Don't add bytes read if type of data is form
            if mdata["type"] == "chunk": deta_read += 8

    def parse_mesh_form(self, mesh_form):
        mjrmsh_read = 4

        while mjrmsh_read < mesh_form["length"]:

            lod_form = self.iff.read_data()
            # print("LOD FORM offset:", lod_form["offset"])
            # print("LOD FORM name:", lod_form["name"])
            # print("LOD FORM length:", lod_form["length"])
            lod_lev = int(lod_form["name"].decode("ascii"))
            self.iff.read_data()  # Minor MESH form
            vers_form = self.iff.read_data()
            mesh_vers = int(vers_form["name"].decode("ascii"))
            mjrmsh_read += 8  # Bytes for LOD form header

            mdat_len = vers_form["length"]
            mdat_read = 4

            self.lods[lod_lev] = {}
            self.lods[lod_lev]["mats"] = []
            self.lods[lod_lev]["altmats"] = []
            self.lods[lod_lev]["name"] = ""
            self.lods[lod_lev]["version"] = mesh_vers
            while mdat_read < mdat_len:
                mdat = self.iff.read_data()

                if mdat["type"] == "chunk":
                    mdat_read += 8 + mdat["length"]

                if mdat["name"] == b"NAME":
                    self.lods[lod_lev]["name"] = (
                        self.parse_cstr(mdat["data"], 0))
                elif mdat["name"] == b"FACE":

                    # This isn't part of Wing Blender, so I'm using features
                    # from newer versions of Python 3.
                    for f in struct.iter_unpack(self.FACE_FMT, mdat["data"]):
                        if f[2] not in self.lods[lod_lev]["mats"]:
                            self.lods[lod_lev]["mats"].append(f[2])
                        if f[6] not in self.lods[lod_lev]["altmats"]:
                            self.lods[lod_lev]["altmats"].append(f[2])

            mjrmsh_read += lod_form["length"]
            # print("mjrmsh_read:", mjrmsh_read, "of", mesh_form["length"])

    def parse_cstr(self, data, offset):
        cstr = bytearray()
        while data[offset] != 0:
            cstr.append(data[offset])
            offset += 1
        return cstr.decode("ascii", "ignore")

    def parse_hard_form(self, hard_form):
        hard_read = 4
        while hard_read < hard_form["length"]:
            hard_chunk = self.iff.read_data()

            hard_name_offset = struct.calcsize(self.HARD_FMT)

            hard_read += 8 + hard_chunk["length"]
            hard_read += 1 if hard_chunk["length"] % 2 == 1 else 0

            hard_name = self.parse_cstr(hard_chunk["data"], hard_name_offset)
            hard_xfm = struct.unpack_from(self.HARD_FMT, hard_chunk["data"])

            hard_matrix = (
                (hard_xfm[0], hard_xfm[1], hard_xfm[2]),
                (hard_xfm[4], hard_xfm[5], hard_xfm[6]),
                (hard_xfm[8], hard_xfm[9], hard_xfm[10])
            )
            hard_loc = (hard_xfm[3], hard_xfm[7], hard_xfm[11])
            self.hardpoints.append(
                iff_mesh.Hardpoint(hard_matrix, hard_loc, hard_name))

    def parse_coll_form(self, coll_form):
        pass

    def read(self):
        root_form = self.iff.read_data()
        root_read = 4

        if root_form["name"] == b"DETA":
            self.parse_deta_form(root_form)
        elif root_form["name"] == b"MESH":
            self.parse_mesh_form(root_form)


def print_iff_data(iffthing):
    print("--- IFF data ---")
    print("type:", iffthing["type"])
    print("name:", iffthing["name"])
    print("length:", iffthing["length"])
    print("offset:", iffthing["offset"])
    print("data:", iffthing.get("data", "None"))

if __name__ == '__main__':

    argp = argparse.ArgumentParser(
        description="Find out what materials a WCP/SO mesh uses.",
        epilog="Info will be displayed on a per-LOD basis")
    argp.add_argument('mesh', action='store', nargs='+', metavar='mesh.iff',
                      help="The IFF mesh to query.")
    argp.add_argument('--for-lod', '-l', action='store', nargs='?', type=int,
                      metavar='LOD', dest='for_lod', required=False,
                      default=None,
                      help="The LOD for which to query material usage.")
    argp.add_argument('--out-format', action='store', nargs='?',
                      metavar='FORMAT', dest='out_fmt', required=False,
                      default='tty', const='tty', choices=['tty', 'json'],
                      help="The format to output the data in.")

    args = argp.parse_args()

    for_lod = getattr(args, 'for_lod', None)
    modelfs = getattr(args, 'mesh', None)
    out_mode = getattr(args, 'out_fmt', "tty")

    for cur_model, modelf in enumerate(modelfs):

        if out_mode == "tty":
            print("--- Model: %s ---" % modelf)
        elif out_mode == "json":
            model_data.append({"name": modelf})

        model_reader = IffMeshReader(modelf)
        model_reader.read()

        if out_mode == "tty":
            for lod_lev, lod_dat in model_reader.lods.items():
                print ("--- LOD %d (version %d) ---"  % (lod_lev, lod_dat["version"]))
