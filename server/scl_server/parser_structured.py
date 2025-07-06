import re
from collections import defaultdict

VAR_BLOCKS = {
    "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR", "VAR_TEMP", "CONST",
}

class VariableNode:
    def __init__(self, name, var_type, data_type, parent=None, default=None, comment=None, block_type=None):
        self.name = name
        self.var_type = var_type  # input, output, inout, static, temp, normal
        self.data_type = data_type  # INT, BOOL, STRUCT, etc.
        self.parent = parent  # parent VariableNode or None
        self.children = {}  # name -> VariableNode
        self.default = default
        self.comment = comment
        self.block_type = block_type  # VAR_INPUT, VAR_OUTPUT, etc.

    def add_child(self, child):
        self.children[child.name] = child

    def to_dict(self):
        return {
            "name": self.name,
            "var_type": self.var_type,
            "data_type": self.data_type,
            "parent": self.parent.name if self.parent else None,
            "children": list(self.children.keys()),
            "default": self.default,
            "comment": self.comment,
            "block_type": self.block_type,
        }

class StructuredSCLParser:
    def __init__(self):
        self.variables = {}  # name -> VariableNode
        self.all_nodes = {}  # all VariableNodes by full path

    def parse(self, text: str):
        self.variables = {}
        self.all_nodes = {}
        lines = text.splitlines()
        block_type = None
        parent_stack = []
        current_parent = None

        for line in lines:
            stripped = line.strip()
            upper = stripped.upper()

            # Detect block start
            if upper in VAR_BLOCKS:
                block_type = upper
                continue
            if upper.startswith("END_VAR") or upper.startswith("END_CONST"):
                block_type = None
                continue

            # Structure start
            struct_match = re.match(r"(?i)(\w+)\s*:\s*STRUCT\b", stripped)
            if struct_match and block_type:
                name = struct_match.group(1)
                node = VariableNode(
                    name=name,
                    var_type=self._block_to_vartype(block_type),
                    data_type="STRUCT",
                    parent=current_parent,
                    comment=self._extract_comment(stripped),
                    block_type=block_type
                )
                if current_parent:
                    current_parent.add_child(node)
                else:
                    self.variables[name] = node
                self.all_nodes[self._full_path(parent_stack, name)] = node
                parent_stack.append(name)
                current_parent = node
                continue

            # Structure end
            if re.match(r"(?i)END_STRUCT\s*;", stripped):
                if parent_stack:
                    parent_stack.pop()
                    current_parent = self._get_parent_node(parent_stack)
                continue

            # Variable declaration
            var_match = re.match(r"(?i)(\w+)\s*:\s*([\w.]+)(?:\s*:=\s*([^;]+))?\s*;", stripped)
            if var_match and block_type:
                name, data_type, default = var_match.groups()
                node = VariableNode(
                    name=name,
                    var_type=self._block_to_vartype(block_type),
                    data_type=data_type,
                    parent=current_parent,
                    default=default.strip() if default else None,
                    comment=self._extract_comment(stripped),
                    block_type=block_type
                )
                if current_parent:
                    current_parent.add_child(node)
                else:
                    self.variables[name] = node
                self.all_nodes[self._full_path(parent_stack, name)] = node

        # Optionally: flatten children for easier lookup
        # self._flatten_children(self.variables)

    def _block_to_vartype(self, block_type):
        if block_type == "VAR_INPUT":
            return "input"
        if block_type == "VAR_OUTPUT":
            return "output"
        if block_type == "VAR_IN_OUT":
            return "inout"
        if block_type == "VAR_STATIC":
            return "static"
        if block_type == "VAR_TEMP":
            return "temporary"
        if block_type == "CONST":
            return "constant"
        return "normal"

    def _full_path(self, parent_stack, name):
        return ".".join(parent_stack + [name]) if parent_stack else name

    def _get_parent_node(self, parent_stack):
        if not parent_stack:
            return None
        path = ".".join(parent_stack)
        return self.all_nodes.get(path)

    def _extract_comment(self, line: str) -> str:
        comment_index = line.find("//")
        if comment_index != -1:
            return line[comment_index + 2:].strip()
        return ""

    def get_variable(self, name: str) -> dict | None:
        node = self.all_nodes.get(name)
        return node.to_dict() if node else None

    def get_all_variables(self):
        return {name: node.to_dict() for name, node in self.all_nodes.items()}

    def get_children(self, name: str):
        node = self.all_nodes.get(name)
        if node:
            return [child.to_dict() for child in node.children.values()]
        return []

# Example usage:
# parser = StructuredSCLParser()
# parser.parse(scl_code)
# print(parser.get_all_variables())
