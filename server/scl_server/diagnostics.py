import re
from lsprotocol.types import Diagnostic, DiagnosticSeverity, Range, Position
from pygls.workspace import Document
from pygls.server import LanguageServer
from parser_def import update_parser, parser


def run_diagnostics(ls: LanguageServer, doc: Document):
    update_parser(doc)
    diagnostics = []

    lines = doc.lines
    diagnostics += check_assignments(lines)
    diagnostics += check_if_blocks(lines)

    ls.publish_diagnostics(doc.uri, diagnostics)


def is_literal(value: str) -> bool:
    return re.match(r"^\d+(\.\d+)?$", value) or value.upper() in ("TRUE", "FALSE")


def is_var_defined(varname: str) -> bool:
    path = varname.split(".")
    return parser.get_hover_info(path) is not None


def extract_variables(expr: str) -> list[str]:
    return re.findall(r"[\w.]+", expr)


def check_assignments(lines: list[str]) -> list[Diagnostic]:
    diagnostics = []

    in_code_block = False
    for i, line in enumerate(lines):
        stripped = line.strip().upper()
        if stripped == "BEGIN":
            in_code_block = True
            continue
        if not in_code_block:
            continue

        code = line.split("//")[0].rstrip()
        match = re.search(r"([\w.]+)\s*:=\s*(.+)", code)
        if not match:
            continue

        lhs, rhs = match.groups()

        for var in extract_variables(lhs) + extract_variables(rhs):
            if not is_literal(var) and not is_var_defined(var):
                diagnostics.append(Diagnostic(
                    range=Range(
                        start=Position(line=i, character=line.find(var)),
                        end=Position(line=i, character=line.find(var) + len(var))
                    ),
                    message=f"Variable '{var}' is not edefined.",
                    severity=DiagnosticSeverity.Error,
                    source="scl-ls"
                ))

        if not code.endswith(";"):
            diagnostics.append(Diagnostic(
                range=Range(
                    start=Position(line=i, character=len(code)),
                    end=Position(line=i, character=len(code) + 1)
                ),
                message="Missing semicolon ';'",
                severity=DiagnosticSeverity.Error,
                source="scl-ls"
            ))

    return diagnostics


def check_if_blocks(lines: list[str]) -> list[Diagnostic]:
    diagnostics = []
    if_stack = []

    for i, line in enumerate(lines):
        upper = line.strip().upper()
        stripped_code = line.split("//")[0].strip()

        if upper.startswith("IF"):
            if_stack.append({'if': i, 'then': None, 'else': None, 'end_if': None})

        if "THEN" in upper and if_stack:
            if_stack[-1]['then'] = i

        if upper.startswith("ELSE"):
            if if_stack:
                if_stack[-1]['else'] = i
            if is_empty_else_block(lines, i):
                diagnostics.append(Diagnostic(
                    range=Range(start=Position(line=i, character=0), end=Position(line=i, character=len(line))),
                    message="Missing semicolon ';'",
                    severity=DiagnosticSeverity.Warning,
                    source="scl-ls"
                ))

        if "END_IF" in upper and if_stack:
            block = if_stack.pop()
            block['end_if'] = i
            if block['then'] is None:
                diagnostics.append(Diagnostic(
                    range=Range(
                        start=Position(line=block['if'], character=0),
                        end=Position(line=block['if'], character=len(lines[block['if']]))
                    ),
                    message="Missing THEN after IF statement.",
                    severity=DiagnosticSeverity.Error,
                    source="scl-ls"
                ))
            if not stripped_code.rstrip().endswith(";"):
                diagnostics.append(Diagnostic(
                    range=Range(
                        start=Position(line=i, character=len(stripped_code)),
                        end=Position(line=i, character=len(stripped_code) + 1)
                    ),
                    message="Missing semicolon ';'",
                    severity=DiagnosticSeverity.Error,
                    source="scl-ls"
                ))

    for block in if_stack:
        diagnostics.append(Diagnostic(
            range=Range(
                start=Position(line=block['if'], character=0),
                end=Position(line=block['if'], character=len(lines[block['if']]))
            ),
            message="END_IF missing after IF statment.",
            severity=DiagnosticSeverity.Error,
            source="scl-ls"
        ))

    return diagnostics


def is_empty_else_block(lines: list[str], start_index: int) -> bool:
    for j in range(start_index + 1, len(lines)):
        line = lines[j].split("//")[0].strip()
        if not line:
            continue
        if ";" in line:
            return False
        if line.strip().upper().startswith("END_IF"):
            return True
    return False
