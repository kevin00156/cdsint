# -*- coding: utf-8 -*-
"""What read_value() answers, read as a type: its size, and its roles.

The size bounds the controller's ring (SPEC 6.8 "The controller's memory");
the role rules keep a trigger numeric and a condition a BOOL.
"""
import pytest

from cds.core import trace_types


@pytest.mark.parametrize("shown, kind", [
    ("INT#3", "INT"), ("UDINT#0", "UDINT"), ("int#3", "INT"),
    ("BOOL#TRUE", "BOOL"), ("TRUE", "BOOL"), ("false", "BOOL"),
    ("REAL#1.5", "REAL"), ("LREAL#-2", "LREAL"),
    ("T#5s", "TIME"), ("TIME#5s", "TIME"), ("LTIME#1ns", "LTIME"),
    ("TOD#12:00", "TOD"), ("TIME_OF_DAY#12:00", "TOD"),
    ("D#2026-09-24", "DATE"), ("DT#2026-09-24-12:00", "DT"),
    ("DATE_AND_TIME#2026-09-24-12:00", "DT"),
    ("E_State#Idle", "E_STATE"),
])
def test_the_type_is_what_comes_before_the_hash(shown, kind):
    assert trace_types.type_of(shown) == kind


@pytest.mark.parametrize("shown", ["3", "'abc'", "", None, "TRUEISH"])
def test_an_answer_that_names_no_type_is_none(shown):
    assert trace_types.type_of(shown) is None


def test_the_sizes_are_the_iec_ones():
    sizes = trace_types.SIZES
    assert [sizes[t] for t in ("BOOL", "BYTE", "SINT", "USINT")] == [1] * 4
    assert [sizes[t] for t in ("WORD", "INT", "UINT")] == [2] * 3
    assert [sizes[t] for t in ("DWORD", "DINT", "UDINT", "REAL", "TIME",
                               "TOD", "DATE", "DT")] == [4] * 8
    assert [sizes[t] for t in ("LWORD", "LINT", "ULINT", "LREAL",
                               "LTIME")] == [8] * 5
    assert len(sizes) == 20


def test_every_alias_lands_on_a_sized_type():
    assert set(trace_types.ALIASES.values()) <= set(trace_types.SIZES)


def job(**extra):
    found = {"variables": ["PRG_X.a", "GVL.b"]}
    found.update(extra)
    return found


SHOWN = {"prg_x.a": "INT#3", "gvl.b": "UDINT#0", "gvl.cnt": "UDINT#7",
         "gvl.x": "TRUE", "gvl.flag": "BOOL#FALSE", "gvl.s": "'text'",
         "gvl.e": "E_State#Idle", "gvl.t": "T#1s"}


def test_sized_variables_are_refused_nothing():
    assert trace_types.refusals(job(), SHOWN) == []


def test_a_variable_with_no_type_is_refused_by_name():
    found = trace_types.refusals(job(variables=["PRG_X.a", "GVL.s"]), SHOWN)
    assert [name for name, _why in found] == ["GVL.s"]
    assert "type unknown" in found[0][1]
    assert "'text'" in found[0][1]


def test_a_type_without_a_size_is_refused_by_name():
    found = trace_types.refusals(job(variables=["GVL.e"]), SHOWN)
    assert found[0][0] == "GVL.e" and "type E_STATE" in found[0][1]


def test_a_numeric_trigger_is_accepted():
    trigger = {"variable": "GVL.cnt"}
    assert trace_types.refusals(job(trigger=trigger), SHOWN) == []


@pytest.mark.parametrize("variable", ["GVL.x", "GVL.flag", "GVL.t", "GVL.s"])
def test_a_trigger_that_is_not_numeric_is_refused(variable):
    found = trace_types.refusals(job(trigger={"variable": variable}), SHOWN)
    assert found[0][0] == variable
    assert "trigger needs a numeric type" in found[0][1]


@pytest.mark.parametrize("variable", ["GVL.x", "GVL.flag"])
def test_a_bool_condition_is_accepted(variable):
    assert trace_types.refusals(job(record_condition=variable), SHOWN) == []


@pytest.mark.parametrize("variable", ["GVL.cnt", "GVL.s", "GVL.t"])
def test_a_condition_that_is_not_bool_is_refused(variable):
    found = trace_types.refusals(job(record_condition=variable), SHOWN)
    assert found[0][0] == variable and "not a BOOL" in found[0][1]


def test_names_are_looked_up_without_case():
    found = trace_types.refusals(job(variables=["prg_X.A"],
                                     trigger={"variable": "gvl.CNT"}), SHOWN)
    assert found == []
