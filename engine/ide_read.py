# -*- coding: utf-8 -*-
"""Reading one property off a live IDE object, in one place.

Every attribute read here crosses into .NET (PRINCIPLES 3), and every one of
them can raise: an object whose plugin is missing answers nothing at all, not
even its name. Four modules had each grown a private version of the same four
reads, and the versions had drifted -- two spellings of "list the children",
one of which recorded the failure and one of which only logged it; three
different sentences for "it will not say its name".

What a failure does here is record the object in engine/unhandled.py by name
(SPEC D13) and hand the caller a value it can carry on with, so one unreadable
object costs one named entry in the result rather than the whole walk. That is
also the behaviour change this module made: the login pre-flight in
codesys_online.py used to log a warning and carry on, which left an import
believing nothing was logged in when the truth was that nobody could tell.
"""
from __future__ import print_function

from engine import unhandled
from engine.codesys_constants import kind_of as kind_of_guid
from engine.codesys_utils import safe_str

# The register owns this one: note() needs a name for the very object that is
# failing, so the fallback chain has to live where the register can reach it
# without importing this module back. Re-exported rather than reimplemented,
# so "what do we call an object" still has exactly one answer.
name_of = unhandled.name_of


def guid_of(obj):
    """The object's GUID as text, or None when it has none or will not say.

    An empty GUID is None too. Callers use this as a cache key, and "" is a
    key that every object without a GUID would share.
    """
    try:
        return safe_str(obj.guid) or None
    except Exception as exc:
        unhandled.note(obj, exc)
        return None


def kind_of(obj):
    """The profile kind name of an object, or None when it will not say.

    kind_of_guid (codesys_constants) answers the other half of this question:
    it maps a type GUID to a kind. This one is the read that gets the GUID.
    """
    try:
        return kind_of_guid(safe_str(obj.type))
    except Exception as exc:
        unhandled.note(obj, exc)
        return None


def parent_of(obj):
    """The object's parent, or None at the top of the tree.

    One read, not two: hasattr() is itself a property read, so the guarded
    form doubled the cost of the single most-repeated lookup in path building.
    A missing `parent` is the tree root and costs nothing; only a parent
    property that raises is worth recording.
    """
    try:
        return getattr(obj, "parent", None)
    except Exception as exc:
        unhandled.note(obj, exc)
        return None


def children_of(obj):
    """The object's direct children, or an empty list when it will not list them.

    Empty is what the caller gets either way, which is exactly why the failure
    has to be recorded: a node that refuses to list its children looks the same
    from here as a leaf.
    """
    try:
        return obj.get_children()
    except Exception as exc:
        unhandled.note(obj, exc)
        return []
