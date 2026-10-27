# -*- coding: utf-8 -*-
"""engine/native_xml.py: the .NET document copied into ElementTree elements.

The .NET half only runs inside an IDE; here its nodes are stand-ins with the
members tree() reads, so the copy is checked without one.
"""
from engine import native_xml

ELEMENT, TEXT, COMMENT = "Element", "Text", "Comment"


class Attribute(object):
    def __init__(self, name, value):
        self.Name, self.Value = name, value


class Node(object):
    def __init__(self, kind, name=u"", attributes=None, children=(),
                 text=u""):
        self.NodeType, self.Name = kind, name
        self.Attributes = [Attribute(k, v)
                           for k, v in sorted((attributes or {}).items())]
        self.ChildNodes = list(children)
        self.InnerText = text or u"".join(c.InnerText for c in children)


def element(name, attributes=None, children=(), text=u""):
    return Node(ELEMENT, name, attributes, children, text)


def test_the_copy_keeps_names_attributes_children_and_leaf_text():
    unit = element(u"Single", {u"Name": u"Unit"}, [Node(TEXT, text=u"µs")])
    interval = element(u"Single", {u"Name": u"Interval"},
                       [Node(COMMENT, text=u"not an element"), unit])
    root = native_xml.tree(element(u"ExportFile", children=[interval]),
                           ELEMENT)
    assert root.tag == u"ExportFile"
    [copied] = list(root)
    assert copied.get(u"Name") == u"Interval"
    [leaf] = list(copied)
    assert leaf.get(u"Name") == u"Unit"
    assert leaf.text == u"µs"


def test_outside_an_ide_the_text_is_parsed_as_utf8():
    root = native_xml.parsed(u'<a n="主"><b>主任務 µs</b></a>')
    assert root.get("n") == u"主"
    assert root.find("b").text == u"主任務 µs"
