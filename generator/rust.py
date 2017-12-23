# Copyright (c) 2016 Nuxi (https://nuxi.nl/) and contributors.
#
# This file is distributed under a 2-clause BSD license.
# See the LICENSE and CONTRIBUTORS files for details.

import re

from .abi import *
from .generator import *


class RustNaming:

    def __init__(self):
        pass

    def typename(self, type):
        if isinstance(type, VoidType):
            return '()'
        elif isinstance(type, IntType):
            if type.name == 'char':
                return 'u8'
            elif type.name == 'size':
                return 'usize'
            elif type.name[0:3] == 'int':
                return 'i' + type.name[3:]
            elif type.name[0:4] == 'uint':
                return 'u' + type.name[4:]
            else:
                raise Exception('Unknown int type: {}'.format(type.name))
        elif isinstance(type, UserDefinedType):
            return type.name
        elif isinstance(type, AtomicType):
            # TODO: Update once rust has generic atomic types
            return self.typename(type.target_type)
        elif isinstance(type, PointerType):
            if isinstance(type.target_type, FunctionType):
                return self.typename(type.target_type)
            mut = 'const' if type.const else 'mut'
            return '*{} {}'.format(mut, self.typename(type.target_type))
        elif isinstance(type, ArrayType):
            return '[{}; {}]'.format(
                self.typename(type.element_type),
                type.count)
        elif isinstance(type.target_type, VoidType):
            return '()'
        else:
            raise Exception('Unable to generate Rust declaration '
                            'for type: {}'.format(type))

    def valname(self, type, value):
        if isinstance(type, FlagsType) or isinstance(type, EnumType):
            if value.name == '2big':
                return 'TOOBIG'
            return value.name.upper()
        else:
            return '{}{}'.format(type.cprefix, value.name).upper()

    def syscallname(self, syscall):
        return syscall.name

    def vardecl(self, type, name, array_need_parens=False):
        return '{}: {}'.format(name, self.typename(type))

    def fieldname(self, name):
        if name == 'type':
            return 'type_'
        return name


class RustGenerator(Generator):

    def print_doc(self, thing, indent = '', prefix = '///'):
        if hasattr(thing, 'doc'):
            for line in thing.doc.splitlines():
                line = re.sub(r'\[([\w.]+)\](?!\()', r'`\1`', line)
                print(indent + prefix + (' ' + line if line != '' else ''))

    def __init__(self, naming):
        super().__init__(comment_prefix='// ')
        self.naming = naming

    def syscall_params(self, syscall):
        params = []
        for p in syscall.input.raw_members:
            params.append(self.naming.vardecl(p.type, p.name))
        for p in syscall.output.raw_members:
            params.append(self.naming.vardecl(OutputPointerType(p.type),
                                              p.name))
        return params


class RustSyscalldefsGenerator(RustGenerator):

    def generate_head(self, abi):
        super().generate_head(abi)
        print('//! **PLEASE NOTE: This entire crate including this '
              'documentation is automatically generated from '
              '[`cloudabi.txt`](https://github.com/NuxiNL/cloudabi/blob/master/cloudabi.txt)**')
        self.print_doc(abi, '', '//!')
        print()
        print('#![allow(dead_code)]')
        print('#![allow(non_camel_case_types)]')
        print('#[macro_use]')
        print('extern crate bitflags;')

    def generate_type(self, abi, type):

        if isinstance(type, FlagsType):
            print('bitflags! {')
            self.print_doc(type, '  ')
            print('  pub struct {}: {} {{'.format(self.naming.typename(type), self.naming.typename(type.int_type)))
            if len(type.values) > 0:
                width = max(
                    len(self.naming.valname(type, v)) for v in type.values)
                val_format = '#0{}x'.format(type.layout.size[0] * 2 + 2)
                for v in type.values:
                    self.print_doc(v, '    ')
                    print('    const {name:{width}} = {val:{val_format}};'.format(
                              name=self.naming.valname(type, v),
                              width=width,
                              val=v.value,
                              val_format=val_format))
            else:
                print('    const DEFAULT = 0;')
            print('  }')
            print('}')

        elif isinstance(type, EnumType):
            self.print_doc(type)
            print('#[repr({})]'.format(self.naming.typename(type.int_type)))
            print('#[derive(Copy, Clone, Eq, PartialEq, Hash, Debug)]')
            print('pub enum {} {{'.format(self.naming.typename(type)))
            if len(type.values) > 0:
                width = max(
                    len(self.naming.valname(type, v)) for v in type.values)
                val_format = '{}d'.format(max(len(str(v.value)) for v in type.values))
                for v in type.values:
                    self.print_doc(v, '  ')
                    print('  {name:{width}} = {val:{val_format}},'.format(
                              name=self.naming.valname(type, v),
                              width=width,
                              val=v.value,
                              val_format=val_format))
            #TODO: use #[non_exhaustive] once it's in the rust release version:
            # https://github.com/rust-lang/rust/issues/44109
            print('  #[doc(hidden)] _NonExhaustive = -1 as isize as {},'.format(self.naming.typename(type.int_type)))
            print('}')

        elif isinstance(type, OpaqueType) or isinstance(type, AliasType):
            self.print_doc(type)
            if isinstance(type, OpaqueType):
                print('#[repr(C)]')
                print('#[derive(Copy, Clone, Eq, PartialEq, Hash, Debug)]')
                print('pub struct {}(pub {});'.format(
                    self.naming.typename(type),
                    self.naming.typename(type.int_type)))
                const_format = 'pub const {name:{width}}: {type} = {type}({val:{val_format}});'
            else:
                print('pub type {} = {};'.format(
                    self.naming.typename(type),
                    self.naming.typename(type.int_type)))
                const_format = 'pub const {name:{width}}: {type} = {val:{val_format}};'
            if len(type.values) > 0:
                width = max(
                    len(self.naming.valname(type, v)) for v in type.values)
                if (isinstance(type, FlagsType) or
                        isinstance(type, OpaqueType)):
                    if len(type.values) == 1 and type.values[0].value == 0:
                        val_format = 'd'
                    else:
                        val_format = '#0{}x'.format(
                            type.layout.size[0] * 2 + 2)
                else:
                    val_width = max(len(str(v.value)) for v in type.values)
                    val_format = '{}d'.format(val_width)
                for v in type.values:
                    self.print_doc(v)
                    print(const_format.format(
                              name=self.naming.valname(type, v),
                              width=width,
                              type=self.naming.typename(type),
                              val=v.value,
                              val_format=val_format))

        elif isinstance(type, FunctionType):
            self.print_doc(type)
            for param in type.parameters.raw_members:
                print('///')
                print('/// **{}**:'.format(param.name))
                self.print_doc(param)
            print('pub type {} = extern "C" fn('.format(self.naming.typename(type)))
            for param in type.parameters.raw_members:
                print('  {}: {},'.format(param.name,
                    self.naming.typename(param.type)))
            print(') -> {};'.format(self.naming.typename(type.return_type)))

        elif isinstance(type, StructType):
            structs = [(self.naming.typename(type), type)]
            unions = []

            while len(structs) > 0 or len(unions) > 0:
                for name, struct in structs:
                    self.print_doc(struct)
                    print('#[repr(C)]')
                    print('#[derive(Copy, Clone)]')
                    print('pub struct {} {{'.format(name))
                    for m in struct.members:
                        self.print_doc(m, '  ')
                        if isinstance(m, SimpleStructMember):
                            print('  pub {}: {},'.format(
                                self.naming.fieldname(m.name), self.naming.typename(m.type)))
                        elif isinstance(m, RangeStructMember):
                            print('  pub {}: ({}, {}),'.format(
                                self.naming.fieldname(m.name),
                                self.naming.typename(m.raw_members[0].type),
                                self.naming.typename(m.raw_members[1].type)))
                        elif isinstance(m, VariantStructMember):
                            unions.append((name + '_union', m))
                            print('  pub union: {}_union'.format(name))
                        else:
                            raise Exception('Unknown struct member: {}'.format(m))
                    print('}')

                structs = []

                # To support multiple unions in the same struct, we should first
                # give them different names.
                assert(len(unions) <= 1)

                for name, union in unions:
                    print('#[repr(C)]')
                    print('#[derive(Copy, Clone)]')
                    print('pub union {} {{'.format(name))
                    for x in m.members:
                        if x.name is None:
                            assert(len(x.type.members) == 1)
                            m = x.type.members[0]
                            print('  pub {}: {},'.format(
                                self.naming.fieldname(m.name), self.naming.typename(m.type)))
                        else:
                            structname = '{}_{}'.format(self.naming.typename(type), x.name)
                            structs.append((structname, x.type))
                            print('  pub {}: {},'.format(
                                self.naming.fieldname(x.name), structname))
                    print('}')

                unions = []

            for name, struct in structs:
                print('#[repr(C)]')
                print('#[derive(Copy, Clone)]')
                print('pub struct {}_{} {{'.format(
                    self.naming.typename(type), name))
                for m in struct.raw_members:
                    assert(isinstance(m, SimpleStructMember))
                    print('  pub {}: {},'.format(
                        self.naming.fieldname(m.name), self.naming.typename(m.type)))
                print('}')

        else:
            raise Exception('Unknown class of type: {}'.format(type))

        print()
