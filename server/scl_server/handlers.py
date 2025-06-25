import re
from lsprotocol.types import (
    CompletionItem,
    CompletionParams,
    Hover,
    HoverParams,
    MarkupContent,
    MarkupKind,
    DocumentHighlightParams,
    DocumentHighlight,
    DocumentHighlightKind,
    Range,
    Position,
    Diagnostic, 
    DiagnosticSeverity
)
from pygls.server import LanguageServer
from pygls.workspace import Document

from parser_def import parser, update_parser



def find_hover_token_with_segment(line: str, char: int) -> tuple[str, int] | None:
    if char > len(line):
        return None
    start = char
    end = char

    while start > 0 and (line[start - 1].isalnum() or line[start - 1] in '._'):
        start -= 1
    while end < len(line) and (line[end].isalnum() or line[end] in '._'):
        end += 1

    token = line[start:end]
    if not token:
        return None

    relative_pos = char - start
    segments = token.split(".")
    seg_index = 0
    offset = 0

    for i, seg in enumerate(segments):
        if offset <= relative_pos <= offset + len(seg):
            seg_index = i
            break
        offset += len(seg) + 1  # +1 for dot

    return token, seg_index

def handle_hover(ls: LanguageServer, params: HoverParams) -> Hover | None:
    doc = ls.workspace.get_document(params.text_document.uri)
    update_parser(doc)

    line = doc.lines[params.position.line]
    char = params.position.character

    token_info = find_hover_token_with_segment(line, char)
    if not token_info:
        return None

    full_token, segment_index = token_info
    path = full_token.split('.')
    target_path = path[:segment_index + 1]

    hover_data = parser.get_hover_info(target_path)
    if not hover_data:
        return None

    # Preparation of the output depending on whether it is a structure or a final variable
    if hover_data.get("children") is not None:
        type_str = "Type: STRUCT"
        comment_str = f"\nComment:\n{hover_data['comment_chain']}" if hover_data.get("comment_chain") else ""
        result = f"{type_str}{comment_str}"
    else:
        type_str = f"Type: {hover_data.get('type', '')}"
        default_str = f"\nDefault: {hover_data['default']}" if hover_data.get("default") else ""
        comment_str = f"\nComment: {hover_data['comment_chain']}" if hover_data.get("comment_chain") else ""
        result = f"{type_str}{default_str}{comment_str}"

    return Hover(contents=MarkupContent(kind=MarkupKind.PlainText, value=result))

def handle_completion(ls: LanguageServer, params: CompletionParams) -> list[CompletionItem]:
    doc = ls.workspace.get_document(params.text_document.uri)
    update_parser(doc)

    line = doc.lines[params.position.line][:params.position.character]
    match = re.search(r'([\w.]+)$', line)
    if not match:
        return []

    full_path = match.group(1)
    path_parts = full_path.split('.')
    prefix = path_parts[-1]
    path = path_parts[:-1]

    candidates = parser.get_completion_items(path) if path else parser.get_all_top_level_variables()
    filtered = [c for c in candidates if c.startswith(prefix)]
    return [CompletionItem(label=s) for s in filtered]

def handle_highlight(ls: LanguageServer, params: DocumentHighlightParams) -> list[DocumentHighlight]:
    doc = ls.workspace.get_document(params.text_document.uri)
    lines = doc.lines
    pos = params.position

    if pos.line >= len(lines):
        return []

    line = lines[pos.line]
    if pos.character >= len(line):
        return []

    char = line[pos.character]
    pairs = {'(': ')', ')': '(', '{': '}', '}': '{', '[': ']', ']': '['}
    openers = '([{'
    closers = ')]}'

    def find_match(lines, line_idx, char_idx, open_br, close_br, forward=True):
        stack = 1
        if forward:
            for l in range(line_idx, len(lines)):
                line_text = lines[l]
                r = range(char_idx + 1, len(line_text)) if l == line_idx else range(len(line_text))
                for c in r:
                    if line_text[c] == open_br:
                        stack += 1
                    elif line_text[c] == close_br:
                        stack -= 1
                        if stack == 0:
                            return Position(line=l, character=c)
        else:
            for l in range(line_idx, -1, -1):
                line_text = lines[l]
                r = range(char_idx - 1, -1, -1) if l == line_idx else range(len(line_text) - 1, -1, -1)
                for c in r:
                    if line_text[c] == close_br:
                        stack += 1
                    elif line_text[c] == open_br:
                        stack -= 1
                        if stack == 0:
                            return Position(line=l, character=c)
        return None

    if char in openers:
        match = find_match(lines, pos.line, pos.character, char, pairs[char], forward=True)
    elif char in closers:
        match = find_match(lines, pos.line, pos.character, pairs[char], char, forward=False)
    else:
        return []

    if match:
        return [
            DocumentHighlight(
                range=Range(start=pos, end=Position(line=pos.line, character=pos.character + 1)),
                kind=DocumentHighlightKind.Text,
            ),
            DocumentHighlight(
                range=Range(start=match, end=Position(line=match.line, character=match.character + 1)),
                kind=DocumentHighlightKind.Text,
            ),
        ]
    return []

