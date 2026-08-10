"""v1.45 — emailing a costing document from the Preview / Export dialog.

Covers both endpoints (live preview + approved record):
  * the rendered document is ATTACHED, with the right filename/extension per format
    and byte-identical to what the download endpoint would have produced;
  * one recipient, the sender Cc'd from their account email (skipped when blank —
    many accounts still carry email='' since the column only landed in 0030);
  * PREVIEW mail is framed as an internal draft (Michael, 10 Aug) and approved mail
    is not; the optional note rides in the body; totals appear in the body;
  * recipient validation (blank / malformed) and the permission gate;
  * unconfigured SMTP fails LOUDLY (503) rather than silently no-opping — the user
    is waiting on the dialog;
  * emailing a preview still writes NOTHING to the DB.

SMTP is never really opened: `_deliver` is monkeypatched and the EmailMessage is
captured, so these assert on the actual MIME the app built.
"""
import io
import json
import uuid
from datetime import datetime

import pytest

FIXED_RECORD_ID = 900146
FIXED_TT_NAME = "V145 EMAIL BODY"
FIXED_CREATED_AT = datetime(2026, 3, 3, 8, 0, 0)

RESULT_FIXTURE = {
    "items": [
        {"category": "FLOOR", "material": "MAIL FLOOR SHEET", "material_code": "MF-1",
         "formula": "L*W", "quantity": 4.0, "unit": "m2", "unit_price": 100.0,
         "waste_pct": 0, "line_cost": 400.0, "last_updated": None},
    ],
    "category_totals": {"FLOOR": 400.0},
    "grand_total": 400.0,
    "profit_margin": 10,
    "ratio_value": 0.5,
}
DIMS_FIXTURE = {"length": 9.0, "width": 2.5, "height": 2.6}


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app_mod():
    import app.main as m
    from starlette.testclient import TestClient
    with TestClient(m.app) as _c:
        yield m


@pytest.fixture(scope="module")
def client(app_mod):
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        yield c


def _session_for(username: str) -> dict:
    from app.database import SessionLocal, User, UserSession
    sid = f"v145-{uuid.uuid4().hex[:12]}"
    csrf = f"csrf-{sid}"
    with SessionLocal() as db:
        u = db.query(User).filter_by(username=username).first()
        assert u, f"user {username!r} missing"
        db.merge(UserSession(id=sid, user_id=u.id, role=u.role,
                             expires_at=None, csrf_token=csrf))
        db.commit()
    return {"Cookie": f"session_id={sid}", "X-CSRF-Token": csrf}


@pytest.fixture(scope="module")
def admin_headers(app_mod):
    """Admin, WITH an account email so the sender-Cc path is exercised."""
    from app.database import SessionLocal, User
    with SessionLocal() as db:
        u = db.query(User).filter_by(username="admin").first()
        prior = u.email
        u.email = "sender@icecoldgrp.co.za"
        db.commit()
    headers = _session_for("admin")
    yield headers
    with SessionLocal() as db:
        u = db.query(User).filter_by(username="admin").first()
        u.email = prior
        db.commit()


@pytest.fixture(scope="module")
def full_no_email_headers(app_mod):
    """Role 'full' with a BLANK account email — Nadie's real shape on dev today."""
    from app.database import SessionLocal, User, UserSession
    uname = f"t_full_{uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        db.add(User(username=uname, password_hash="x", role="full", email=""))
        db.commit()
    headers = _session_for(uname)
    yield headers
    with SessionLocal() as db:
        db.query(UserSession).filter_by(
            id=headers["Cookie"].split("session_id=")[1]).delete()
        db.query(User).filter_by(username=uname).delete()
        db.commit()


@pytest.fixture(scope="module")
def planner_headers(app_mod):
    from app.database import SessionLocal, User, UserSession
    uname = f"t_planner_{uuid.uuid4().hex[:6]}"
    with SessionLocal() as db:
        db.add(User(username=uname, password_hash="x", role="planner"))
        db.commit()
    headers = _session_for(uname)
    yield headers
    with SessionLocal() as db:
        db.query(UserSession).filter_by(
            id=headers["Cookie"].split("session_id=")[1]).delete()
        db.query(User).filter_by(username=uname).delete()
        db.commit()


@pytest.fixture(scope="module")
def seeded(app_mod):
    from app.database import (SessionLocal, TrailerType, CalculationRecord, User,
                              Customer)
    with SessionLocal() as db:
        admin = db.query(User).filter_by(username="admin").first()
        tt = db.query(TrailerType).filter_by(name=FIXED_TT_NAME).first()
        if not tt:
            tt = TrailerType(name=FIXED_TT_NAME, description="v1.45 email fixture")
            db.add(tt)
            db.flush()
        cust = db.query(Customer).filter_by(name="V145 EMAIL CUSTOMER").first()
        if not cust:
            cust = Customer(name="V145 EMAIL CUSTOMER")
            db.add(cust)
            db.flush()
        rec = db.query(CalculationRecord).filter_by(id=FIXED_RECORD_ID).first()
        if not rec:
            rec = CalculationRecord(
                id=FIXED_RECORD_ID, trailer_type_id=tt.id, user_id=admin.id,
                customer_id=cust.id, quote_number="A99145/03/2026",
                contact_email="attention@customer.co.za",
                dimensions_json=json.dumps(DIMS_FIXTURE),
                result_json=json.dumps(RESULT_FIXTURE),
                created_at=FIXED_CREATED_AT, status="pending", is_repair=False)
            db.add(rec)
        db.commit()
        ids = {"tt_id": tt.id, "rec_id": FIXED_RECORD_ID, "cust_id": cust.id}
    yield ids
    with SessionLocal() as db:
        db.query(CalculationRecord).filter_by(id=FIXED_RECORD_ID).delete()
        db.query(TrailerType).filter_by(id=ids["tt_id"]).delete()
        db.query(Customer).filter_by(id=ids["cust_id"]).delete()
        db.commit()


@pytest.fixture()
def outbox(monkeypatch):
    """Capture the EmailMessage instead of opening SMTP. Also forces a non-empty
    SMTP_URL so the 'not configured' guard doesn't short-circuit the send."""
    import app.services.notifications as notif
    sent: list = []
    monkeypatch.setattr(notif.settings, "SMTP_URL", "smtp://user:pw@mail.test:587",
                        raising=False)
    monkeypatch.setattr(notif.settings, "EMAIL_FROM", "mes@icecoldgrp.co.za",
                        raising=False)
    monkeypatch.setattr(notif, "_deliver", lambda msg, url: sent.append(msg))
    return sent


@pytest.fixture()
def frozen_clock(monkeypatch):
    """Pin the renderers' clock. Every document carries a "Generated {dd Mon YYYY
    HH:MM}" footer, so two renders only match byte-for-byte inside the same
    minute — comparing them unpinned is a coin-flip that passes alone and fails
    in a full run (which is exactly how it first showed up)."""
    import app.routers.exports as ex
    fixed = datetime(2026, 3, 3, 9, 30, 0)

    class _FixedDT(datetime):        # subclass: fromisoformat/timedelta still work
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.replace(tzinfo=tz)

    monkeypatch.setattr(ex, "datetime", _FixedDT)
    return fixed


def _attachment(msg):
    for part in msg.iter_attachments():
        return part
    return None


def _body_text(msg) -> str:
    for part in msg.walk():
        if part.get_content_type() == "text/plain" and not part.get_filename():
            return part.get_content()
    return ""


def _preview_payload(**over):
    payload = {"result": RESULT_FIXTURE, "dims": DIMS_FIXTURE,
               "trailer_name": FIXED_TT_NAME, "to": "buyer@customer.co.za"}
    payload.update(over)
    return payload


# ── preview email ─────────────────────────────────────────────────────────────
def test_preview_email_attaches_the_document(client, admin_headers, outbox):
    r = client.post("/api/export/preview/email", headers=admin_headers,
                    json=_preview_payload(format="pdf", detail="totals", ratios=[0.5]))
    assert r.status_code == 200, r.text
    assert r.json()["to"] == "buyer@customer.co.za"
    assert len(outbox) == 1
    msg = outbox[0]
    assert msg["To"] == "buyer@customer.co.za"
    assert msg["Cc"] == "sender@icecoldgrp.co.za"          # sender copied in
    att = _attachment(msg)
    assert att is not None, "no attachment on the message"
    assert att.get_filename().endswith(".pdf")
    assert att.get_payload(decode=True)[:5] == b"%PDF-"


def test_preview_email_is_framed_as_a_draft(client, admin_headers, outbox):
    r = client.post("/api/export/preview/email", headers=admin_headers,
                    json=_preview_payload(format="excel", note="Checked the floor twice."))
    assert r.status_code == 200, r.text
    msg = outbox[0]
    assert "DRAFT" in msg["Subject"] and "not a quotation" in msg["Subject"].lower()
    body = _body_text(msg)
    assert "INTERNAL DRAFT" in body
    assert "no quote number" in body
    assert "Checked the floor twice." in body               # the optional note rides along
    assert "TOTAL COST" in body                             # totals summarised in the body
    assert _attachment(msg).get_filename().endswith(".xlsx")


def test_preview_email_matches_the_download_bytes(client, admin_headers, outbox,
                                                  frozen_clock):
    """The emailed attachment IS the document the user would have downloaded —
    same renderer, same options, same bytes (clock pinned, see frozen_clock)."""
    opts = {"format": "word", "detail": "items", "ratios": [0.35, 0.55]}
    dl = client.post("/api/export/preview", headers=admin_headers,
                     json=_preview_payload(**opts))
    assert dl.status_code == 200, dl.text
    em = client.post("/api/export/preview/email", headers=admin_headers,
                     json=_preview_payload(**opts))
    assert em.status_code == 200, em.text
    attached = _attachment(outbox[0]).get_payload(decode=True)
    assert attached == dl.content


def test_preview_email_writes_nothing(client, admin_headers, outbox):
    from app.database import SessionLocal, CalculationRecord
    with SessionLocal() as db:
        before = db.query(CalculationRecord).count()
    r = client.post("/api/export/preview/email", headers=admin_headers,
                    json=_preview_payload(format="pdf"))
    assert r.status_code == 200
    with SessionLocal() as db:
        assert db.query(CalculationRecord).count() == before


def test_sender_cc_skipped_when_account_has_no_email(client, full_no_email_headers, outbox):
    r = client.post("/api/export/preview/email", headers=full_no_email_headers,
                    json=_preview_payload(format="excel"))
    assert r.status_code == 200, r.text
    assert r.json()["cc"] is None
    assert outbox[0]["Cc"] is None                          # sent, just without a copy


# ── approved email ────────────────────────────────────────────────────────────
def test_approved_email_is_not_a_draft(client, admin_headers, seeded, outbox):
    r = client.post(f"/results/{seeded['rec_id']}/export/email", headers=admin_headers,
                    json={"to": "buyer@customer.co.za", "format": "pdf",
                          "detail": "totals", "ratios": [0.5]})
    assert r.status_code == 200, r.text
    msg = outbox[0]
    assert "DRAFT" not in msg["Subject"]
    assert "A99145/03/2026" in msg["Subject"]               # quote number in the subject
    body = _body_text(msg)
    assert "INTERNAL DRAFT" not in body
    assert "V145 EMAIL CUSTOMER" in body                    # client named in the body
    assert _attachment(msg).get_filename().endswith(".pdf")


def test_approved_email_defaults_to_pdf(client, admin_headers, seeded, outbox):
    r = client.post(f"/results/{seeded['rec_id']}/export/email", headers=admin_headers,
                    json={"to": "buyer@customer.co.za"})
    assert r.status_code == 200, r.text
    assert _attachment(outbox[0]).get_filename().endswith(".pdf")


def test_approved_email_404_for_unknown_record(client, admin_headers, outbox):
    r = client.post("/results/99999999/export/email", headers=admin_headers,
                    json={"to": "buyer@customer.co.za"})
    assert r.status_code == 404


# ── guards ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["", "   ", "not-an-email", "a@b", "two@addr.com, x@y.com"])
def test_bad_recipient_rejected(client, admin_headers, outbox, bad):
    r = client.post("/api/export/preview/email", headers=admin_headers,
                    json=_preview_payload(format="pdf", to=bad))
    assert r.status_code == 400, r.text
    assert not outbox, "nothing may be sent when the address is rejected"


def test_email_gated_on_the_format_permission(client, planner_headers, outbox):
    r = client.post("/api/export/preview/email", headers=planner_headers,
                    json=_preview_payload(format="pdf"))
    assert r.status_code == 403
    assert not outbox


def test_email_requires_a_session(client, outbox):
    r = client.post("/api/export/preview/email", json=_preview_payload(format="pdf"))
    assert r.status_code == 401
    assert not outbox


def test_bad_format_rejected(client, admin_headers, outbox):
    r = client.post("/api/export/preview/email", headers=admin_headers,
                    json=_preview_payload(format="csv"))
    assert r.status_code == 400
    assert not outbox


def test_unconfigured_smtp_fails_loudly(client, admin_headers, monkeypatch):
    """No SMTP → 503 with a plain-English message, NOT a silent success. The
    sibling helpers log-and-continue; this one must not (the user is waiting)."""
    import app.services.notifications as notif
    monkeypatch.setattr(notif.settings, "SMTP_URL", "", raising=False)
    r = client.post("/api/export/preview/email", headers=admin_headers,
                    json=_preview_payload(format="pdf"))
    assert r.status_code == 503, r.text
    assert "not configured" in r.json()["detail"].lower()


def test_relay_failure_surfaces_as_502(client, admin_headers, monkeypatch):
    import app.services.notifications as notif
    monkeypatch.setattr(notif.settings, "SMTP_URL", "smtp://user:pw@mail.test:587",
                        raising=False)

    def _boom(msg, url):
        raise OSError("mailbox unavailable")
    monkeypatch.setattr(notif, "_deliver", _boom)
    r = client.post("/api/export/preview/email", headers=admin_headers,
                    json=_preview_payload(format="pdf"))
    assert r.status_code == 502, r.text
    assert "could not be sent" in r.json()["detail"].lower()
