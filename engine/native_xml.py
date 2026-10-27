# -*- coding: utf-8 -*-
"""Native XML text parsed into an ElementTree, the same inside every IDE.

The ElementTree a vendor's ScriptLib ships is not one parser. CODESYS
3.5.21.40 has expat underneath, which wants UTF-8 bytes and refuses text
that is not ASCII. DIADesigner-AX 1.8 and 1.10 and Lenze PLC Designer 3.24
fall back to the old pure-Python xmllib, which reads bytes as Latin-1 (so
the micro sign in a task's "µs" came back as "Âµs") and refuses any
character above U+00FF however it is given, a task named in Chinese
included. Measured 2026-10-27 in all four with a headless probe. .NET's XmlDocument read both correctly in every one of them, so inside an
IDE the document goes through it and is copied into ElementTree elements;
outside one, where there is no .NET, ElementTree is CPython's own and
takes UTF-8 bytes.
"""
from __future__ import print_function

import xml.etree.ElementTree as ET


def parsed(text):
    """The root element of `text`, an XML document without its declaration."""
    try:
        import clr
    except ImportError:
        return ET.fromstring(text.encode("utf-8"))
    clr.AddReference("System.Xml")
    from System.Xml import XmlDocument, XmlNodeType
    document = XmlDocument()
    document.LoadXml(text)
    return tree(document.DocumentElement, XmlNodeType.Element)


def tree(node, element_kind):
    """`node` and the elements under it, copied into ElementTree elements.

    Only what the readers here use: names, attributes, child elements, and
    the text of an element with no child elements.
    """
    element = ET.Element(node.Name, dict((attribute.Name, attribute.Value)
                                         for attribute in node.Attributes))
    children = [child for child in node.ChildNodes
                if child.NodeType == element_kind]
    for child in children:
        element.append(tree(child, element_kind))
    if not children:
        element.text = node.InnerText
    return element
