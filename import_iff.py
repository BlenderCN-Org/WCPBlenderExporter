# -*- coding: utf8 -*-
# Blender WCP IFF mesh import/export script by Kevin Caccamo
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
#
# <pep8-80 compliant>

import bpy
import struct
from . import iff_read, iff_mesh, mat_read
from mathutils import Matrix
from itertools import starmap, count
from os import sep as dirsep, listdir
from collections import OrderedDict

MAX_NUM_LODS = 7
# MAIN_LOD_NAMES = ["detail-" + str(lod) for lod in range(MAX_NUM_LODS)]
CHLD_LOD_NAMES = ["{{0}}-lod{0:d}".format(lod) for lod in range(MAX_NUM_LODS)]

mfilepath = None  # These are Initialized in ImportBackend constructor
texmats = None


class ValueWarning(Warning):
    pass


def register_texture(texnum, read_mats=True):
    """Add a texture to the texture reference if it isn't already there.

    Add a texture to the global texture dictionary if it isn't already in it.
    New entries in the dictionary have the texture number as the key, and the
    Blender material as the value. Return the Blender material associated with
    the newly-registered texture, or the existing Blender material if said
    texture is already in the dictionary.

    @param texnum The texture number to register
    """

    bmtl_name = "{0:0>8d}".format(texnum)

    def get_teximg(texnum, bl_mat):
        mfiledir = mfilepath[:mfilepath.rfind(dirsep)]
        mat_pfx = bmtl_name + "."

        def get_img_fname():
            img_extns = ("bmp", "png", "jpg", "jpeg", "tga", "gif", "dds",
                         "mat")
            print("Searching", mfiledir, "for textures...")
            # Search for high-quality images first.
            for entry in listdir(mfiledir):
                for extn in img_extns:
                    mat_fname = mat_pfx + extn
                    if entry.lower() == mat_fname:
                        return entry
            return None

        mat_fname = get_img_fname()

        if mat_fname is not None:
            # mat_fname is not a MAT.
            if not mat_fname.lower().endswith("mat"):
                bl_img = bpy.data.images.load(mat_fname)
                texmats[texnum][2] = bl_img

                bl_mtexslot = bl_mat.texture_slots.add()
                bl_mtexslot.texture_coords = "UV"

                bl_mtex = bpy.data.textures.new(mat_fname, "IMAGE")
                bl_mtex.image = bl_img

                bl_mtexslot.texture = bl_mtex
            else:
                # mat_fname is a MAT.
                if read_mats:
                    mat_path = mfiledir + dirsep + mat_fname
                    mat_reader = mat_read.MATReader(mat_path)
                    mat_reader.read()
                    mat_reader.flip_y()
                    bl_img = bpy.data.images.new(
                        mat_path[mat_path.rfind(dirsep):],
                        mat_reader.img_width,
                        mat_reader.img_height,
                        True
                    )
                    bl_img.pixels = [
                        x / 255 for x in mat_reader.pixels.tolist()]

                    bl_mtexslot = bl_mat.texture_slots.add()
                    bl_mtexslot.texture_coords = "UV"
                    bl_mtexslot.uv_layer = "UVMap"

                    bl_mtex = bpy.data.textures.new(mat_fname, "IMAGE")
                    bl_mtex.image = bl_img

                    bl_mtexslot.texture = bl_mtex
        else:
            print("Image not found for texture {0:0>8d}!".format(texnum))

    if texnum in texmats.keys():
        return texmats[texnum][1]
    else:
        bl_mat = bpy.data.materials.new(bmtl_name)

        texmats[texnum] = [bmtl_name, bl_mat, None]
        if (texnum & 0xff000000) == 0x7f000000:
            # Flat colour material
            bl_mat.diffuse_color = iff_mesh.texnum_colour(texnum)
        else:
            # Last element in this list will become the image file path
            get_teximg(texnum, bl_mat)
        return bl_mat


def approx_equal(num1, num2, error):
    return (abs(num2 - num1) <= abs(error))


class ImportBackend:

    def __init__(self,
                 filepath,
                 texname,
                 reorient_matrix,
                 import_all_lods=False,
                 use_facetex=False,
                 import_bsp=False,
                 read_mats=False):

        global mfilepath
        global texmats

        mfilepath = filepath
        texmats = {}

        self.reorient_matrix = reorient_matrix
        self.import_all_lods = import_all_lods
        self.use_facetex = use_facetex
        self.import_bsp = import_bsp
        self.read_mats = read_mats
        self.dranges = None
        self.lod_objs = []
        self.base_name = ""


class LODMesh:

    def __init__(self, version, name, vert_data, vtnm_data, fvrt_data,
                 face_data, cntr_data, radi_data):
        self._name = name
        self._cntr = None
        self._radi = None
        self.mtlinfo = OrderedDict()
        self.setup_complete = False
        self.version = version
        self.bl_mesh = None

        # Vertices
        structlen = 12  # 4 bytes * 3 floats (XYZ)
        structstr = "<fff"
        num_verts = len(vert_data) // structlen
        self._verts = [None] * num_verts
        for idx in range(num_verts):
            self._verts[idx] = struct.unpack_from(
                structstr, vert_data, idx * structlen)

        # Vertex Normals
        structlen = 12  # 4 bytes * 3 floats (XYZ)
        structstr = "<fff"
        num_norms = len(vtnm_data) // structlen
        self._norms = [None] * num_norms
        for idx in range(num_norms):
            self._norms[idx] = struct.unpack_from(
                structstr, vtnm_data, idx * structlen)

        # Face vertices
        structstr = "<iiff"
        structlen = 16  # 4 bytes * (2 ints + 2 floats)
        num_fvrts = len(fvrt_data) // structlen
        self._fvrts = [None] * num_fvrts
        for idx in range(num_norms):
            self._fvrts[idx] = struct.unpack_from(
                structstr, vtnm_data, idx * structlen)

        # Faces
        structstr = "<ifiiii" if version >= 11 else "<ifiii"
        structlen = 28 if version >= 11 else 24  # 4 bytes * (6 ints + 1 float)
        num_faces = len(face_data) // structlen
        self._faces = [None] * num_faces
        for idx in range(num_faces):
            self._faces[idx] = struct.unpack_from(
                structstr, vtnm_data, idx * structlen)

        # Center
        structstr = "<fff"
        self._cntr = struct.unpack(structstr, cntr_data)

        structstr = "<f"
        self._radi = struct.unpack(structstr, radi_data)[0]  # Tuple

    def set_name(self, name):
        """Set the name of this mesh."""
        self._name = name.strip()

    def set_cntr(self, cntr):
        """Set the center point for this mesh."""
        if len(cntr) == 3 and all(map(lambda e: isinstance(e, float), cntr)):
            self._cntr = cntr
        else:
            raise TypeError("{0!r} ain't no CNTR!".format(cntr))

    def set_radi(self, radi):
        """Set the radius of this mesh."""
        if not isinstance(radi, float):
            raise TypeError("{0!r} is not a valid radius!".format(radi))
        self._radi = radi

    def edges_from_verts(self, verts):
        """Generates vertex reference tuples for edges."""
        if all(map(lambda e: isinstance(e, int), verts)):
            for idx in range(len(verts)):
                first_idx = verts[idx]
                if (idx + 1) >= len(verts): next_idx = verts[0]
                else: next_idx = verts[idx + 1]
                yield (first_idx, next_idx)
        else:
            raise TypeError("{0!r} ain't vertex references!")

    def setup(self):
        """Take the WC mesh data and convert it to Blender mesh data."""
        assert(
            len(self._verts) > 0 and len(self._norms) > 0 and
            len(self._fvrts) > 0 and len(self._faces) > 0 and
            self._name != "")

        self.bl_mesh = bpy.data.meshes.new(self._name)
        self.bl_mesh.vertices.add(len(self._verts))

        for vidx, v in enumerate(self._verts):
            self.bl_mesh.vertices[vidx].co = v
            self.bl_mesh.vertices[vidx].co[0] *= -1

        face_edges = []  # The edges (tuples of indices of two verts)
        edge_refs = []  # indices of edges of faces, as lists per face

        for fidx, f in enumerate(self._faces):

            # used_fvrts = []
            cur_face_verts = []

            for fvrt_ofs in range(f[4]):  # f[4] is number of FVRTS of the face

                cur_fvrt = f[3] + fvrt_ofs  # f[3] is index of first FVRT
                cur_face_verts.append(self._fvrts[cur_fvrt][0])

                self.bl_mesh.vertices[self._fvrts[cur_fvrt][0]].normal = (
                    self._norms[self._fvrts[cur_fvrt][1]])

                self.bl_mesh.vertices[self._fvrts[cur_fvrt][0]].normal[0] *= -1
                # used_fvrts.append(f[3] + fvrt_ofs)
            edge_refs.append([])

            for ed in self.edges_from_verts(tuple(reversed(cur_face_verts))):
                if (ed not in face_edges and
                        tuple(reversed(ed)) not in face_edges):
                    eidx = len(face_edges)
                    face_edges.append(ed)
                else:
                    if face_edges.count(ed) == 1:
                        eidx = face_edges.index(ed)
                    else:
                        eidx = face_edges.index(tuple(reversed(ed)))
                edge_refs[fidx].append(eidx)

            # Get texture info
            # f[2] = Texture number, f[5] = Light flags
            self.mtlinfo[(f[2], f[5])] = None  # Assign material later
            # if f[2] in texmats.keys():
            #     if texmats[f[2]][0] not in self.bl_mesh.materials:
            #         self.mtlinfo[f[2]] = len(self.bl_mesh.materials)
            #         self.bl_mesh.materials.append(texmats[f[2]][1])

        self.bl_mesh.edges.add(len(face_edges))
        for eidx, ed in enumerate(face_edges):
            self.bl_mesh.edges[eidx].vertices = ed

        self.bl_mesh.polygons.add(len(self._faces))
        self.bl_mesh.uv_textures.new("UVMap")
        num_loops = 0

        for fidx, f in enumerate(self._faces):

            cur_face_fvrts = self._fvrts[f[3]:f[3] + f[4]]
            f_verts = [fvrt[0] for fvrt in cur_face_fvrts]
            f_uvs = [
                (fvrt[2], 1 - fvrt[3]) for fvrt in reversed(cur_face_fvrts)]
            f_edgerefs = edge_refs[fidx]
            f_startloop = num_loops

            self.bl_mesh.polygons[fidx].vertices = f_verts

            # Assign corresponding material to polygon
            self.bl_mesh.polygons[fidx].material_index = (
                list(self.mtlinfo).index((f[2], f[5])))

            assert(len(f_verts) == len(f_edgerefs) == f[4])

            # print("Face", fidx, "loop_total:", f[4])

            # The edges were generated from a set of vertices in reverse order.
            # Since we're getting the vertices from the FVRTs in forward order,
            # only reverse the vertices.
            for fvidx, vrt, edg in zip(
                    count(), reversed(f_verts), f_edgerefs):
                self.bl_mesh.loops.add(1)
                self.bl_mesh.loops[num_loops].edge_index = edg
                self.bl_mesh.loops[num_loops].vertex_index = vrt

                # print("Loop", num_loops, "vertex index:", vrt)
                # print("Loop", num_loops, "edge index:", edg)
                # print("Edge", edg, "vertices",
                #       self.bl_mesh.edges[edg].vertices[0],
                #       self.bl_mesh.edges[edg].vertices[1])

                self.bl_mesh.uv_layers["UVMap"].data[num_loops].uv = (
                    f_uvs[fvidx])
                num_loops += 1

            self.bl_mesh.polygons[fidx].loop_start = f_startloop
            self.bl_mesh.polygons[fidx].loop_total = f[4]
        # Materials need to be assigned afterwards

    def get_mtlinfo(self):
        return self.mtlinfo

    def assign_materials(self, materials):
        mtxslots = {}  # Optimization

        def mtl_image(material):
            # Get material image for face texture
            if material not in mtxslots:
                for tsi, ts in enumerate(material.texture_slots):
                    if (ts.use and ts.use_map_color_diffuse and
                            ts.texture.type == "IMAGE"):
                        mtxslots[material] = tsi
                        return ts.texture.image
            else:
                return material.texture_slots[mtxslots[material]].texture.image

        for mi, mtl in enumerate(materials):
            if isinstance(mtl, Material):
                # Add material to list of materials for the mesh
                self.bl_mesh.materials.append(mtl)
                # Assign corresponding image to UV image texture (AKA facetex)
                for fi, f in enumerate(self.bl_mesh.polygons):
                    if f.material_index == mi:
                        self.bl_mesh.uv_layers["UVMap"].data[fi].image = (
                            mtl_image(mtl))

    def get_bl_mesh(self):
        if self.bl_mesh and setup_complete:
            return self.bl_mesh


class IFFImporter(ImportBackend):

    def read_rang_chunk(self, rang_chunk):
        if rang_chunk["length"] % 4 != 0:
            raise ValueError("RANG chunk has an invalid length!")
        num_dranges = rang_chunk["length"] // 4
        dranges = struct.unpack("<" + ("f" * num_dranges), rang_chunk["data"])
        return dranges

    def parse_major_mesh_form(self, mesh_form):
        mjrmsh_read = 4
        # Read all LODs
        while mjrmsh_read < mesh_form["length"]:
            lod_form = self.iff_reader.read_data()
            lod_lev = int(lod_form["name"].decode("ascii"))

            mnrmsh = self.iff_reader.read_data()
            if mnrmsh["type"] == "form" and mnrmsh["name"] == b"MESH":
                self.parse_minor_mesh_form(mnrmsh, lod_lev)
            elif mnrmsh["type"] == "form" and mnrmsh["name"] == b"EMPT":
                if self.base_name != "":
                    bl_obname = CHLD_LOD_NAMES[lod_lev].format(self.base_name)
                else:
                    bl_obname = "detail-{}".format(lod_lev)
                bl_ob = bpy.data.objects.new(bl_obname, None)
                bpy.context.scene.objects.link(bl_ob)
                self.lod_objs.append(bl_ob)

            mjrmsh_read += 8 + lod_form["length"]
            print("mjrmsh_read:", mjrmsh_read, "of", mesh_form["length"])

    def parse_minor_mesh_form(self, mesh_form, lod_lev=0):
        # lodm = LODMesh()

        mnrmsh_read = 4

        vers_form = self.iff_reader.read_data()
        mesh_vers = int(vers_form["name"].decode("ascii"))
        mnrmsh_read += 12

        print("---------- LOD {} (version {}) ----------".format(
            lod_lev, mesh_vers
        ))

        # Use 28 to skip the "unknown2" value, present in mesh versions 11+
        face_size = 28 if mesh_vers >= 11 else 24
        mesh_name = ""
        vert_data = None
        vtnm_data = None
        fvrt_data = None
        face_data = None
        cntr_data = None
        radi_data = None

        while mnrmsh_read < mesh_form["length"]:
            geom_data = self.iff_reader.read_data()
            mnrmsh_read += 8 + geom_data["length"]
            print("mnrmsh_read:", mnrmsh_read, "of", mesh_form["length"])

            # NORM chunk is ignored

            # Internal name of "minor" mesh/LOD mesh
            if geom_data["name"] == b"NAME":
                mesh_name = self.read_cstring(geom_data["data"], 0)
                if self.base_name == "":
                    self.base_name = mesh_name

            # Vertices
            elif geom_data["name"] == b"VERT":
                vert_data = geom_data["data"]

            # Vertex normals.
            elif geom_data["name"] == b"VTNM" and mesh_vers != 9:
                vtnm_data = geom_data["data"]

            # Vertex normals (mesh version 9).
            elif geom_data["name"] == b"NORM" and mesh_vers == 9:
                vtnm_data = geom_data["data"]

            # Vertices for each face
            elif geom_data["name"] == b"FVRT":
                fvrt_data = geom_data["data"]

            # Face info
            elif geom_data["name"] == b"FACE":
                face_data = geom_data["data"]

            # Center point
            elif geom_data["name"] == b"CNTR":
                cntr_data = geom_data["data"]

            elif geom_data["name"] == b"RADI":
                radi_data = geom_data["data"]

            # print(
            #     "geom length:", geom["length"],
            #     "geom read:", geom_bytes_read,
            #     "current position:", self.iff_file.tell()
            # )
        try:
            lodm = LODMesh(mesh_vers, mesh_name, vert_data, vtnm_data,
                           fvrt_data, face_data, cntr_data, radi_data)
            lodm.setup()
            mtlinfo = lodm.get_mtlinfo()
            if isinstance(self.reorient_matrix, Matrix):
                bl_mesh.transform(self.reorient_matrix)
            bl_obname = CHLD_LOD_NAMES[lod_lev].format(self.base_name)
            bl_ob = bpy.data.objects.new(bl_obname, bl_mesh)
            bpy.context.scene.objects.link(bl_ob)
            if lod_lev > 0:
                # Set drange custom property
                try:
                    bl_ob["drange"] = self.dranges[lod_lev]
                except IndexError:
                    try:
                        del bl_ob["drange"]
                    except KeyError:
                        pass
            self.lod_objs.append(bl_ob)
        except AssertionError:
            lodm.debug_info()

    def read_hard_data(self, major_form):
        mjrf_bytes_read = 4
        while mjrf_bytes_read < major_form["length"]:
            hardpt_chunk = self.iff_reader.read_data()
            mjrf_bytes_read += hardpt_chunk["length"] + 8

            hardpt = iff_mesh.Hardpoint.from_chunk(hardpt_chunk["data"])
            bl_ob = hardpt.to_bl_obj()

            bpy.context.scene.objects.link(bl_ob)
            bl_ob.parent = self.lod_objs[0]

    def read_coll_data(self):
        coll_data = self.iff_reader.read_data()
        if coll_data["name"] == b"SPHR":
            coll_sphere = iff_mesh.Sphere.from_sphr_chunk(coll_data["data"])

            bl_obj = coll_sphere.to_bl_obj("collsphr")
            bpy.context.scene.objects.link(bl_obj)
            bl_obj.parent = self.lod_objs[0]

    def read_cstring(self, data, ofs):
        cstring = bytearray()
        the_byte = 1
        while the_byte != 0:
            the_byte = data[ofs]
            if the_byte == 0: break
            cstring.append(the_byte)
            ofs += 1
        return cstring.decode("iso-8859-1")

    def load(self):
        self.iff_reader = iff_read.IffReader(mfilepath)
        root_form = self.iff_reader.read_data()
        if root_form["type"] == "form":
            print("Root form is:", root_form["name"])
            if root_form["name"] == b"DETA":
                mjrfs_read = 4
                while mjrfs_read < root_form["length"]:
                    major_form = self.iff_reader.read_data()
                    mjrfs_read += major_form["length"] + 8
                    # print("Reading major form:", major_form["name"])
                    if major_form["name"] == b"RANG":
                        self.dranges = self.read_rang_chunk(major_form)
                    elif major_form["name"] == b"MESH":
                        self.parse_major_mesh_form(major_form)
                    elif major_form["name"] == b"HARD":
                        self.read_hard_data(major_form)
                    elif major_form["name"] == b"COLL":
                        self.read_coll_data()
                    elif major_form["name"] == b"FAR ":
                        pass  # FAR data is useless to Blender.
                    else:
                        # print("Unknown major form:", major_form["name"])
                        pass

                    # print(
                    #     "root form length:", root_form["length"],
                    #     "root form bytes read:", mjrfs_read
                    # )
            elif root_form["name"] == b"MESH":
                self.parse_minor_mesh_form(root_form)
            else:
                self.iff_reader.close()
                raise TypeError(
                    "This file isn't a mesh! (root form is {})".format(
                        root_form["name"].decode("iso-8859-1")))
        else:
            self.iff_reader.close()
            raise TypeError("This file isn't a mesh! (root is not a form)")
        self.iff_reader.close()
