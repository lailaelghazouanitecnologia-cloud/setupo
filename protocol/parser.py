"""Setupo Protocol - Custom DSL for orchestrating VMs and MicroVMs.

Syntax:
    CREATE microvm "worker-1" vcpus=2 memory=512
    CREATE vm "database" vcpus=4 memory=2048 disk=8192
    EXEC "worker-1" run "apt update && apt install -y nginx"
    CAPSULE "worker-1" load "nginx-proxy"
    DESTROY "worker-1"
    LIST microvms
    LIST vms
    CONNECT "worker-1" -> "worker-2" port=8080
    SSH "user@external-host" run "uptime"
    PIPE "worker-1" exec "cat /data" -> "worker-2" exec "tee /import"

Lines starting with # are comments. Commands are newline-separated.
Strings are quoted with double quotes.
"""
import re
import logging
from dataclasses import dataclass

logger = logging.getLogger("setupo.protocol")


@dataclass
class Token:
    type: str  # KEYWORD, STRING, NUMBER, IDENT, ARROW, EQUALS, NEWLINE
    value: str
    line: int


class Lexer:
    """Tokenize setupo protocol source code."""

    KEYWORDS = {
        "CREATE", "EXEC", "DESTROY", "LIST", "CAPSULE",
        "CONNECT", "SSH", "PIPE", "STOP", "START", "INFO",
    }

    def __init__(self, source: str):
        self.source = source
        self.tokens: list[Token] = []
        self._tokenize()

    def _tokenize(self):
        for line_num, line in enumerate(self.source.split("\n"), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            i = 0
            while i < len(line):
                if line[i].isspace():
                    i += 1
                elif line[i] == '"':
                    end = line.index('"', i + 1)
                    self.tokens.append(Token("STRING", line[i+1:end], line_num))
                    i = end + 1
                elif line[i:i+2] == "->":
                    self.tokens.append(Token("ARROW", "->", line_num))
                    i += 2
                elif line[i] == "=":
                    self.tokens.append(Token("EQUALS", "=", line_num))
                    i += 1
                elif line[i].isdigit():
                    m = re.match(r"\d+", line[i:])
                    self.tokens.append(Token("NUMBER", m.group(), line_num))
                    i += m.end()
                else:
                    m = re.match(r"[a-zA-Z_][\w\-]*", line[i:])
                    if m:
                        word = m.group()
                        t = "KEYWORD" if word.upper() in self.KEYWORDS else "IDENT"
                        self.tokens.append(Token(t, word, line_num))
                        i += m.end()
                    else:
                        i += 1
            self.tokens.append(Token("NEWLINE", "\n", line_num))


class SetupoParser:
    """Parse setupo protocol tokens into executable instructions."""

    def parse(self, source: str) -> list[dict]:
        lexer = Lexer(source)
        tokens = lexer.tokens
        instructions = []
        i = 0

        while i < len(tokens):
            if tokens[i].type == "NEWLINE":
                i += 1
                continue

            if tokens[i].type != "KEYWORD":
                logger.warning("Unexpected token at line %d: %s", tokens[i].line, tokens[i].value)
                i = self._skip_to_newline(tokens, i)
                continue

            cmd = tokens[i].value.upper()

            if cmd == "CREATE":
                instr, i = self._parse_create(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "EXEC":
                instr, i = self._parse_exec(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "DESTROY":
                instr, i = self._parse_destroy(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "STOP":
                instr, i = self._parse_simple(tokens, i + 1, "stop")
                instructions.append(instr)
            elif cmd == "START":
                instr, i = self._parse_simple(tokens, i + 1, "start")
                instructions.append(instr)
            elif cmd == "LIST":
                instr, i = self._parse_list(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "CAPSULE":
                instr, i = self._parse_capsule(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "CONNECT":
                instr, i = self._parse_connect(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "SSH":
                instr, i = self._parse_ssh(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "PIPE":
                instr, i = self._parse_pipe(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "INFO":
                instr, i = self._parse_simple(tokens, i + 1, "info")
                instructions.append(instr)
            else:
                i = self._skip_to_newline(tokens, i)

        return instructions

    def _parse_create(self, tokens, i) -> tuple[dict, int]:
        vm_type = self._expect(tokens, i, "IDENT").value  # microvm or vm
        i += 1
        name = self._expect(tokens, i, "STRING").value
        i += 1
        params = {}
        while i < len(tokens) and tokens[i].type != "NEWLINE":
            key = tokens[i].value
            i += 1
            if i < len(tokens) and tokens[i].type == "EQUALS":
                i += 1
                params[key] = int(tokens[i].value) if tokens[i].type == "NUMBER" else tokens[i].value
                i += 1
            else:
                params[key] = True
        return {"action": "create", "type": vm_type, "name": name, "params": params}, i

    def _parse_exec(self, tokens, i) -> tuple[dict, int]:
        target = self._expect(tokens, i, "STRING").value
        i += 1
        # Skip optional "run" keyword
        if i < len(tokens) and tokens[i].type == "IDENT" and tokens[i].value == "run":
            i += 1
        command = self._expect(tokens, i, "STRING").value
        i += 1
        return {"action": "exec", "target": target, "command": command}, i

    def _parse_destroy(self, tokens, i) -> tuple[dict, int]:
        target = self._expect(tokens, i, "STRING").value
        i += 1
        return {"action": "destroy", "target": target}, i

    def _parse_simple(self, tokens, i, action: str) -> tuple[dict, int]:
        target = self._expect(tokens, i, "STRING").value
        i += 1
        return {"action": action, "target": target}, i

    def _parse_list(self, tokens, i) -> tuple[dict, int]:
        what = "all"
        if i < len(tokens) and tokens[i].type == "IDENT":
            what = tokens[i].value
            i += 1
        return {"action": "list", "type": what}, i

    def _parse_capsule(self, tokens, i) -> tuple[dict, int]:
        target = self._expect(tokens, i, "STRING").value
        i += 1
        # Skip "load" keyword
        if i < len(tokens) and tokens[i].type == "IDENT" and tokens[i].value == "load":
            i += 1
        name = self._expect(tokens, i, "STRING").value
        i += 1
        return {"action": "capsule", "target": target, "name": name}, i

    def _parse_connect(self, tokens, i) -> tuple[dict, int]:
        source = self._expect(tokens, i, "STRING").value
        i += 1
        self._expect(tokens, i, "ARROW")
        i += 1
        dest = self._expect(tokens, i, "STRING").value
        i += 1
        params = {}
        while i < len(tokens) and tokens[i].type != "NEWLINE":
            key = tokens[i].value
            i += 1
            if i < len(tokens) and tokens[i].type == "EQUALS":
                i += 1
                params[key] = int(tokens[i].value) if tokens[i].type == "NUMBER" else tokens[i].value
                i += 1
        return {"action": "connect", "source": source, "dest": dest, "params": params}, i

    def _parse_ssh(self, tokens, i) -> tuple[dict, int]:
        host = self._expect(tokens, i, "STRING").value
        i += 1
        if i < len(tokens) and tokens[i].type == "IDENT" and tokens[i].value == "run":
            i += 1
        command = self._expect(tokens, i, "STRING").value
        i += 1
        return {"action": "ssh", "host": host, "command": command}, i

    def _parse_pipe(self, tokens, i) -> tuple[dict, int]:
        source = self._expect(tokens, i, "STRING").value
        i += 1
        if i < len(tokens) and tokens[i].type == "IDENT" and tokens[i].value == "exec":
            i += 1
        src_cmd = self._expect(tokens, i, "STRING").value
        i += 1
        self._expect(tokens, i, "ARROW")
        i += 1
        dest = self._expect(tokens, i, "STRING").value
        i += 1
        if i < len(tokens) and tokens[i].type == "IDENT" and tokens[i].value == "exec":
            i += 1
        dst_cmd = self._expect(tokens, i, "STRING").value
        i += 1
        return {
            "action": "pipe",
            "source": source, "source_cmd": src_cmd,
            "dest": dest, "dest_cmd": dst_cmd,
        }, i

    @staticmethod
    def _expect(tokens, i, expected_type: str) -> Token:
        if i >= len(tokens):
            raise SyntaxError(f"Unexpected end of input, expected {expected_type}")
        if tokens[i].type != expected_type:
            raise SyntaxError(
                f"Line {tokens[i].line}: expected {expected_type}, got {tokens[i].type} ({tokens[i].value!r})"
            )
        return tokens[i]

    @staticmethod
    def _skip_to_newline(tokens, i) -> int:
        while i < len(tokens) and tokens[i].type != "NEWLINE":
            i += 1
        return i + 1
