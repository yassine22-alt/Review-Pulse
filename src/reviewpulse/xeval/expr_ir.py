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

from ..interpreter import units
from ..interpreter.schema import Binding
from ..interpreter.units import is_unit

KEYWORDS = {"forall", "exists", "count", "sum", "min", "max", "where", "and", "or", "not", "true", "false",
            "reaches", "through", "avoiding", "linked"}
TOKEN = re.compile(r"""\s*(?:
    (?P<num>\d+(?:\.\d+)?)(?P<unitrun>\s?(?:[^\W\d_°µ]|[°µ%])[^\s,()<>=!:+*]*)?
  | (?P<str>'[^']*'|"[^"]*")
  | (?P<op>>=|<=|==|!=|>|<|\+|-|\*|/|\(|\)|:|,|\.)
  | (?P<id>[A-Za-z_][A-Za-z0-9_]*)
)""", re.X)
AGGREGATES = {"count", "sum", "min", "max"}      # words that are also units (min) unless a bracket follows
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
        unit = None
        if m.group("num") is not None and m.group("unitrun"):
            # the longest stretch after the number that is a unit ("kPa", "L/min", "m2"); a word like "and" is not one
            run = m.group("unitrun").strip()
            keep = next((run[:k] for k in range(len(run), 0, -1)
                         if (run[:k].lower() not in KEYWORDS or (run[:k].lower() in AGGREGATES and run[k:k + 1] != "("))
                         and is_unit(run[:k])), None)           # "30 min" is minutes; "min(" would be the aggregate
            if keep:
                unit = keep
                pos = m.start("unitrun") + (len(m.group("unitrun")) - len(m.group("unitrun").lstrip())) + len(keep)
            else:
                pos = m.end("num")
        for kind in ("num", "str", "op", "id"):
            if m.group(kind) is not None:
                out.append((kind, m.group(kind), unit if kind == "num" else None))
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
            if self.accept("avoiding"):
                # reaches(v, EXIT, avoiding 'a', 'b'): the model names categories; the filter is built from declared values
                values = []
                while True:
                    kind, value, _ = self.take()
                    if kind != "str":
                        raise ExprError("avoiding needs category values in single quotes, such as avoiding 'bathroom'")
                    values.append(value[1:-1])
                    if not self.accept(","):
                        break
                node["_avoid"] = values
            else:
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

    def linked(self) -> dict:
        """linked(a, b): a door or opening joins the two rooms directly."""
        self.expect("(")
        ends = []
        for k in range(2):
            name = self.ident("a variable")
            if name not in self.vars:
                raise ExprError(f"'{name}' is not a variable of an enclosing forall/exists/aggregate")
            ends.append("$" + name)
            if k == 0:
                self.expect(",")
        self.expect(")")
        return {"node": "linked", "a": ends[0], "b": ends[1]}
    def atom(self) -> dict:
        kind, value, unit = self.peek()
        if kind == "num":
            self.i += 1
            number = float(value)
            if unit:
                return {"node": "literal", "value": number, "unit": unit, "_written": True}
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
            if value == "linked" and self.peek(1)[1] == "(":
                self.i += 1
                return self.linked()
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
    if kind in ("mul", "div"):
        left, right = _unit(node["left"], bindings), _unit(node["right"], bindings)
        if left and right:
            try:
                return units.combine(left, right, kind)
            except units.UnitError:
                return None
        return left or (right if kind == "mul" else None)          # a bare number leaves the other unit unchanged
    return None


def _convert_written(lit: dict, target: str) -> None:
    """A number written with a unit takes the unit of what it is compared with: 90 cm against a length in m is 0.9 m."""
    try:
        if units.compatible(lit["unit"], target):
            lit["value"] = round(units.convert(lit["value"], lit["unit"], target), 9)
            lit["unit"] = target
            lit.pop("_written", None)
    except units.UnitError:
        pass                                                   # incompatible: the validator refuses it with its reason


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
            elif lit.get("node") == "literal" and lit.get("_written"):
                unit = _unit(other, bindings)
                if unit:
                    _convert_written(lit, unit)


def _strip(node) -> None:
    if isinstance(node, dict):
        node.pop("_bare", None)
        if node.pop("_written", None):                          # compared with nothing that has a unit: coherent SI
            try:
                u = units.parse_unit(node["unit"])
                if not u.offset:
                    node["value"] = round(node["value"] * u.factor, 9)
                    node["unit"] = units.symbol_of(units.Unit(1.0, u.dims))
            except units.UnitError:
                pass
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


def resolve_avoiding(node, kinds: dict | None) -> None:
    """Turn `_avoid: ['a', 'b']` into a route filter on the category fact whose declared values contain them all."""
    if isinstance(node, list):
        for child in node:
            resolve_avoiding(child, kinds)
        return
    if not isinstance(node, dict):
        return
    for child in node.values():
        if isinstance(child, (dict, list)):
            resolve_avoiding(child, kinds)
    values = node.pop("_avoid", None)
    if values is None:
        return
    fact = next((name for name, declared in (kinds or {}).items() if set(values) <= set(declared)), None)
    if fact is None:
        raise ExprError(f"avoiding {values}: no category fact declares all of these values; use only declared values")
    tests = [{"node": "ne", "left": {"node": "fact", "entity": "$node", "name": fact},
              "right": {"node": "literal", "value": v, "unit": "1"}} for v in values]
    node["node_filter"] = tests[0] if len(tests) == 1 else {"node": "all", "args": tests}


def apply_passable(node, passable: list[str] | None) -> None:
    """Routes and links follow the connections the fact graph declares passable (a door, an opening, a pipe)."""
    if passable is None:
        return
    if isinstance(node, list):
        for child in node:
            apply_passable(child, passable)
        return
    if not isinstance(node, dict):
        return
    if node.get("node") in ("path_exists", "linked") and "via_edges" not in node:
        node["via_edges"] = list(passable)
    for child in node.values():
        if isinstance(child, (dict, list)):
            apply_passable(child, passable)


def compile_expr_program(fields: dict, document: str, bindings: dict[str, Binding],
                         entities: set[str] | None = None, kinds: dict | None = None,
                         passable: list[str] | None = None, labels: dict | None = None,
                         groups: dict | None = None) -> dict:
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
    for key in ("requirement", "applicability", "exemption"):
        if key in program:
            from .terms import resolve_terms

            resolve_terms(program[key], kinds or {}, labels or {}, groups or {})
            resolve_avoiding(program[key], kinds)
            apply_passable(program[key], passable)
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
        return _number(value) + (f" {unit}" if unit not in ("1", "count") else "")
    if kind == "fact":
        return f"{'n' if node['entity'] == '$node' else node['entity'].lstrip('$')}.{node['name']}"
    if kind == "linked":
        return f"linked({node['a'].lstrip('$')}, {node['b'].lstrip('$')})"
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
