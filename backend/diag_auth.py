"""
diag_auth.py — Authentication diagnostic script.

Run from the project root:

    docker compose exec backend python diag_auth.py

Reads the database. Writes nothing.
Does not modify application code or database state.
"""

import sys

# ---------------------------------------------------------------------------
# App modules — imported after Docker sets the environment variables,
# so no manual .env loading is needed when running inside the container.
# ---------------------------------------------------------------------------
from app.config import get_settings
from app.database import SessionLocal
from app.models.user import User
from app.core.security import verify_password

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LOOKUP_EMAIL  = "test@example.com"
TEST_PASSWORD = "Password123!"
SEP           = "─" * 64

settings = get_settings()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def result(label: str, value: object) -> None:
    print(f"  {label:<28} {value}")


# ---------------------------------------------------------------------------
# Main diagnostic
# ---------------------------------------------------------------------------

section("ENVIRONMENT")
result("DATABASE_URL", settings.DATABASE_URL)

db = SessionLocal()

try:
    # ── STEP 1: Email lookup ────────────────────────────────────────────────
    section("STEP 1 — EMAIL LOOKUP")
    result("Querying for", repr(LOOKUP_EMAIL))

    user = db.query(User).filter(User.email == LOOKUP_EMAIL).first()

    if user is None:
        result("Result", "FAIL — no row found")

        # Scan every stored email to reveal case or encoding differences
        print()
        all_rows = db.query(User.email).all()

        if not all_rows:
            result("users table", "EMPTY — no users registered")
        else:
            print(f"  All emails currently in users table:")
            for (stored_email,) in all_rows:
                case_match = stored_email.lower() == LOOKUP_EMAIL.lower()
                flag = "  ← case-insensitive match" if case_match else ""
                print(f"    {stored_email!r}{flag}")

        section("CONCLUSION")
        print("  EMAIL LOOKUP FAILURE")
        print()
        print("  The users table has no row where email = 'test@example.com'.")
        print("  Possible causes:")
        print("    1. The user was never registered in this PostgreSQL instance.")
        print("    2. The email was stored with different casing (EmailStr")
        print("       normalises on registration; login lookup is case-sensitive).")
        print("    3. The user was registered in a different database or container.")
        sys.exit(0)

    result("Result", "OK — user found")

    # ── STEP 2: Stored email forensics ─────────────────────────────────────
    section("STEP 2 — STORED EMAIL")
    result("repr", repr(user.email))
    result("length (chars)", len(user.email))
    result("bytes", user.email.encode("utf-8"))

    if user.email != LOOKUP_EMAIL:
        print()
        print("  WARNING: stored email differs from the query input.")
        result("  Query used", repr(LOOKUP_EMAIL))
        result("  Stored value", repr(user.email))

    # ── STEP 3: Stored hash forensics ──────────────────────────────────────
    section("STEP 3 — STORED HASH")
    result("repr", repr(user.hashed_password))
    result("length (chars)", f"{len(user.hashed_password)}  (bcrypt is always 60)")
    result("prefix", repr(user.hashed_password[:7]))
    result("expected prefix", "'$2b$12$'")

    if not user.hashed_password.startswith("$2"):
        print()
        print("  ERROR: stored value does not look like a bcrypt hash.")
        print("  The column may contain a plaintext password or a corrupted value.")

    if len(user.hashed_password) != 60:
        print()
        print(f"  WARNING: expected 60 chars, got {len(user.hashed_password)}.")

    # ── STEP 4: verify_password ────────────────────────────────────────────
    section("STEP 4 — verify_password")
    print(f"  Calling: verify_password({TEST_PASSWORD!r}, stored_hash)")
    print()

    try:
        match = verify_password(TEST_PASSWORD, user.hashed_password)

        result("Result", "PASS ✓" if match else "FAIL ✗")

        if match:
            section("CONCLUSION")
            print("  AUTHENTICATION FLOW BUG")
            print()
            print("  bcrypt verification succeeded for the correct credentials.")
            print("  The hash and password are consistent. The failure is NOT in")
            print("  security.py, auth_service.py, or the database layer.")
            print()
            print("  Likely location of the bug:")
            print("    - The request reaching /auth/login has different credentials")
            print("      than expected (e.g. wrong field name, encoding issue in client).")
            print("    - Email normalisation gap: EmailStr normalises the email at")
            print("      registration; OAuth2PasswordRequestForm.username is a raw str")
            print("      at login, so mixed-case input produces a lookup mismatch.")
        else:
            section("CONCLUSION")
            print("  PASSWORD HASH MISMATCH")
            print()
            print(f"  verify_password returned False for password {TEST_PASSWORD!r}.")
            print("  The hash stored in the database does not correspond to this password.")
            print()
            print("  Possible causes:")
            print("    1. A different password was used during registration.")
            print("       (Swagger /docs has no confirm-password field.)")
            print("    2. The hash was stored before the passlib→bcrypt migration")
            print("       and the formats are incompatible.")
            print("    3. The hash column was overwritten or corrupted.")

    except Exception as exc:
        print(f"  EXCEPTION: {type(exc).__name__}: {exc}")

        section("CONCLUSION")
        print("  VERIFICATION EXCEPTION")
        print()
        print(f"  verify_password raised {type(exc).__name__} instead of returning bool.")
        print("  Possible causes:")
        print("    - The stored hash is not a valid bcrypt string.")
        print("    - A type mismatch: hashed_password is not a str (check column type).")
        print("    - bcrypt library version incompatibility.")

finally:
    db.close()

print(f"\n{SEP}\n")
