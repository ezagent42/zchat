"""Tests for wc_protocol shared module."""


def test_scoped_name_adds_prefix():
    from wc_protocol.naming import scoped_name
    assert scoped_name("helper", "alice") == "alice-helper"


def test_scoped_name_no_double_prefix():
    from wc_protocol.naming import scoped_name
    assert scoped_name("alice-helper", "alice") == "alice-helper"


def test_scoped_name_different_prefix():
    from wc_protocol.naming import scoped_name
    assert scoped_name("bob-helper", "alice") == "bob-helper"
