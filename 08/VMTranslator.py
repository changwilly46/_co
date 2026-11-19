import os
import sys


class Parser:
    C_ARITHMETIC = 'C_ARITHMETIC'
    C_PUSH = 'C_PUSH'
    C_POP = 'C_POP'
    C_LABEL = 'C_LABEL'
    C_GOTO = 'C_GOTO'
    C_IF = 'C_IF'
    C_FUNCTION = 'C_FUNCTION'
    C_RETURN = 'C_RETURN'
    C_CALL = 'C_CALL'

    def __init__(self, lines):
        self.commands = []
        for line in lines:
            line = line.split('//')[0].strip()
            if line:
                self.commands.append(line)
        self.index = -1
        self.current = None

    def has_more_commands(self):
        return self.index + 1 < len(self.commands)

    def advance(self):
        self.index += 1
        self.current = self.commands[self.index]

    def command_type(self):
        cmd = self.current.split()[0]
        if cmd == 'push':
            return self.C_PUSH
        if cmd == 'pop':
            return self.C_POP
        if cmd == 'label':
            return self.C_LABEL
        if cmd == 'goto':
            return self.C_GOTO
        if cmd == 'if-goto':
            return self.C_IF
        if cmd == 'function':
            return self.C_FUNCTION
        if cmd == 'return':
            return self.C_RETURN
        if cmd == 'call':
            return self.C_CALL
        return self.C_ARITHMETIC

    def arg1(self):
        parts = self.current.split()
        if self.command_type() == self.C_ARITHMETIC:
            return parts[0]
        return parts[1]

    def arg2(self):
        parts = self.current.split()
        return int(parts[2])


class CodeWriter:
    SEGMENT_MAP = {
        'local': 'LCL',
        'argument': 'ARG',
        'this': 'THIS',
        'that': 'THAT',
    }

    def __init__(self, out_file):
        self.out = out_file
        self.filename = 'Static'
        self.label_counter = 0
        self.call_counter = 0
        self.current_function = ''

    def set_file_name(self, filename):
        self.filename = os.path.splitext(os.path.basename(filename))[0]
        self.current_function = ''

    def _w(self, *lines):
        for line in lines:
            self.out.write(line + '\n')

    def _push_d(self):
        self._w('@SP', 'A=M', 'M=D', '@SP', 'M=M+1')

    def _pop_to_d(self):
        self._w('@SP', 'AM=M-1', 'D=M')

    def _new_label(self, base):
        self.label_counter += 1
        return f'{base}${self.filename}${self.label_counter}'

    def _scoped_label(self, label):
        if self.current_function:
            return f'{self.current_function}${label}'
        return label

    def write_init(self):
        self._w('@256', 'D=A', '@SP', 'M=D')
        self.write_call('Sys.init', 0)

    def write_arithmetic(self, command):
        if command == 'add':
            self._w('@SP', 'AM=M-1', 'D=M', 'A=A-1', 'M=M+D')
        elif command == 'sub':
            self._w('@SP', 'AM=M-1', 'D=M', 'A=A-1', 'M=M-D')
        elif command == 'and':
            self._w('@SP', 'AM=M-1', 'D=M', 'A=A-1', 'M=M&D')
        elif command == 'or':
            self._w('@SP', 'AM=M-1', 'D=M', 'A=A-1', 'M=M|D')
        elif command == 'neg':
            self._w('@SP', 'A=M-1', 'M=-M')
        elif command == 'not':
            self._w('@SP', 'A=M-1', 'M=!M')
        elif command in ('eq', 'gt', 'lt'):
            jump = {'eq': 'JEQ', 'gt': 'JGT', 'lt': 'JLT'}[command]
            true_label = self._new_label(command.upper() + '_TRUE')
            end_label = self._new_label(command.upper() + '_END')
            self._w(
                '@SP', 'AM=M-1', 'D=M', 'A=A-1', 'D=M-D',
                f'@{true_label}', f'D;{jump}',
                '@SP', 'A=M-1', 'M=0',
                f'@{end_label}', '0;JMP',
                f'({true_label})',
                '@SP', 'A=M-1', 'M=-1',
                f'({end_label})'
            )
        else:
            raise ValueError(f'Unknown arithmetic command: {command}')

    def write_push_pop(self, command_type, segment, index):
        if command_type == Parser.C_PUSH:
            self._write_push(segment, index)
        else:
            self._write_pop(segment, index)

    def _write_push(self, segment, index):
        if segment == 'constant':
            self._w(f'@{index}', 'D=A')
            self._push_d()
        elif segment in self.SEGMENT_MAP:
            base = self.SEGMENT_MAP[segment]
            self._w(f'@{base}', 'D=M', f'@{index}', 'A=D+A', 'D=M')
            self._push_d()
        elif segment == 'temp':
            addr = 5 + index
            self._w(f'@{addr}', 'D=M')
            self._push_d()
        elif segment == 'pointer':
            reg = 'THIS' if index == 0 else 'THAT'
            self._w(f'@{reg}', 'D=M')
            self._push_d()
        elif segment == 'static':
            self._w(f'@{self.filename}.{index}', 'D=M')
            self._push_d()
        else:
            raise ValueError(f'Unknown segment: {segment}')

    def _write_pop(self, segment, index):
        if segment in self.SEGMENT_MAP:
            base = self.SEGMENT_MAP[segment]
            self._w(f'@{base}', 'D=M', f'@{index}', 'D=D+A', '@R13', 'M=D')
            self._pop_to_d()
            self._w('@R13', 'A=M', 'M=D')
        elif segment == 'temp':
            addr = 5 + index
            self._pop_to_d()
            self._w(f'@{addr}', 'M=D')
        elif segment == 'pointer':
            reg = 'THIS' if index == 0 else 'THAT'
            self._pop_to_d()
            self._w(f'@{reg}', 'M=D')
        elif segment == 'static':
            self._pop_to_d()
            self._w(f'@{self.filename}.{index}', 'M=D')
        else:
            raise ValueError(f'Unknown segment: {segment}')

    def write_label(self, label):
        self._w(f'({self._scoped_label(label)})')

    def write_goto(self, label):
        self._w(f'@{self._scoped_label(label)}', '0;JMP')

    def write_if(self, label):
        self._pop_to_d()
        self._w(f'@{self._scoped_label(label)}', 'D;JNE')

    def write_function(self, function_name, num_locals):
        self.current_function = function_name
        self._w(f'({function_name})')
        for _ in range(num_locals):
            self._w('@0', 'D=A')
            self._push_d()

    def write_call(self, function_name, num_args):
        self.call_counter += 1
        return_label = f'RET${function_name}${self.call_counter}'
        # push return address
        self._w(f'@{return_label}', 'D=A')
        self._push_d()
        # push LCL, ARG, THIS, THAT
        for seg in ('LCL', 'ARG', 'THIS', 'THAT'):
            self._w(f'@{seg}', 'D=M')
            self._push_d()
        # ARG = SP - 5 - num_args
        offset = 5 + num_args
        self._w('@SP', 'D=M', f'@{offset}', 'D=D-A', '@ARG', 'M=D')
        # LCL = SP
        self._w('@SP', 'D=M', '@LCL', 'M=D')
        # goto function
        self._w(f'@{function_name}', '0;JMP')
        # return label
        self._w(f'({return_label})')

    def write_return(self):
        # FRAME = LCL (R13)
        self._w('@LCL', 'D=M', '@R13', 'M=D')
        # RET = *(FRAME-5) (R14)
        self._w('@5', 'A=D-A', 'D=M', '@R14', 'M=D')
        # *ARG = pop()
        self._pop_to_d()
        self._w('@ARG', 'A=M', 'M=D')
        # SP = ARG + 1
        self._w('@ARG', 'D=M+1', '@SP', 'M=D')
        # restore THAT, THIS, ARG, LCL
        for seg in ('THAT', 'THIS', 'ARG', 'LCL'):
            self._w('@R13', 'AM=M-1', 'D=M', f'@{seg}', 'M=D')
        # goto RET
        self._w('@R14', 'A=M', '0;JMP')


def translate_file(vm_path, code_writer):
    code_writer.set_file_name(vm_path)
    with open(vm_path, 'r', encoding='utf-8') as f:
        parser = Parser(f.readlines())
    while parser.has_more_commands():
        parser.advance()
        ctype = parser.command_type()
        if ctype == Parser.C_ARITHMETIC:
            code_writer.write_arithmetic(parser.arg1())
        elif ctype in (Parser.C_PUSH, Parser.C_POP):
            code_writer.write_push_pop(ctype, parser.arg1(), parser.arg2())
        elif ctype == Parser.C_LABEL:
            code_writer.write_label(parser.arg1())
        elif ctype == Parser.C_GOTO:
            code_writer.write_goto(parser.arg1())
        elif ctype == Parser.C_IF:
            code_writer.write_if(parser.arg1())
        elif ctype == Parser.C_FUNCTION:
            code_writer.write_function(parser.arg1(), parser.arg2())
        elif ctype == Parser.C_CALL:
            code_writer.write_call(parser.arg1(), parser.arg2())
        elif ctype == Parser.C_RETURN:
            code_writer.write_return()


def translate(path):
    if os.path.isdir(path):
        vm_files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.vm')]
        if not vm_files:
            raise SystemExit('No .vm files found in directory')
        vm_files.sort()
        out_path = os.path.join(path, os.path.basename(os.path.normpath(path)) + '.asm')
        write_bootstrap = len(vm_files) > 1
    else:
        if not path.endswith('.vm'):
            raise SystemExit('Input must be a .vm file or a directory')
        vm_files = [path]
        out_path = path[:-3] + '.asm'
        write_bootstrap = False

    with open(out_path, 'w', encoding='utf-8', newline='\n') as out:
        writer = CodeWriter(out)
        if write_bootstrap:
            writer.write_init()
        for vm_file in vm_files:
            translate_file(vm_file, writer)
    return out_path


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: VMTranslator.py <file.vm|directory>')
        sys.exit(1)
    out = translate(sys.argv[1])
    print(out)
