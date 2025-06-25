import re
from collections import defaultdict

class SCLParser:
    def __init__(self):
        self.variables = {}

    def parse(self, text: str):
        self.variables = {}

        lines = text.splitlines()
        stack = []
        current = self.variables

        for line in lines:
            stripped = line.strip()

            # Beginning of the structure
            struct_match = re.match(r"(?i)(\w+)\s*:\s*STRUCT\b", stripped)
            if struct_match:
                name = struct_match.group(1)
                node = {
                    "type": "STRUCT",
                    "comment": self._extract_comment(stripped),
                    "children": {}
                }
                current[name] = node
                stack.append((current, name))
                current = node["children"]
                continue

            # End of the structure
            if re.match(r"(?i)END_STRUCT\s*;", stripped):
                if stack:
                    current, _ = stack.pop()
                continue

            # Variable or part of the structure
            var_match = re.match(r"(?i)(\w+)\s*:\s*(\w+)(?:\s*:=\s*([^;]+))?\s*;", stripped)
            if var_match:
                name, var_type, default = var_match.groups()
                current[name] = {
                    "type": var_type,
                    "default": default.strip() if default else None,
                    "comment": self._extract_comment(stripped),
                }

    def get_completion_items(self, path: list[str]) -> list[str]:
        node = self._resolve_path(path)
        if isinstance(node, dict) and "children" in node:
            return list(node["children"].keys())
        return []

    def get_all_top_level_variables(self) -> list[str]:
        return list(self.variables.keys())

    def resolve_variable_path(self, path: list[str]):

        current = self.variables
        for i, key in enumerate(path):
            if not isinstance(current, dict) or key not in current:
                return None
            current = current[key]
            if i < len(path) - 1:
                if "children" in current:
                    current = current["children"]
                else:
                    return None
        return current

    def get_hover_info(self, path: list[str]) -> dict | None:

        final_node = self.resolve_variable_path(path)
        if final_node is None:
            return None

        # Set up of comment chain
        comment_chain = []
        current = self.variables
        for key in path:
            if key not in current:
                break
            node = current[key]
            comment = node.get("comment", "")
            if comment:
                comment_chain.append(comment)
            if "children" in node:
                current = node["children"]
            else:
                break

        hover_data = {
            "comment_chain": ", ".join(comment_chain),
            "children": list(final_node.get("children", {}).keys()) if "children" in final_node else None,
            "type": final_node.get("type", ""),
            "default": final_node.get("default", ""),
        }
        return hover_data


    def _resolve_path(self, path: list[str]):
        current = self.variables
        for i, key in enumerate(path):
            if not isinstance(current, dict):
                return None
            if key not in current:
                return None
            current = current[key]
            if i < len(path) - 1:
                if "children" in current:
                    current = current["children"]
                else:
                    return None
        return current

    def _extract_comment(self, line: str) -> str:
        comment_index = line.find("//")
        if comment_index != -1:
            return line[comment_index + 2:].strip()
        return ""

parser = SCLParser()

def update_parser(doc):
    parser.parse(doc.source)