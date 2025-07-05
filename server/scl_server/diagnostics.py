import re
from lsprotocol.types import Diagnostic, DiagnosticSeverity, Range, Position
from pygls.workspace import Document
from pygls.server import LanguageServer
from parser_def import update_parser, parser
from syntax_keywords import SCL_KEYWORDS


def run_diagnostics(ls: LanguageServer, doc: Document):
    update_parser(doc)
    diagnostics = []

    lines = doc.lines
    declared_vars = set(parser.get_all_top_level_variables())
    diagnostics += check_assignments(lines, declared_vars)
    diagnostics += check_if_blocks(lines)
    diagnostics += check_variable_prefix_collisions(lines)

    ls.publish_diagnostics(doc.uri, diagnostics)


def is_literal(value: str) -> bool:
    # Exclude time constants starting with T# and SCL keywords
    return (
        re.match(r"^\d+(\.\d+)?$", value)
        or value.upper() in SCL_KEYWORDS
        or value.upper().startswith("T#")
    )


def is_var_defined(varname: str) -> bool:
    path = varname.split(".")
    return parser.get_hover_info(path) is not None


def preprocess_function_block_info(lines: list[str]):
    """Precompute function block names and all function call argument names."""
    fb_names = set()
    in_var_block = False
    var_decl_pattern = re.compile(r"^\s*([\w.]+)\s*:\s*([\w.]+)\s*;")
    call_pattern = re.compile(r"\b([\w.]+)\s*\(([^)]*)\)")
    fb_arg_names = set()
    for line in lines:
        upper = line.strip().upper()
        if upper.startswith("VAR"):
            in_var_block = True
            continue
        if upper.startswith("END_VAR"):
            in_var_block = False
            continue
        if in_var_block:
            match = var_decl_pattern.match(line.split("//")[0])
            if match:
                var_name, var_type = match.groups()
                if var_type.upper() not in SCL_KEYWORDS:
                    fb_names.add(var_name)
        # Function call argument names (IN, PT, etc.)
        for call_match in call_pattern.finditer(line):
            arglist = call_match.group(2)
            for arg in arglist.split(","):
                arg = arg.strip()
                if ":=" in arg:
                    arg_name = arg.split(":=")[0].strip()
                    fb_arg_names.add(arg_name)
    return fb_names, fb_arg_names


def extract_variables(text: str) -> list[str]:
    # Remove T# time literals and numbers
    text = re.sub(r"\bT#\w+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+(\.\d+)?\b", "", text)
    # Extract variable-like tokens, skip time literals and numbers
    return re.findall(r"[\w.]+", text)


def check_variable_length_and_prefix(var: str, i: int, line: str, prefix_map: dict, scope: tuple) -> list[Diagnostic]:
    """Return diagnostics for variable name length and prefix collisions in the given scope."""
    diagnostics = []
    if len(var) > 24:
        diagnostics.append(Diagnostic(
            range=Range(
                start=Position(line=i, character=line.find(var)),
                end=Position(line=i, character=line.find(var) + len(var))
            ),
            message=f"Variable '{var}' is longer than 24 characters.",
            severity=DiagnosticSeverity.Information,
            source="scl-ls"
        ))
    prefix = var[:24]
    if scope not in prefix_map:
        prefix_map[scope] = {}
    if prefix in prefix_map[scope]:
        prev_i, prev_var = prefix_map[scope][prefix]
        diagnostics.append(Diagnostic(
            range=Range(
                start=Position(line=i, character=line.find(var)),
                end=Position(line=i, character=line.find(var) + len(var))
            ),
            message=f"Variable '{var}' has the same first 24 characters as '{prev_var}' (line {prev_i+1}) in the same scope.",
            severity=DiagnosticSeverity.Error,
            source="scl-ls"
        ))
    else:
        prefix_map[scope][prefix] = (i, var)
    return diagnostics


def check_variable_prefix_collisions(lines: list[str]) -> list[Diagnostic]:
    """
    Return diagnostics if two variables have the same first 24 characters or are too long.
    The check is done per scope: global for top-level, or per structure for nested variables.
    """
    diagnostics = []
    prefix_map = {}
    struct_stack = []
    # Regex for structure and variable declarations
    struct_start_pattern = re.compile(r"(?i)^\s*(\w+)\s*:\s*STRUCT\b")
    struct_end_pattern = re.compile(r"(?i)^\s*END_STRUCT\s*;")
    var_decl_pattern = re.compile(r"(?i)^\s*([\w.]+)\s*:\s*[\w.]+\s*(?::=|:=)?")
    for i, line in enumerate(lines):
        code = line.split("//")[0].strip()
        # Check for structure start
        struct_start = struct_start_pattern.match(code)
        if struct_start:
            struct_stack.append(struct_start.group(1))
            continue
        # Check for structure end
        if struct_end_pattern.match(code):
            if struct_stack:
                struct_stack.pop()
            continue
        # Check for variable declaration
        match = var_decl_pattern.match(code)
        if match:
            var_name = match.group(1).strip()
            # Scope is tuple of structure stack, or empty tuple for global
            scope = tuple(struct_stack)
            diagnostics += check_variable_length_and_prefix(var_name, i, line, prefix_map, scope)
    return diagnostics


def check_assignments(lines: list[str], declared_vars: set[str]) -> list[Diagnostic]:
    diagnostics = []
    fb_names, fb_arg_names = preprocess_function_block_info(lines)
    in_code_block = False
    logical_ops = ("AND", "OR", "XOR", "NOT")
    # Join all code lines into a single string for multiline context
    multiline_code = "\n".join(line.split("//")[0].rstrip() for line in lines)
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
            if (
                not is_literal(var)
                and not is_var_defined(var)
                and var not in declared_vars
                and var not in fb_names
                and not any(var.startswith(fb + ".") for fb in fb_names)
                and var not in fb_arg_names
            ):
                diagnostics.append(Diagnostic(
                    range=Range(
                        start=Position(line=i, character=line.find(var)),
                        end=Position(line=i, character=line.find(var) + len(var))
                    ),
                    message=f"Variable '{var}' is not defined.",
                    severity=DiagnosticSeverity.Warning,
                    source="scl-ls"
                ))

        # Check for missing semicolon, but allow line continuation with logical operators
        # For function calls, require semicolon only after the closing parenthesis of the call
        if not code.endswith(";"):
            # Check if we are inside an unclosed parenthesis (e.g., multiline function call)
            open_parens = 0
            for ch in code:
                if ch == "(":
                    open_parens += 1
                elif ch == ")":
                    open_parens -= 1
            # Look ahead for closing parenthesis and semicolon
            if open_parens > 0:
                # Scan following lines to find the closing parenthesis and check for semicolon
                found_close = False
                for k in range(i + 1, len(lines)):
                    next_line = lines[k].split("//")[0].rstrip()
                    for ch in next_line:
                        if ch == "(":
                            open_parens += 1
                        elif ch == ")":
                            open_parens -= 1
                    if open_parens <= 0:
                        found_close = True
                        # After closing parenthesis, require semicolon at end of line
                        if not next_line.rstrip().endswith(";"):
                            diagnostics.append(Diagnostic(
                                range=Range(
                                    start=Position(line=k, character=len(next_line)),
                                    end=Position(line=k, character=len(next_line) + 1)
                                ),
                                message="Missing semicolon ';' after function call.",
                                severity=DiagnosticSeverity.Error,
                                source="scl-ls"
                            ))
                        break
                # If never closed, do not report semicolon error here
                continue
            # Otherwise, check for logical operator continuation as before
            continuation_found = False
            for k in range(i + 1, len(lines)):
                next_line = lines[k].split("//")[0]
                if not next_line.strip():
                    continue  # skip empty/comment lines
                tokens = next_line.lstrip().split()
                if tokens and tokens[0].upper() in logical_ops:
                    continuation_found = True
                    break
                if len(tokens) > 1 and tokens[1].upper() in logical_ops:
                    continuation_found = True
                    break
                break  # only check the first non-empty line after current
            if not continuation_found:
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
