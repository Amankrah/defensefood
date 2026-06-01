"""Comtrade API key pool and rotation."""

import os

import pytest

from defensefood.ingestion import comtrade_keys as ck


@pytest.fixture(autouse=True)
def _reset_pool(monkeypatch):
    ck.reset_key_pool()
    monkeypatch.delenv("COMTRADE_SUBSCRIPTION_KEY", raising=False)
    monkeypatch.delenv("COMTRADE_SUBSCRIPTION_KEYS", raising=False)
    yield
    ck.reset_key_pool()


def test_parse_multiple_keys(monkeypatch):
    monkeypatch.setenv("COMTRADE_SUBSCRIPTION_KEYS", "key_a, key_b ,key_a")
    pool = ck.ComtradeKeyPool()
    assert pool.keys == ["key_a", "key_b"]


def test_single_and_multi_combined(monkeypatch):
    monkeypatch.setenv("COMTRADE_SUBSCRIPTION_KEY", "solo")
    monkeypatch.setenv("COMTRADE_SUBSCRIPTION_KEYS", "b,c")
    pool = ck.ComtradeKeyPool()
    assert pool.keys == ["solo", "b", "c"]


def test_rotate_until_exhausted(monkeypatch):
    monkeypatch.setenv("COMTRADE_SUBSCRIPTION_KEYS", "k1,k2")
    pool = ck.ComtradeKeyPool()
    assert pool.current_key() == "k1"
    assert pool.rotate() is True
    assert pool.current_key() == "k2"
    assert pool.rotate() is False
    assert pool.all_exhausted() is True


def test_is_quota_http_error():
    assert ck.is_quota_http_error(403, "Out of call volume quota")
    assert not ck.is_quota_http_error(401, "Unauthorized")
