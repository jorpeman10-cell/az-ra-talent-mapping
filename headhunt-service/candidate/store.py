# -*- coding: utf-8 -*-
"""Candidate archive: per-candidate JSON dirs, 48h single-use tokens, status machine.
Pure stdlib; no LLM, no network, no production connections."""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("HEADHUNT_DATA_DIR") or os.path.join(BASE, "data")
CONFIG_DIR = os.environ.get("HEADHUNT_CONFIG_DIR") or os.path.join(BASE, "config")
CANDIDATES_DIR = os.path.join(DATA_DIR, "candidates")
TOKEN_TTL_HOURS = 48          # self-assess token (single use)
HR_TOKEN_TTL_HOURS = 168      # HR interview-assess token, 7 days (independent)


def _now():
    return datetime.now(timezone.utc)


def _cid():
    return "c" + _now().strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)


def _write(cid, fname, obj):
    os.makedirs(os.path.join(CANDIDATES_DIR, cid), exist_ok=True)
    with open(os.path.join(CANDIDATES_DIR, cid, fname), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def new_candidate(name, target_line="", notes=""):
    cid = _cid()
    rec = {
        "cid": cid, "name": name, "target_line": target_line or "", "notes": notes or "",
        "created_at": _now().isoformat(),
        "token": secrets.token_urlsafe(24),
        "token_expires_at": (_now() + timedelta(hours=TOKEN_TTL_HOURS)).isoformat(),
        "hr_token": secrets.token_urlsafe(24),
        "hr_token_expires_at": (_now() + timedelta(hours=HR_TOKEN_TTL_HOURS)).isoformat(),
        "self_submitted_at": None, "hr_submitted_at": None, "assessed_at": None,
        "status": "CREATED",
    }
    _write(cid, "profile.json", rec)
    return rec


def get(cid):
    p = os.path.join(CANDIDATES_DIR, cid, "profile.json")
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def update(cid, **fields):
    rec = get(cid)
    if rec is None:
        return None
    rec.update(fields)
    _write(cid, "profile.json", rec)
    return rec


def save_json(cid, fname, obj):
    _write(cid, fname, obj)


def load_json(cid, fname):
    p = os.path.join(CANDIDATES_DIR, cid, fname)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def list_candidates():
    out = []
    if not os.path.isdir(CANDIDATES_DIR):
        return out
    for cid in sorted(os.listdir(CANDIDATES_DIR)):
        rec = get(cid)
        if rec:
            # status is derived, not read from the stored field (it goes stale)
            out.append({k: rec.get(k) for k in ("cid", "name", "created_at",
                                                "self_submitted_at", "hr_submitted_at", "assessed_at")}
                       | {"status": derive_status(rec)})
    return out


def validate_token(token, now=None):
    """Return (cid, None) or (None, reason in not_found/expired/already_submitted)."""
    now = now or _now()
    if not os.path.isdir(CANDIDATES_DIR):
        return None, "not_found"
    for cid in os.listdir(CANDIDATES_DIR):
        rec = get(cid)
        if rec and rec.get("token") == token:
            if rec.get("self_submitted_at"):
                return None, "already_submitted"
            if now > datetime.fromisoformat(rec["token_expires_at"]):
                return None, "expired"
            return cid, None
    return None, "not_found"


def validate_hr_token(token, now=None):
    """HR interview-assess token: same contract as validate_token but keyed on
    hr_token / hr_token_expires_at / hr_submitted_at. Fully independent from
    the self-assess token."""
    now = now or _now()
    if not os.path.isdir(CANDIDATES_DIR):
        return None, "not_found"
    for cid in os.listdir(CANDIDATES_DIR):
        rec = get(cid)
        if rec and rec.get("hr_token") == token:
            if rec.get("hr_submitted_at"):
                return None, "already_submitted"
            if now > datetime.fromisoformat(rec["hr_token_expires_at"]):
                return None, "expired"
            return cid, None
    return None, "not_found"


def derive_status(rec):
    if rec.get("assessed_at"):
        return "ASSESSED"
    if rec.get("hr_submitted_at"):
        return "HR_DONE"
    if rec.get("self_submitted_at"):
        return "SELF_DONE"
    return "CREATED"
