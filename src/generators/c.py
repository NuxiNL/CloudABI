# Copyright (c) 2016 Nuxi, https://nuxi.nl/
#
# This file is distributed under a 2-clause BSD license.
# See the LICENSE file for details.

from ..abi import *
from ..generator import *


class CGenerator(Generator):

    def __init__(self, prefix):
        super().__init__(comment_start='//')
        self.prefix = prefix

    def ctypename(self, type):
        if isinstance(type, VoidType):
            return 'void'
        elif isinstance(type, IntType):
            if type.name == 'char':
                return 'char'
            return '{}_t'.format(type.name)
        elif (isinstance(type, IntLikeType) or
              isinstance(type, FunctionPointerType) or
              isinstance(type, StructType)):
            return '{}{}_t'.format(self.prefix, type.name)

        else:
            raise Exception(
                'Unable to generate C type name for type: {}'.format(type))

    def cdecl(self, type, name=''):
        if (isinstance(type, VoidType) or
                isinstance(type, IntType) or
                isinstance(type, IntLikeType) or
                isinstance(type, StructType) or
                isinstance(type, FunctionPointerType)):
            return '{} {}'.format(self.ctypename(type), name).rstrip()

        elif isinstance(type, PointerType):
            decl = self.cdecl(type.target_type, '*{}'.format(name))
            if type.const:
                decl = 'const ' + decl
            return decl

        elif isinstance(type, ArrayType):
            if name.startswith('*'):
                name = '({})'.format(name)
            return self.cdecl(
                type.element_type, '{}[{}]'.format(
                    name, type.count))

        elif isinstance(type, AtomicType):
            return '_Atomic({}) {}'.format(
                self.cdecl(type.target_type), name).rstrip()

        else:
            raise Exception(
                'Unable to generate C type declaration for type: {}'.format(type))

    def syscall_params(self, syscall):
        params = []
        for p in syscall.input.raw_members:
            params.append(self.cdecl(p.type, p.name))
        for p in syscall.output.raw_members:
            params.append(self.cdecl(PointerType(False, p.type), p.name))
        if params == []:
            params = ['void']
        return params


class CHeaderGenerator(CGenerator):

    def generate_struct_members(self, type, indent=''):
        for m in type.raw_members:
            if isinstance(m, SimpleStructMember):
                print('{}{};'.format(indent, self.cdecl(m.type, m.name)))
            elif isinstance(m, VariantStructMember):
                print('{}union {{'.format(indent))
                for x in m.members:
                    if x.name is None:
                        self.generate_struct_members(x.type, indent + '\t')
                    else:
                        print('{}\tstruct {{'.format(indent))
                        self.generate_struct_members(x.type, indent + '\t\t')
                        print('{}\t}} {};'.format(indent, x.name))
                print('{}}};'.format(indent))
            else:
                raise Exception('Unknown struct member: {}'.format(m))

    def generate_type(self, type):

        if isinstance(type, IntLikeType):
            print('typedef {};'.format(self.cdecl(type.int_type,
                                                  self.ctypename(type))))
            use_hex = (isinstance(type, FlagsType) or
                       isinstance(type, OpaqueType))
            for val, name in type.values:
                if use_hex:
                    val = hex(val)
                print('#define {}{}{} {}'.format(
                    self.prefix.upper(),
                    type.cprefix,
                    name.upper(),
                    val))

        elif isinstance(type, FunctionPointerType):
            parameters = []
            for p in type.parameters.raw_members:
                parameters.append(self.cdecl(p.type, p.name))
            print('typedef {} (*{})({});'.format(
                self.cdecl(type.return_type),
                self.cdecl(type), ', '.join(parameters)))
            pass

        elif isinstance(type, StructType):
            typename = self.ctypename(type)

            print('typedef struct {')
            self.generate_struct_members(type, '\t')
            print('}} {};'.format(typename))

            self.generate_offset_asserts(typename, type.raw_members)

            if type.layout is not None:
                self.generate_size_assert(typename, type.layout.size)

        else:
            raise Exception('Unknown class of type: {}'.format(type))

        print()

    def generate_offset_asserts(
            self, type_name, members, prefix='', offset=(0, 0)):
        for m in members:
            if isinstance(m, VariantMember):
                mprefix = prefix
                if m.name is not None:
                    mprefix += m.name + '.'
                self.generate_offset_asserts(
                    type_name, m.type.members, mprefix, offset)
            elif m.offset is not None:
                moffset = (offset[0] + m.offset[0], offset[1] + m.offset[1])
                if isinstance(m, VariantStructMember):
                    self.generate_offset_asserts(
                        type_name, m.members, prefix, moffset)
                else:
                    self.generate_offset_assert(
                        type_name, prefix + m.name, moffset)

    def generate_offset_assert(self, type_name, member_name, offset):
        offsetof = 'offsetof({}, {})'.format(type_name, member_name)
        static_assert = '_Static_assert({}, "Offset incorrect");'
        if offset[0] == offset[1]:
            print(static_assert.format('{} == {}'.format(offsetof, offset[0])))
        else:
            print(static_assert.format('sizeof(void*) != 4 || {} == {}'.format(
                offsetof, offset[0])))
            print(static_assert.format('sizeof(void*) != 8 || {} == {}'.format(
                offsetof, offset[1])))

    def generate_size_assert(self, type_name, size):
        sizeof = 'sizeof({})'.format(type_name)
        static_assert = '_Static_assert({}, "Size incorrect");'
        if size[0] == size[1]:
            print(static_assert.format('{} == {}'.format(sizeof, size[0])))
        else:
            print(static_assert.format('sizeof(void*) != 4 || {} == {}'.format(
                sizeof, size[0])))
            print(static_assert.format('sizeof(void*) != 8 || {} == {}'.format(
                sizeof, size[1])))

    def generate_syscall(self, syscall):
        print('inline static {}errno_t {}sys_{}({});'.format(
            self.prefix, self.prefix,
            syscall.name, ', '.join(self.syscall_params(syscall))))
