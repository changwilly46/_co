import glob
import os
import sys

KEYWORDS = {
    "class", "constructor", "function", "method", "field", "static", "var",
    "int", "char", "boolean", "void", "true", "false", "null", "this",
    "let", "do", "if", "else", "while", "return",
}

SYMBOLS = set("{}()[].,;+-*/&|<>=~")

OP_SYMBOLS = {"+", "-", "*", "/", "&", "|", "<", ">", "="}

UNARY_SYMBOLS = {"-", "~"}

BINARY_OPS = {
    "+": "add", "-": "sub", "&": "and", "|": "or",
    "=": "eq", ">": "gt", "<": "lt",
}

SEGMENTS = {
    "static": "static", "field": "this", "arg": "argument", "var": "local",
}


class JackTokenizer:
    def __init__(self, source):
        self.tokens = []
        self.index = 0
        self.tokenize(source)

    def tokenize(self, source):
        pos = 0
        size = len(source)
        while pos < size:
            char = source[pos]
            if char.isspace():
                pos += 1
            elif source.startswith("//", pos):
                end = source.find("\n", pos)
                pos = size if end == -1 else end + 1
            elif source.startswith("/*", pos):
                end = source.find("*/", pos + 2)
                pos = size if end == -1 else end + 2
            elif char == '"':
                end = source.find('"', pos + 1)
                if end == -1:
                    raise ValueError("unterminated string constant")
                self.tokens.append(("stringConstant", source[pos + 1:end]))
                pos = end + 1
            elif char in SYMBOLS:
                self.tokens.append(("symbol", char))
                pos += 1
            else:
                start = pos
                while (pos < size and not source[pos].isspace()
                       and source[pos] not in SYMBOLS and source[pos] != '"'):
                    pos += 1
                word = source[start:pos]
                if word in KEYWORDS:
                    self.tokens.append(("keyword", word))
                elif word.isdigit():
                    self.tokens.append(("integerConstant", word))
                else:
                    self.tokens.append(("identifier", word))

    def peek(self, offset=0):
        position = self.index + offset
        if position < len(self.tokens):
            return self.tokens[position]
        return (None, None)

    def advance(self):
        token = self.peek()
        self.index += 1
        return token


class SymbolTable:
    def __init__(self):
        self.class_table = {}
        self.subroutine_table = {}
        self.counts = {"static": 0, "field": 0, "arg": 0, "var": 0}

    def start_subroutine(self):
        self.subroutine_table = {}
        self.counts["arg"] = 0
        self.counts["var"] = 0

    def define(self, name, kind, var_type):
        table = self.subroutine_table if kind in ("arg", "var") else self.class_table
        table[name] = (var_type, kind, self.counts[kind])
        self.counts[kind] += 1

    def var_count(self, kind):
        return self.counts[kind]

    def kind_of(self, name):
        if name in self.subroutine_table:
            return self.subroutine_table[name][1]
        if name in self.class_table:
            return self.class_table[name][1]
        return "none"

    def type_of(self, name):
        if name in self.subroutine_table:
            return self.subroutine_table[name][0]
        if name in self.class_table:
            return self.class_table[name][0]
        raise ValueError("undefined identifier: " + name)

    def index_of(self, name):
        if name in self.subroutine_table:
            return self.subroutine_table[name][2]
        if name in self.class_table:
            return self.class_table[name][2]
        raise ValueError("undefined identifier: " + name)


class VMWriter:
    def __init__(self):
        self.lines = []

    def write_push(self, segment, index):
        self.lines.append("push %s %d" % (segment, index))

    def write_pop(self, segment, index):
        self.lines.append("pop %s %d" % (segment, index))

    def write_arithmetic(self, command):
        self.lines.append(command)

    def write_function(self, name, n_locals):
        self.lines.append("function %s %d" % (name, n_locals))

    def write_call(self, name, n_args):
        self.lines.append("call %s %d" % (name, n_args))

    def write_label(self, label):
        self.lines.append("label " + label)

    def write_goto(self, label):
        self.lines.append("goto " + label)

    def write_if(self, label):
        self.lines.append("if-goto " + label)

    def write_return(self):
        self.lines.append("return")

    def save(self, path):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(self.lines) + "\n")


class CompilationEngine:
    def __init__(self, source):
        self.tokenizer = JackTokenizer(source)
        self.symbols = SymbolTable()
        self.writer = VMWriter()
        self.class_name = ""
        self.label_count = 0

    def expect(self, kind, value=None):
        token_kind, token_value = self.tokenizer.advance()
        if token_kind != kind or (value is not None and token_value != value):
            raise ValueError("expected %s %s but found %s %s at token %d" % (
                kind, value if value is not None else "", token_kind,
                token_value, self.tokenizer.index - 1))
        return token_value

    def next_label(self, name):
        self.label_count += 1
        return "%s.%s.%d" % (self.class_name, name, self.label_count)

    def compile_class(self):
        self.expect("keyword", "class")
        self.class_name = self.expect("identifier")
        self.expect("symbol", "{")
        while self.tokenizer.peek() == ("keyword", "static") or self.tokenizer.peek() == ("keyword", "field"):
            self.compile_class_var_dec()
        while self.tokenizer.peek()[0] == "keyword" and self.tokenizer.peek()[1] in (
                "constructor", "function", "method"):
            self.compile_subroutine()
        self.expect("symbol", "}")

    def compile_type(self):
        kind, value = self.tokenizer.peek()
        if kind == "keyword" and value in ("int", "char", "boolean", "void"):
            self.tokenizer.advance()
        else:
            self.expect("identifier")
        return value

    def compile_class_var_dec(self):
        kind = self.tokenizer.advance()[1]
        var_type = self.compile_type()
        name = self.expect("identifier")
        self.symbols.define(name, kind, var_type)
        while self.tokenizer.peek() == ("symbol", ","):
            self.tokenizer.advance()
            name = self.expect("identifier")
            self.symbols.define(name, kind, var_type)
        self.expect("symbol", ";")

    def compile_parameter_list(self):
        if self.tokenizer.peek() != ("symbol", ")"):
            var_type = self.compile_type()
            name = self.expect("identifier")
            self.symbols.define(name, "arg", var_type)
            while self.tokenizer.peek() == ("symbol", ","):
                self.tokenizer.advance()
                var_type = self.compile_type()
                name = self.expect("identifier")
                self.symbols.define(name, "arg", var_type)

    def compile_var_dec(self):
        self.expect("keyword", "var")
        var_type = self.compile_type()
        name = self.expect("identifier")
        self.symbols.define(name, "var", var_type)
        while self.tokenizer.peek() == ("symbol", ","):
            self.tokenizer.advance()
            name = self.expect("identifier")
            self.symbols.define(name, "var", var_type)
        self.expect("symbol", ";")

    def compile_subroutine(self):
        subroutine_kind = self.tokenizer.advance()[1]
        self.compile_type()
        name = self.expect("identifier")
        self.symbols.start_subroutine()
        if subroutine_kind == "method":
            self.symbols.define("this", "arg", self.class_name)
        self.expect("symbol", "(")
        self.compile_parameter_list()
        self.expect("symbol", ")")
        self.expect("symbol", "{")
        while self.tokenizer.peek() == ("keyword", "var"):
            self.compile_var_dec()
        self.writer.write_function(
            "%s.%s" % (self.class_name, name), self.symbols.var_count("var"))
        if subroutine_kind == "constructor":
            self.writer.write_push("constant", self.symbols.var_count("field"))
            self.writer.write_call("Memory.alloc", 1)
            self.writer.write_pop("pointer", 0)
        elif subroutine_kind == "method":
            self.writer.write_push("argument", 0)
            self.writer.write_pop("pointer", 0)
        self.compile_statements()
        self.expect("symbol", "}")

    def compile_statements(self):
        while self.tokenizer.peek()[0] == "keyword":
            keyword = self.tokenizer.peek()[1]
            if keyword == "let":
                self.compile_let()
            elif keyword == "if":
                self.compile_if()
            elif keyword == "while":
                self.compile_while()
            elif keyword == "do":
                self.compile_do()
            elif keyword == "return":
                self.compile_return()
            else:
                break

    def write_push_variable(self, name):
        kind = self.symbols.kind_of(name)
        if kind == "none":
            raise ValueError("undefined identifier: " + name)
        self.writer.write_push(SEGMENTS[kind], self.symbols.index_of(name))

    def compile_let(self):
        self.expect("keyword", "let")
        name = self.expect("identifier")
        is_array = self.tokenizer.peek() == ("symbol", "[")
        if is_array:
            self.write_push_variable(name)
            self.tokenizer.advance()
            self.compile_expression()
            self.expect("symbol", "]")
            self.writer.write_arithmetic("add")
        self.expect("symbol", "=")
        self.compile_expression()
        self.expect("symbol", ";")
        if is_array:
            self.writer.write_pop("temp", 0)
            self.writer.write_pop("pointer", 1)
            self.writer.write_push("temp", 0)
            self.writer.write_pop("that", 0)
        else:
            kind = self.symbols.kind_of(name)
            if kind == "none":
                raise ValueError("undefined identifier: " + name)
            self.writer.write_pop(SEGMENTS[kind], self.symbols.index_of(name))

    def compile_if(self):
        else_label = self.next_label("ELSE")
        end_label = self.next_label("END_IF")
        self.expect("keyword", "if")
        self.expect("symbol", "(")
        self.compile_expression()
        self.expect("symbol", ")")
        self.writer.write_arithmetic("not")
        self.expect("symbol", "{")
        self.writer.write_if(else_label)
        self.compile_statements()
        self.expect("symbol", "}")
        self.writer.write_goto(end_label)
        self.writer.write_label(else_label)
        if self.tokenizer.peek() == ("keyword", "else"):
            self.tokenizer.advance()
            self.expect("symbol", "{")
            self.compile_statements()
            self.expect("symbol", "}")
        self.writer.write_label(end_label)

    def compile_while(self):
        start_label = self.next_label("WHILE")
        end_label = self.next_label("END_WHILE")
        self.expect("keyword", "while")
        self.writer.write_label(start_label)
        self.expect("symbol", "(")
        self.compile_expression()
        self.expect("symbol", ")")
        self.writer.write_arithmetic("not")
        self.writer.write_if(end_label)
        self.expect("symbol", "{")
        self.compile_statements()
        self.expect("symbol", "}")
        self.writer.write_goto(start_label)
        self.writer.write_label(end_label)

    def compile_do(self):
        self.expect("keyword", "do")
        name = self.expect("identifier")
        self.compile_call(name)
        self.expect("symbol", ";")
        self.writer.write_pop("temp", 0)

    def compile_call(self, name):
        if self.tokenizer.peek() == ("symbol", "."):
            self.tokenizer.advance()
            subroutine_name = self.expect("identifier")
            n_args = 0
            if self.symbols.kind_of(name) != "none":
                self.write_push_variable(name)
                n_args = 1
            target = name
        else:
            subroutine_name = name
            self.writer.write_push("pointer", 0)
            n_args = 1
            target = self.class_name
        self.expect("symbol", "(")
        n_args += self.compile_expression_list()
        self.expect("symbol", ")")
        self.writer.write_call("%s.%s" % (target, subroutine_name), n_args)

    def compile_return(self):
        self.expect("keyword", "return")
        if self.tokenizer.peek() != ("symbol", ";"):
            self.compile_expression()
        else:
            self.writer.write_push("constant", 0)
        self.writer.write_return()
        self.expect("symbol", ";")

    def compile_expression(self):
        self.compile_term()
        while self.tokenizer.peek()[0] == "symbol" and self.tokenizer.peek()[1] in OP_SYMBOLS:
            op = self.tokenizer.advance()[1]
            self.compile_term()
            if op == "*":
                self.writer.write_call("Math.multiply", 2)
            elif op == "/":
                self.writer.write_call("Math.divide", 2)
            else:
                self.writer.write_arithmetic(BINARY_OPS[op])

    def compile_term(self):
        kind, value = self.tokenizer.peek()
        if kind in ("integerConstant", "stringConstant"):
            self.tokenizer.advance()
            if kind == "integerConstant":
                self.writer.write_push("constant", int(value))
            else:
                self.writer.write_push("constant", len(value))
                self.writer.write_call("String.new", 1)
                for char in value:
                    self.writer.write_push("constant", ord(char))
                    self.writer.write_call("String.appendChar", 2)
        elif kind == "keyword":
            self.tokenizer.advance()
            if value == "true":
                self.writer.write_push("constant", 0)
                self.writer.write_arithmetic("not")
            elif value in ("false", "null"):
                self.writer.write_push("constant", 0)
            elif value == "this":
                self.writer.write_push("pointer", 0)
            else:
                raise ValueError("unexpected keyword in expression: " + value)
        elif kind == "symbol" and value in UNARY_SYMBOLS:
            self.tokenizer.advance()
            self.compile_term()
            self.writer.write_arithmetic("neg" if value == "-" else "not")
        elif self.tokenizer.peek() == ("symbol", "("):
            self.tokenizer.advance()
            self.compile_expression()
            self.expect("symbol", ")")
        elif kind == "identifier":
            name = self.tokenizer.advance()[1]
            lookahead = self.tokenizer.peek()
            if lookahead in (("symbol", "("), ("symbol", ".")):
                self.compile_call(name)
            else:
                self.write_push_variable(name)
                if self.tokenizer.peek() == ("symbol", "["):
                    self.tokenizer.advance()
                    self.compile_expression()
                    self.expect("symbol", "]")
                    self.writer.write_arithmetic("add")
                    self.writer.write_pop("pointer", 1)
                    self.writer.write_push("that", 0)
        else:
            raise ValueError("unexpected token in expression: %s %s" % (kind, value))

    def compile_expression_list(self):
        count = 0
        if self.tokenizer.peek() != ("symbol", ")"):
            self.compile_expression()
            count = 1
            while self.tokenizer.peek() == ("symbol", ","):
                self.tokenizer.advance()
                self.compile_expression()
                count += 1
        return count


def main():
    if len(sys.argv) < 2:
        print("usage: python JackCompiler.py <file.jack | directory> [more ...]")
        sys.exit(1)
    paths = []
    for argument in sys.argv[1:]:
        if os.path.isdir(argument):
            paths.extend(sorted(glob.glob(os.path.join(argument, "*.jack"))))
        elif os.path.isfile(argument) and argument.endswith(".jack"):
            paths.append(argument)
        else:
            print("path not found: " + argument)
            sys.exit(1)
    if not paths:
        print("no .jack files found")
        sys.exit(1)
    for path in paths:
        with open(path, "r", encoding="utf-8") as handle:
            engine = CompilationEngine(handle.read())
        engine.compile_class()
        output_path = os.path.splitext(path)[0] + ".vm"
        engine.writer.save(output_path)
        print("compiled -> " + output_path)


if __name__ == "__main__":
    main()
