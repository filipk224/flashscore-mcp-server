"""A tiny stdlib DOM for rendered Flashscore pages.

Flashscore's newer markup nests deeply and uses hashed class names
(``wcl-name_ZggyJ``), so fixed-span regexes read the wrong element. This tree
keeps parsing offline-testable without adding a dependency.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Callable, Iterator, Optional

_VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}
_SKIP_TEXT = {"script", "style", "svg", "noscript", "template"}


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs: dict[str, str], parent: Optional["Node"] = None):
        self.tag = tag
        self.attrs = attrs
        self.children: list["Node | str"] = []
        self.parent = parent

    # -- attributes -------------------------------------------------------
    def get(self, name: str, default: str | None = None) -> str | None:
        return self.attrs.get(name, default)

    @property
    def classes(self) -> list[str]:
        return (self.attrs.get("class") or "").split()

    def has_class(self, token: str) -> bool:
        """Exact class token, or a hashed token such as wcl-name_ZggyJ for 'wcl-name'."""
        hashed = token + "_"
        for cls in self.classes:
            if cls == token:
                return True
            # wcl-name_ZggyJ is a hashed wcl-name; duelParticipant__home is a
            # different BEM element, not a hash of duelParticipant.
            if cls.startswith(hashed) and not cls.startswith(token + "__") and re.fullmatch(r"[A-Za-z0-9-]{3,8}", cls[len(hashed):]):
                return True
        return False

    def class_contains(self, fragment: str) -> bool:
        return fragment in (self.attrs.get("class") or "")

    @property
    def testid(self) -> str:
        return self.attrs.get("data-testid") or ""

    # -- traversal --------------------------------------------------------
    def iter(self) -> Iterator["Node"]:
        stack: list[Node] = [self]
        while stack:
            node = stack.pop()
            yield node
            for child in reversed(node.children):
                if isinstance(child, Node):
                    stack.append(child)

    def find_all(self, pred: Callable[["Node"], bool]) -> list["Node"]:
        return [node for node in self.iter() if node is not self and pred(node)]

    def find(self, pred: Callable[["Node"], bool]) -> Optional["Node"]:
        for node in self.iter():
            if node is not self and pred(node):
                return node
        return None

    def by_class(self, token: str) -> list["Node"]:
        return self.find_all(lambda n: n.has_class(token))

    def first_class(self, token: str) -> Optional["Node"]:
        return self.find(lambda n: n.has_class(token))

    def by_testid(self, testid: str) -> list["Node"]:
        return self.find_all(lambda n: n.testid == testid)

    def first_testid(self, testid: str) -> Optional["Node"]:
        return self.find(lambda n: n.testid == testid)

    def ancestor(self, pred: Callable[["Node"], bool]) -> Optional["Node"]:
        node = self.parent
        while node is not None:
            if pred(node):
                return node
            node = node.parent
        return None

    # -- text -------------------------------------------------------------
    def text(self, sep: str = " ") -> str:
        parts: list[str] = []
        self._collect(parts)
        return " ".join(sep.join(parts).split())

    def texts(self) -> list[str]:
        parts: list[str] = []
        self._collect(parts)
        return [" ".join(part.split()) for part in parts if part.strip()]

    def _collect(self, parts: list[str]) -> None:
        if self.tag in _SKIP_TEXT:
            return
        for child in self.children:
            if isinstance(child, Node):
                child._collect(parts)
            elif child.strip():
                parts.append(child)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Node {self.tag} class={self.attrs.get('class')!r}>"


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {})
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        node = self.cur
        while node is not None and node.tag != tag:
            node = node.parent
        if node is not None and node.parent is not None:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse_html(html: str) -> Node:
    builder = _Builder()
    try:
        builder.feed(html or "")
        builder.close()
    except Exception:  # pragma: no cover - html.parser is lenient
        pass
    return builder.root


def slice_from(html: str, marker: str) -> str:
    """Drop everything before marker's tag so the tree covers less markup."""
    at = (html or "").find(marker)
    if at < 0:
        return html or ""
    start = html.rfind("<", 0, at)
    return html[max(0, start):]


def mid_from_href(href: str | None) -> str | None:
    if not href:
        return None
    found = re.search(r"[?&]mid=([A-Za-z0-9]{6,12})", href)
    if found:
        return found.group(1)
    found = re.search(r"/match/([A-Za-z0-9]{6,12})/?(?:[#?]|$)", href)
    return found.group(1) if found else None
