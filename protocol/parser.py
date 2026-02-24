"""MMS Protocol - DSL for managing capsules, environments and pipelines.

Syntax:
    # Capsule lifecycle
    CAPSULE CREATE "api-server" runtime=python isolation=container
    CAPSULE START "api-server"
    CAPSULE STOP "api-server"
    CAPSULE DESTROY "api-server"
    CAPSULE LIST

    # Execute inside a capsule
    EXEC "api-server" "pip install fastapi"

    # Environments
    ENV CREATE "py312" runtime=python packages=fastapi,uvicorn
    ENV LIST

    # Pipelines (inline)
    PIPELINE "deploy" {
        STEP "build" capsule="builder" command="make build"
        STEP "test" capsule="tester" command="pytest"
        STEP "deploy" capsule="deployer" command="./deploy.sh"
    }

    # Write code to a capsule
    WRITE "api-server" "main.py" <<<
    from fastapi import FastAPI
    app = FastAPI()

    @app.get("/")
    def root():
        return {"status": "ok"}
    >>>
"""
import re
import logging
from dataclasses import dataclass

logger = logging.getLogger("mms.protocol")


@dataclass
class Token:
    type: str   # KEYWORD, STRING, IDENT, NUMBER, EQUALS, LBRACE, RBRACE, HEREDOC, NEWLINE
    value: str
    line: int


KEYWORDS = {
    "CAPSULE", "EXEC", "ENV", "PIPELINE", "STEP", "WRITE",
    "CREATE", "START", "STOP", "DESTROY", "LIST", "BUILD",
}


class Lexer:
    def __init__(self, source: str):
        self.tokens: list[Token] = []
        self._tokenize(source)

    def _tokenize(self, source: str):
        lines = source.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith("#"):
                i += 1
                continue

            # Heredoc: <<<\n ... \n>>>
            if "<<<" in line:
                prefix = line[:line.index("<<<")].strip()
                # Tokenize prefix
                self._tokenize_line(prefix, i + 1)
                # Collect heredoc body
                body_lines = []
                i += 1
                while i < len(lines) and lines[i].strip() != ">>>":
                    body_lines.append(lines[i])
                    i += 1
                self.tokens.append(Token("HEREDOC", "\n".join(body_lines), i))
                i += 1
                self.tokens.append(Token("NEWLINE", "\n", i))
                continue

            self._tokenize_line(line, i + 1)
            self.tokens.append(Token("NEWLINE", "\n", i + 1))
            i += 1

    def _tokenize_line(self, line: str, line_num: int):
        j = 0
        while j < len(line):
            if line[j].isspace():
                j += 1
            elif line[j] == '"':
                end = line.index('"', j + 1)
                self.tokens.append(Token("STRING", line[j+1:end], line_num))
                j = end + 1
            elif line[j] == '{':
                self.tokens.append(Token("LBRACE", "{", line_num))
                j += 1
            elif line[j] == '}':
                self.tokens.append(Token("RBRACE", "}", line_num))
                j += 1
            elif line[j] == '=':
                self.tokens.append(Token("EQUALS", "=", line_num))
                j += 1
            elif line[j].isdigit():
                m = re.match(r"\d+", line[j:])
                self.tokens.append(Token("NUMBER", m.group(), line_num))
                j += m.end()
            else:
                m = re.match(r"[a-zA-Z_][\w\-\.]*", line[j:])
                if m:
                    word = m.group()
                    t = "KEYWORD" if word.upper() in KEYWORDS else "IDENT"
                    self.tokens.append(Token(t, word, line_num))
                    j += m.end()
                else:
                    j += 1


class MMSParser:
    """Parse MMS protocol into executable instructions."""

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
                i = self._skip_line(tokens, i)
                continue

            cmd = tokens[i].value.upper()

            if cmd == "CAPSULE":
                instr, i = self._parse_capsule(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "EXEC":
                instr, i = self._parse_exec(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "ENV":
                instr, i = self._parse_env(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "PIPELINE":
                instr, i = self._parse_pipeline(tokens, i + 1)
                instructions.append(instr)
            elif cmd == "WRITE":
                instr, i = self._parse_write(tokens, i + 1)
                instructions.append(instr)
            else:
                i = self._skip_line(tokens, i)

        return instructions

    def _parse_capsule(self, tokens, i) -> tuple[dict, int]:
        sub = tokens[i].value.upper()
        i += 1

        if sub == "CREATE":
            name = self._expect(tokens, i, "STRING").value
            i += 1
            params = self._parse_kv(tokens, i)
            i = self._skip_line(tokens, i)
            return {
                "action": "capsule.create",
                "name": name,
                "runtime": params.get("runtime", "python"),
                "isolation": params.get("isolation", "container"),
                "deps": [d.strip() for d in params.get("deps", "").split(",") if d.strip()],
                "code": params.get("code"),
            }, i

        elif sub == "LIST":
            return {"action": "capsule.list"}, self._skip_line(tokens, i)

        elif sub in ("START", "STOP", "DESTROY", "BUILD"):
            target = self._expect(tokens, i, "STRING").value
            i += 1
            return {"action": f"capsule.{sub.lower()}", "target": target}, self._skip_line(tokens, i)

        return {"action": "noop"}, self._skip_line(tokens, i)

    def _parse_exec(self, tokens, i) -> tuple[dict, int]:
        target = self._expect(tokens, i, "STRING").value
        i += 1
        command = self._expect(tokens, i, "STRING").value
        i += 1
        return {"action": "capsule.exec", "target": target, "command": command}, self._skip_line(tokens, i)

    def _parse_env(self, tokens, i) -> tuple[dict, int]:
        sub = tokens[i].value.upper()
        i += 1

        if sub == "CREATE":
            name = self._expect(tokens, i, "STRING").value
            i += 1
            params = self._parse_kv(tokens, i)
            i = self._skip_line(tokens, i)
            packages = [p.strip() for p in params.get("packages", "").split(",") if p.strip()]
            return {
                "action": "env.create",
                "name": name,
                "runtime": params.get("runtime", "python"),
                "packages": packages,
            }, i

        elif sub == "LIST":
            return {"action": "env.list"}, self._skip_line(tokens, i)

        return {"action": "noop"}, self._skip_line(tokens, i)

    def _parse_pipeline(self, tokens, i) -> tuple[dict, int]:
        name = self._expect(tokens, i, "STRING").value
        i += 1
        self._expect(tokens, i, "LBRACE")
        i += 1

        steps = []
        while i < len(tokens) and tokens[i].type != "RBRACE":
            if tokens[i].type == "NEWLINE":
                i += 1
                continue
            if tokens[i].value.upper() == "STEP":
                i += 1
                step_name = self._expect(tokens, i, "STRING").value
                i += 1
                params = self._parse_kv(tokens, i)
                i = self._skip_line(tokens, i)
                steps.append({
                    "capsule": params.get("capsule", step_name),
                    "params": {"command": params.get("command", "")},
                    "depends_on": [],
                })
            else:
                i += 1

        if i < len(tokens) and tokens[i].type == "RBRACE":
            i += 1

        return {"action": "pipeline.run", "name": name, "steps": steps}, i

    def _parse_write(self, tokens, i) -> tuple[dict, int]:
        target = self._expect(tokens, i, "STRING").value
        i += 1
        filename = self._expect(tokens, i, "STRING").value
        i += 1
        code = ""
        if i < len(tokens) and tokens[i].type == "HEREDOC":
            code = tokens[i].value
            i += 1
        return {
            "action": "capsule.write",
            "target": target,
            "filename": filename,
            "code": code,
        }, self._skip_line(tokens, i)

    def _parse_kv(self, tokens, i) -> dict:
        """Parse key=value pairs until newline."""
        kv = {}
        while i < len(tokens) and tokens[i].type not in ("NEWLINE", "LBRACE", "RBRACE"):
            if tokens[i].type in ("IDENT", "KEYWORD"):
                key = tokens[i].value
                if i + 1 < len(tokens) and tokens[i + 1].type == "EQUALS":
                    i += 2
                    if i < len(tokens) and tokens[i].type in ("STRING", "IDENT", "NUMBER"):
                        kv[key] = tokens[i].value
                        i += 1
                    continue
            i += 1
        return kv

    @staticmethod
    def _expect(tokens, i, expected: str) -> Token:
        if i >= len(tokens):
            raise SyntaxError(f"Unexpected end, expected {expected}")
        if tokens[i].type != expected:
            raise SyntaxError(f"Line {tokens[i].line}: expected {expected}, got {tokens[i].type} '{tokens[i].value}'")
        return tokens[i]

    @staticmethod
    def _skip_line(tokens, i) -> int:
        while i < len(tokens) and tokens[i].type != "NEWLINE":
            i += 1
        return i + 1 if i < len(tokens) else i
