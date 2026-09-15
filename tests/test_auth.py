"""Tests for mcp_gateway/auth.py - token issuing and role-based authorization."""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-do-not-use-in-prod")

import pytest
from jose import jwt, JWTError

from mcp_gateway.auth import (
    create_access_token, decode_access_token, is_authorized,
    JWT_SECRET_KEY, JWT_ALGORITHM,
)


def test_token_round_trip_contains_subject_and_role():
    token = create_access_token(subject="recruiter1", role="recruiter")
    payload = decode_access_token(token)
    assert payload["sub"] == "recruiter1"
    assert payload["role"] == "recruiter"


def test_tampered_token_is_rejected():
    token = create_access_token(subject="recruiter1", role="recruiter")
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    with pytest.raises(JWTError):
        decode_access_token(tampered)


def test_recruiter_can_rank_but_not_create_job():
    assert is_authorized("recruiter", "rank_candidates_tool") is True
    assert is_authorized("recruiter", "create_job") is False


def test_hiring_manager_cannot_create_candidate():
    assert is_authorized("hiring_manager", "create_candidate") is False


def test_admin_has_full_access():
    assert is_authorized("admin", "create_candidate") is True
    assert is_authorized("admin", "anything_not_even_a_real_tool") is True


def test_unknown_role_is_denied_everything():
    assert is_authorized("intern_with_no_role_entry", "search_candidates") is False
