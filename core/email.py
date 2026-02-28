"""
NSO Email Service — SMTP-based email delivery with templates.

Handles: verification emails, password reset, invoice notifications,
fraud alerts, deploy status, and welcome messages.
"""
import hashlib
import hmac
import logging
import os
import secrets
import smtplib
import time
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core import db
from core.errors import NotFoundError, ValidationError

logger = logging.getLogger("setupo.email")

# Config from env
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "nso@nso.dev")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "NSO Platform")

# Token signing for verification/reset links
EMAIL_SECRET = os.environ.get("SETUPO_EMAIL_SECRET", secrets.token_hex(32))
VERIFY_EXPIRY = 86400  # 24 hours
RESET_EXPIRY = 3600    # 1 hour


def _generate_token(user_id: str, purpose: str, expiry: int) -> str:
    """Generate HMAC-signed token for email links."""
    exp = int(time.time()) + expiry
    payload = f"{user_id}:{purpose}:{exp}"
    sig = hmac.new(EMAIL_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}:{sig}"


def _verify_token(token: str, purpose: str) -> str | None:
    """Verify and decode email token. Returns user_id or None."""
    try:
        parts = token.split(":")
        if len(parts) != 4:
            return None
        user_id, tok_purpose, exp_str, sig = parts
        if tok_purpose != purpose:
            return None
        if int(exp_str) < time.time():
            return None
        payload = f"{user_id}:{tok_purpose}:{exp_str}"
        expected = hmac.new(EMAIL_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, expected):
            return None
        return user_id
    except Exception:
        return None


def _send_email(to: str, subject: str, html: str, text: str = ""):
    """Send email via SMTP. No-op if SMTP not configured."""
    if not SMTP_HOST:
        logger.warning("SMTP not configured — email to %s skipped: %s", to, subject)
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM}>"
    msg["To"] = to
    msg["Subject"] = subject

    if text:
        msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            if SMTP_PORT != 25:
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, to, msg.as_string())
        logger.info("Email sent: %s → %s", subject, to)
        return True
    except Exception as e:
        logger.error("Email send failed (%s → %s): %s", subject, to, e)
        return False


# ── Templates ─────────────────────────────────────────────────

BASE_URL = os.environ.get("NSO_BASE_URL", "https://nso.dev")


def _wrap_html(title: str, body: str) -> str:
    """Wrap content in email HTML template."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:40px 0;">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;">
  <tr><td style="background:#18181b;padding:24px 32px;">
    <span style="color:#ffffff;font-size:18px;font-weight:600;">NSO</span>
  </td></tr>
  <tr><td style="padding:32px;">
    <h2 style="margin:0 0 16px;color:#18181b;font-size:20px;">{title}</h2>
    {body}
  </td></tr>
  <tr><td style="padding:16px 32px;background:#fafafa;border-top:1px solid #e4e4e7;">
    <p style="margin:0;color:#a1a1aa;font-size:12px;">NSO Platform &mdash; nso.dev</p>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _button(url: str, text: str) -> str:
    return f"""<a href="{url}" style="display:inline-block;padding:12px 24px;background:#18181b;
color:#ffffff;text-decoration:none;border-radius:6px;font-weight:600;font-size:14px;">{text}</a>"""


# ── Email verification ────────────────────────────────────────

async def send_verification_email(user_id: str, email: str):
    """Send email verification link."""
    token = _generate_token(user_id, "verify", VERIFY_EXPIRY)

    # Store token in DB for single-use check
    await db.insert("email_tokens", {
        "id": f"et_{secrets.token_hex(8)}",
        "user_id": user_id,
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "purpose": "verify",
        "used": 0,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=VERIFY_EXPIRY),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    verify_url = f"{BASE_URL}/verify?token={token}"
    html = _wrap_html("Verify your email", f"""
    <p style="color:#52525b;line-height:1.6;">
      Welcome to NSO! Click the button below to verify your email address.
    </p>
    <p style="margin:24px 0;">{_button(verify_url, "Verify Email")}</p>
    <p style="color:#a1a1aa;font-size:13px;">
      This link expires in 24 hours. If you didn't create an account, ignore this email.
    </p>
    """)
    return _send_email(email, "Verify your NSO account", html)


async def confirm_verification(token: str) -> str:
    """Verify token and mark user as verified. Returns user_id."""
    user_id = _verify_token(token, "verify")
    if not user_id:
        raise ValidationError("Invalid or expired verification link")

    # Check single-use
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM email_tokens WHERE token_hash = ? AND purpose = 'verify' AND used = 0",
        (token_hash,),
    )
    row = await cursor.fetchone()
    if not row:
        raise ValidationError("Verification link already used or expired")

    # Mark token as used
    await d.execute("UPDATE email_tokens SET used = 1 WHERE token_hash = ?", (token_hash,))

    # Mark user as verified
    await d.execute("UPDATE users SET verified = 1 WHERE id = ?", (user_id,))
    await d.commit()

    logger.info("User verified: %s", user_id)
    return user_id


# ── Password reset ────────────────────────────────────────────

async def send_reset_email(email: str):
    """Send password reset link. Silent if user doesn't exist (security)."""
    user = await db.fetch_one("users", email=email.strip().lower())
    if not user:
        logger.info("Reset requested for unknown email: %s", email)
        return True  # Don't reveal if email exists

    token = _generate_token(user["id"], "reset", RESET_EXPIRY)

    await db.insert("email_tokens", {
        "id": f"et_{secrets.token_hex(8)}",
        "user_id": user["id"],
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "purpose": "reset",
        "used": 0,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=RESET_EXPIRY),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    reset_url = f"{BASE_URL}/reset-password?token={token}"
    html = _wrap_html("Reset your password", f"""
    <p style="color:#52525b;line-height:1.6;">
      We received a request to reset your password. Click below to set a new one.
    </p>
    <p style="margin:24px 0;">{_button(reset_url, "Reset Password")}</p>
    <p style="color:#a1a1aa;font-size:13px;">
      This link expires in 1 hour. If you didn't request this, ignore this email.
    </p>
    """)
    return _send_email(email, "Reset your NSO password", html)


async def confirm_reset(token: str, new_password: str) -> str:
    """Verify reset token and set new password. Returns user_id."""
    from server.auth.jwt import hash_password

    user_id = _verify_token(token, "reset")
    if not user_id:
        raise ValidationError("Invalid or expired reset link")

    if len(new_password) < 6:
        raise ValidationError("Password must be at least 6 characters")

    # Single-use check
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    d = await db.get_db()
    cursor = await d.execute(
        "SELECT * FROM email_tokens WHERE token_hash = ? AND purpose = 'reset' AND used = 0",
        (token_hash,),
    )
    row = await cursor.fetchone()
    if not row:
        raise ValidationError("Reset link already used or expired")

    # Mark used
    await d.execute("UPDATE email_tokens SET used = 1 WHERE token_hash = ?", (token_hash,))

    # Invalidate all other reset tokens for this user
    await d.execute(
        "UPDATE email_tokens SET used = 1 WHERE user_id = ? AND purpose = 'reset' AND used = 0",
        (user_id,),
    )

    # Set new password
    pw_hash = hash_password(new_password)
    await d.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
    await d.commit()

    logger.info("Password reset completed: %s", user_id)
    return user_id


# ── Notification emails ───────────────────────────────────────

async def send_welcome(email: str, name: str):
    """Send welcome email after verification."""
    html = _wrap_html(f"Welcome, {name}!", f"""
    <p style="color:#52525b;line-height:1.6;">
      Your account is verified and ready to go. Here's how to get started:
    </p>
    <ol style="color:#52525b;line-height:1.8;">
      <li>Create a project from the dashboard</li>
      <li>Set up a workspace with your code</li>
      <li>Deploy with <code style="background:#f4f4f5;padding:2px 6px;border-radius:4px;">nso ship</code></li>
    </ol>
    <p style="margin:24px 0;">{_button(BASE_URL, "Open Dashboard")}</p>
    """)
    return _send_email(email, "Welcome to NSO!", html)


async def send_invoice_notification(email: str, name: str, invoice: dict):
    """Notify user about a new invoice."""
    amount = f"${invoice.get('total_cents', 0) / 100:.2f}"
    number = invoice.get("number", "N/A")
    status = invoice.get("payment_status", "pending")

    html = _wrap_html("New Invoice", f"""
    <p style="color:#52525b;">Hi {name}, you have a new invoice:</p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;">
      <tr><td style="padding:8px 0;color:#71717a;">Invoice</td>
          <td style="padding:8px 0;font-weight:600;">{number}</td></tr>
      <tr><td style="padding:8px 0;color:#71717a;">Amount</td>
          <td style="padding:8px 0;font-weight:600;">{amount}</td></tr>
      <tr><td style="padding:8px 0;color:#71717a;">Status</td>
          <td style="padding:8px 0;font-weight:600;">{status}</td></tr>
    </table>
    <p style="margin:24px 0;">{_button(f"{BASE_URL}/#billing", "View Invoice")}</p>
    """)
    return _send_email(email, f"Invoice {number} — {amount}", html)


async def send_fraud_alert(admin_email: str, details: dict):
    """Alert admin about potential fraud."""
    count = details.get("total_issues", 0)
    html = _wrap_html("Fraud Alert", f"""
    <p style="color:#dc2626;font-weight:600;">
      The automated fraud scanner detected {count} potential issue(s).
    </p>
    <ul style="color:#52525b;line-height:1.8;">
      <li>Balance discrepancies: {details.get('balance_discrepancies', 0)}</li>
      <li>Chain violations: {details.get('chain_violations', 0)}</li>
      <li>Suspicious accounts: {details.get('suspicious_accounts', 0)}</li>
    </ul>
    <p style="margin:24px 0;">{_button("https://sonfazt.nso.dev", "Open Admin Panel")}</p>
    """)
    return _send_email(admin_email, f"[ALERT] {count} fraud issue(s) detected", html)


async def send_deploy_notification(email: str, name: str, workspace: str, status: str, version: str = ""):
    """Notify about deploy status."""
    is_success = status == "success"
    emoji = "deployed" if is_success else "failed"
    color = "#16a34a" if is_success else "#dc2626"

    html = _wrap_html(f"Deploy {emoji}: {workspace}", f"""
    <p style="color:#52525b;">Hi {name},</p>
    <p style="color:{color};font-weight:600;font-size:16px;">
      Deploy {emoji}
    </p>
    <table style="width:100%;border-collapse:collapse;margin:16px 0;">
      <tr><td style="padding:8px 0;color:#71717a;">Workspace</td>
          <td style="padding:8px 0;font-weight:600;">{workspace}</td></tr>
      <tr><td style="padding:8px 0;color:#71717a;">Version</td>
          <td style="padding:8px 0;font-weight:600;">{version or "latest"}</td></tr>
      <tr><td style="padding:8px 0;color:#71717a;">Status</td>
          <td style="padding:8px 0;font-weight:600;color:{color};">{status}</td></tr>
    </table>
    <p style="margin:24px 0;">{_button(f"{BASE_URL}/#deploy", "View Details")}</p>
    """)
    return _send_email(email, f"Deploy {emoji}: {workspace}", html)
