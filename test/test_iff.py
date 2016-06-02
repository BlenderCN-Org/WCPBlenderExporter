#!/usr/bin/env python3
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
# -*- coding: utf8 -*-

from os import getcwd
import os.path
import sys
import unittest

sys.path.append(os.path.abspath(getcwd() + "/.."))


class TestIFFFormAndChunk(unittest.TestCase):

    def setUp(self):
        import iff
        self.ifff = iff.IffForm("FONG")
        self.iffc_ponf = iff.IffChunk("PONF")
        self.iffc_ponf.add_member(12.345)
        self.iffc_ponf.add_member("I am poncho man!")
        self.iffc_ponf.add_member(12345)
        self.ifff.add_member(self.iffc_ponf)
        self.iffc_gone = iff.IffChunk("GONE")
        self.iffc_gone.add_member(42)
        self.ifff.add_member(self.iffc_gone)
        self.ifff_empty = iff.IffForm("EMPT")
        self.ifff.add_member(self.ifff_empty)

    def test_iff_form(self):
        import iff
        self.assertIsNotNone(iff.IffForm("BABY"), 'Cannot create Form BABY!')
        self.assertEqual("IffForm 'BOOK'", str(iff.IffForm("BOOK")),
                         "IffForm isn't converting to a string properly!")

        # Exception testing.
        # Invalid Form ID
        self.assertRaises(ValueError, iff.IffForm, ("\x02Aéâ"))
        # Invalid member types
        self.assertRaises(TypeError, iff.IffForm, "DETA", [192, 2.25, "abc"])

    def test_iff_chunk(self):
        import iff
        self.assertIsNotNone(iff.IffChunk("DOCK"), 'Cannot create chunk DOCK!')
        self.assertEqual("IffChunk 'SOCK'", str(iff.IffChunk("SOCK")),
                         "IffChunk isn't converting to a string properly!")

        # Exception testing.
        # Invalid Chunk ID
        self.assertRaises(ValueError, iff.IffChunk, ("\x02Aé\xFF"))
        # Invalid member types
        self.assertRaises(TypeError, iff.IffChunk, "META",
                          [iff.IffChunk("SETA"), iff.IffForm("ZETA")])

    def test_chunk(self):
        """Check chunk length and content"""
        self.assertEqual(25, self.iffc_ponf.get_length(),
                         'Chunk PONF is wrong length!')
        self.assertEqual(4, self.iffc_gone.get_length(),
                         'Chunk GONE is wrong length!')
        self.assertEqual(
            b'GONE\x00\x00\x00\x04*\x00\x00\x00', self.iffc_gone.to_bytes(),
            'chunk GONE is outputting incorrectly')
        self.assertEqual(
            b'PONF\x00\x00\x00\x19\x1F\x85EAI am poncho man!\x0090\x00\x00'
            b'\x00',
            self.iffc_ponf.to_bytes(), 'chunk PONF is outputting incorrectly')

        import iff
        # Test clear_members method of IffChunk
        void_chnk = iff.IffChunk("VOID")
        void_chnk.add_member(42)
        void_chnk.clear_members()

        self.assertEqual(
            0, void_chnk.get_length(),
            'chunk VOID is wrong length after clearing its members!')
        self.assertEqual(b"VOID\x00\x00\x00\x00", void_chnk.to_bytes(),
                         'chunk VOID is outputting incorrectly!')

    def test_form(self):
        """Check root form length and content"""
        self.assertEqual(62, self.ifff._length, 'Form FONG is wrong length!')
        self.assertEqual(
            b'FORM\x00\x00\x00>FONGPONF\x00\x00\x00\x19\x1f\x85EAI am poncho '
            b'man!\x0090\x00\x00\x00GONE\x00\x00\x00\x04*\x00\x00\x00FORM\x00'
            b'\x00\x00\x04EMPT',
            self.ifff.to_bytes(), 'Form FONG is outputting incorrectly!')


class TestIFFFile(unittest.TestCase):

    def setUp(self):
        import iff
        self.iffl = iff.IffFile("TEST")
        iffc_fib = iff.IffChunk("FIB ")
        iffc_fib.add_member(1)
        iffc_fib.add_member(1)
        iffc_fib.add_member(2)
        iffc_fib.add_member(3)
        iffc_fib.add_member(5)
        iffc_fib.add_member(8)
        iffc_fib.add_member(13)
        self.iffl.get_root_form().add_member(iffc_fib)
        self.iffl.set_comment("The FIB chunk represents the first 7 numbers "
                              "of a fibonacci sequence, as little-endian "
                              "32-bit integers.")

    def test_bytes(self):
        self.assertEqual(
            b'FORM\x00\x00\x00(TESTFIB \x00\x00\x00\x1C\x01\x00\x00\x00'
            b'\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00\x05\x00\x00\x00'
            b'\x08\x00\x00\x00\x0D\x00\x00\x00The FIB chunk represents the '
            b'first 7 numbers of a fibonacci sequence, as little-endian '
            b'32-bit integers.', self.iffl.to_bytes(),
            'The IFF is outputting incorrectly!')


if __name__ == '__main__':
    unittest.main()
