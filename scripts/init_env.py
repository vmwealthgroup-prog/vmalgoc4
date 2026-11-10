#!/usr/bin/env python3
"""Create .env from .env.example with freshly generated secrets. Safe to re-run: it never overwrites an existing .env."""
import base64, os, pathlib, secrets, sys

root = pathlib.Path(__file__).resolve().parents[1]; env = root / ".env"
if env.exists():
    sys.exit(".env already exists, leaving it alone (delete it to regenerate).")
fernet = base64.urlsafe_b64encode(os.urandom(32)).decode()             # valid Fernet key
vals = {"POSTGRES_PASSWORD": secrets.token_urlsafe(24), "SECRET_KEY": secrets.token_hex(32), "ENCRYPTION_KEY": fernet, "NEXTAUTH_SECRET": secrets.token_urlsafe(32)}
out = []
for line in (root / ".env.example").read_text().splitlines():
    k = line.split("=", 1)[0]
    out.append(f"{k}={vals[k]}" if k in vals and line.strip() == f"{k}=" else line)
env.write_text("\n".join(out) + "\n"); env.chmod(0o600)
print("Wrote .env (mode 600). Back up ENCRYPTION_KEY: without it, saved broker API keys cannot be decrypted.")
print("Next: set DOMAIN and ADMIN_EMAIL in .env, then:  docker compose up -d --build")
