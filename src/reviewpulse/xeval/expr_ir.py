"""Rules written as one readable expression, parsed by our own code into the interpreter's `Program`.

A small model is better at writing

    forall rooms r where r.room_type == 'bedroom': r.area_m2 >= 9 m2 and r.min_width_m >= 2.2 m

than at linking a table of node ids (it dropped or invented ids in most failed drafts). Here nothing can dangle,
cm / mm / % are converted by the parser, and the same text is the plain-language readback for the reviewer.

Grammar (lowest to highest precedence)
    expr    := and_e ('or' and_e)*
    and_e   := not_e ('and' not_e)*
    not_e   := 'not' not_e | cmp
    cmp     := add (('>=' | '<=' | '>' | '<' | '==' | '!=') add)?
    add     := mul (('+' | '-') mul)*
    mul     := atom (('*' | '/') atom)*
    atom    := NUMBER [unit] | STRING | 'true' | 'false' | '(' expr ')' | quantifier | aggregate | IDENT '.' IDENT
    quantifier := ('forall' | 'exists') IDENT IDENT ['where' expr] ':' expr
    aggregate  := 'count' '(' IDENT IDENT ['where' expr] ')'
                | ('sum' | 'min' | 'max') '(' IDENT IDENT ['where' expr] ':' expr ')'
units: m, cm, mm, m2, %   (a bare number takes the unit of what it is compared with)
"""

from __future__ import annotations

import re

from ..interpreter.schema import Binding

KEYWORDS = {"forall", "exists", "count", "sum", "min", "max", "where", "and", "or", "not", "true", "false",
            "reaches", "through"}
TOKEN = re.compile(r"""\s*(?:
    (?P<num>\d+(?:\.\d+)?)(?:\s?(?P<unit>m2|m²|cm|mm|m|%)(?![A-Za-z0-9_]))?
  | (?P<str>'[^']*'|"[^"]*")
  | (?P<op>>=|<=|==|!=|>|<|\+|-|\*|/|\(|\)|:|,|\.)
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
)""", re.X)
UNIT_FACTOR = {"m": ("m", 1.0), "cm": ("m", 0.01), "mm": ("m", 0.001), "m2": ("m2", 1.0), "m²": ("m2", 1.0),
               "%": ("1", 0.01)}
COMPARE = {">=": "ge", "<=": "le", ">": "gt", "<": "lt", "==": "eq", "!=": "ne"}


class ExprError(ValueError):
    pass


def tokenize(text: str) -> list[tuple[str, str, str | None]]:
    out, pos = [], 0
    text = text.strip()
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise ExprError(f"cannot read the expression at: {text[pos:pos + 25]!r}")
        pos = m.end()
        for kind in ("num", "str", "op", "id"):
            if m.group(kind) is not None:
                out.append((kind, m.group(kind), m.group("unit") if kind == "num" else None))
                break
    return out


class Parser:
    def __init__(self, text: str, entities: set[str]):
        self.toks = tokenize(text)
        self.i = 0
        self.vars: list[str] = []
        self.entities = entities           # global entities facts may hang on (e.g. building)
        self.alias: dict[str, str] = {}    # the variable of a `through` filter reads the node being passed

    # -- helpers
    def peek(self, offset: int = 0):
        j = self.i + offset
        return self.toks[j] if j < len(self.toks) else (None, None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def accept(self, value: str) -> bool:
        if self.peek()[1] == value:
            self.i += 1
            return True
        return False

    def expect(self, value: str):
        if not self.accept(value):
            raise ExprError(f"expected '{value}' but found '{self.peek()[1]}'")

    def ident(self, what: str) -> str:
        kind, value, _ = self.take()
        if kind != "id" or value in KEYWORDS:
            raise ExprError(f"expected {what} but found '{value}'")
        return value

    # -- grammar
    def parse(self) -> dict:
        node = self.expr()
        if self.i != len(self.toks):
            raise ExprError(f"unexpected '{self.peek()[1]}' after a complete expression")
        return node

    def expr(self) -> dict:
        args = [self.and_e()]
        while self.accept("or"):
            args.append(self.and_e())
        return args[0] if len(args) == 1 else {"node": "any", "args": args}

    def and_e(self) -> dict:
        args = [self.not_e()]
        while self.accept("and"):
            args.append(self.not_e())
        return args[0] if len(args) == 1 else {"node": "all", "args": args}

    def not_e(self) -> dict:
        if self.accept("not"):
            return {"node": "not", "args": [self.not_e()]}
        return self.cmp()

    def cmp(self) -> dict:
        left = self.add()
        op = self.peek()[1]
        if self.peek()[0] == "op" and op in COMPARE:
            self.i += 1
            return {"node": COMPARE[op], "left": left, "right": self.add()}
        return left

    def add(self) -> dict:
        left = self.mul()
        while self.peek()[1] in ("+", "-") and self.peek()[0] == "op":
            op = self.take()[1]
            left = {"node": "add" if op == "+" else "sub", "left": left, "right": self.mul()}
        return left

    def mul(self) -> dict:
        left = self.atom()
        while self.peek()[1] in ("*", "/") and self.peek()[0] == "op":
            op = self.take()[1]
            left = {"node": "mul" if op == "*" else "div", "left": left, "right": self.atom()}
        return left

    def scope(self, var_first: bool = False) -> tuple[str, str, dict | None]:
        collection, var = self.ident("a collection name"), self.ident("a variable name")
        where = None
        self.vars.append(var)
        try:
            if self.accept("where"):
                where = self.expr()
        except ExprError:
            self.vars.pop()
            raise
        return collection, var, where

    def quantified(self, kind: str) -> dict:
        collection, var, where = self.scope()
        try:
            if kind == "exists" and where is not None and self.peek()[1] != ":":
                body, where = where, None          # "exists X v where C" reads as "exists X v: C"
            else:
                self.expect(":")
                body = self.expr()
        finally:
            self.vars.pop()
        node = {"node": kind, "collection": collection, "variable": "$" + var, "body": body}
        if where:
            node["where"] = where
        return node

    def aggregate(self, kind: str) -> dict:
        self.expect("(")
        collection, var, where = self.scope()
        try:
            body = None
            if kind != "count" and self.peek()[1] == ")":
                body = ...                          # "sum(X v where W): value" - the value follows the bracket
            elif kind != "count":
                self.expect(":")
                body = self.expr()
            elif self.accept(":"):                 # "count(X v where A: B)" reads as "count(X v where A and B)"
                extra = self.expr()
                where = extra if where is None else {"node": "all", "args": [where, extra]}
        finally:
            self.vars.pop()
        self.expect(")")
        if body is ...:
            self.vars.append(var)
            try:
                self.expect(":")
                body = self.add()
            finally:
                self.vars.pop()
        node = {"node": kind, "collection": collection, "variable": "$" + var}
        if body:
            node["body"] = body
        if where:
            node["where"] = where
        return node

    def reaches(self) -> dict:
        """reaches(v, EXIT) or reaches(v, EXIT, through n: condition on n): a route over doors and openings."""
        self.expect("(")
        origin = self.ident("a variable")
        if origin not in self.vars:
            raise ExprError(f"'{origin}' is not a variable of an enclosing forall/exists/aggregate")
        self.expect(",")
        target = self.take()[1]
        if target is None or target in KEYWORDS:
            raise ExprError("reaches needs a destination such as EXIT")
        destination = "$" + target if target in self.vars else target
        node = {"node": "path_exists", "origin": "$" + origin, "destination": destination}
        if self.accept(","):
            self.expect("through")
            name = self.ident("a variable")
            self.vars.append(name)
            self.alias[name] = "node"
            try:
                self.expect(":")
                node["node_filter"] = self.expr()
            finally:
                self.vars.pop()
                self.alias.pop(name, None)
        self.expect(")")
        return node

    def atom(self) -> dict:
        kind, value, unit = self.peek()
        if kind == "num":
            self.i += 1
            number = float(value)
            if unit:
                u, factor = UNIT_FACTOR[unit]
                return {"node": "literal", "value": round(number * factor, 9), "unit": u}
            return {"node": "literal", "value": int(number) if number.is_integer() else number, "unit": "1",
                    "_bare": True}
        if kind == "str":
            self.i += 1
            return {"node": "literal", "value": value[1:-1], "unit": "1"}
        if kind == "op" and value == "(":
            self.i += 1
            inner = self.expr()
            self.expect(")")
            return inner
        if kind == "id":
            if value in ("true", "false"):
                self.i += 1
                return {"node": "literal", "value": value == "true", "unit": "1"}
            if value in ("forall", "exists"):
                self.i += 1
                return self.quantified(value)
            if value in ("count", "sum", "min", "max") and self.peek(1)[1] == "(":
                self.i += 1
                return self.aggregate(value)
            if value == "reaches" and self.peek(1)[1] == "(":
                self.i += 1
                return self.reaches()
            if value in KEYWORDS:
                raise ExprError(f"unexpected keyword '{value}'")
            self.i += 1
            self.expect(".")
            name = self.ident("a fact name")
            if value in self.vars:
                return {"node": "fact", "entity": "$" + self.alias.get(value, value), "name": name}
            if value in self.entities:
                return {"node": "fact", "entity": value, "name": name}
            raise ExprError(f"'{value}' is not a variable of an enclosing forall/exists/aggregate"
                            + (f" or one of {sorted(self.entities)}" if self.entities else ""))
        raise ExprError(f"unexpected '{value}'" if value else "the expression ends too early")


def parse_expression(text: str, entities: set[str] | None = None) -> dict:
    return Parser(text, entities or set()).parse()


# ---- units for bare numbers ---------------------------------------------------------------------


def _unit(node: dict, bindings: dict[str, Binding]) -> str | None:
    kind = node["node"]
    if kind == "literal":
        return None if node.get("_bare") else node["unit"]
    if kind == "fact":
        b = bindings.get(node["name"])
        return b.unit if b and b.kind == "number" else None
    if kind == "count":
        return "count"
    if kind in ("sum", "min", "max"):
        return _unit(node["body"], bindings)
    if kind in ("add", "sub"):
        return _unit(node["left"], bindings) or _unit(node["right"], bindings)
    if kind == "div":
        left, right = _unit(node["left"], bindings), _unit(node["right"], bindings)
        return "1" if left and left == right else None
    return None


def _infer(node, bindings: dict[str, Binding]) -> None:
    if isinstance(node, list):
        for child in node:
            _infer(child, bindings)
        return
    if not isinstance(node, dict):
        return
    for child in node.values():
        if isinstance(child, (dict, list)):
            _infer(child, bindings)
    if node.get("node") in ("ge", "le", "gt", "lt", "eq", "ne", "add", "sub"):
        left, right = node["left"], node["right"]
        for lit, other in ((left, right), (right, left)):
            if lit.get("node") == "literal" and lit.get("_bare"):
                unit = _unit(other, bindings)
                if unit:
                    lit["unit"] = unit
                    del lit["_bare"]


def _strip(node) -> None:
    if isinstance(node, dict):
        node.pop("_bare", None)
        for child in node.values():
            _strip(child)
    elif isinstance(node, list):
        for child in node:
            _strip(child)


def to_expression(text: str, bindings: dict[str, Binding], entities: set[str] | None = None) -> dict:
    tree = parse_expression(text, entities)
    _infer(tree, bindings)
    _strip(tree)
    return tree


def compile_expr_program(fields: dict, document: str, bindings: dict[str, Binding],
                         entities: set[str] | None = None) -> dict:
    """The model's small JSON (strings for applies_when / unless / require) -> a Program dict."""
    if not str(fields.get("require", "")).strip():
        raise ExprError("require is empty")
    program = {
        "id": fields.get("id") or "draft", "title": fields.get("title") or "draft", "document": document,
        "requirement": to_expression(fields["require"], bindings, entities),
        "sources": [{"clause": s["clause"], "start": 0, "end": 1, "quote": s["quote"]}
                    for s in fields.get("sources", [])],
        "unresolved": list(fields.get("unresolved") or []),
    }
    if (fields.get("applies_when") or "").strip():
        program["applicability"] = to_expression(fields["applies_when"], bindings, entities)
    if (fields.get("unless") or "").strip():
        program["exemption"] = to_expression(fields["unless"], bindings, entities)
    return program


# ---- the other direction: a rule as readable text (reviewer readback, and a test of the format) ----------

SYMBOL = {"ge": ">=", "le": "<=", "gt": ">", "lt": "<", "eq": "==", "ne": "!=", "add": "+", "sub": "-", "mul": "*",
          "div": "/"}
PRECEDENCE = {"any": 1, "all": 2, "not": 3, "ge": 4, "le": 4, "gt": 4, "lt": 4, "eq": 4, "ne": 4, "add": 5, "sub": 5,
              "mul": 6, "div": 6}


def _number(value: float) -> str:
    return f"{value:g}" if abs(value) >= 1e-4 else f"{value:.9f}".rstrip("0")


def to_text(node: dict, parent: int = 0) -> str:
    kind = node["node"]
    if kind == "literal":
        value, unit = node["value"], node.get("unit", "1")
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return "'" + value + "'"
        return _number(value) + (f" {unit}" if unit in ("m", "m2") else "")
    if kind == "fact":
        return f"{'n' if node['entity'] == '$node' else node['entity'].lstrip('$')}.{node['name']}"
    if kind == "path_exists":
        through = f", through n: {to_text(node['node_filter'])}" if node.get("node_filter") else ""
        return f"reaches({node['origin'].lstrip('$')}, {node['destination'].lstrip('$')}{through})"
    if kind in ("forall", "exists"):
        where = f" where {to_text(node['where'])}" if node.get("where") else ""
        text = f"{kind} {node['collection']} {node['variable'].lstrip('$')}{where}: {to_text(node['body'])}"
        return f"({text})" if parent else text
    if kind in ("count", "sum", "min", "max"):
        where = f" where {to_text(node['where'])}" if node.get("where") else ""
        body = f": {to_text(node['body'])}" if node.get("body") else ""
        return f"{kind}({node['collection']} {node['variable'].lstrip('$')}{where}{body})"
    level = PRECEDENCE[kind]
    if kind == "not":
        text = "not " + to_text(node["args"][0], level)
    elif kind in ("all", "any"):
        text = (" and " if kind == "all" else " or ").join(to_text(a, level + 1) for a in node["args"])
    else:
        text = f"{to_text(node['left'], level)} {SYMBOL[kind]} {to_text(node['right'], level + 1)}"
    return f"({text})" if level < parent else text
