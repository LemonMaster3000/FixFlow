# FixFlow Workspace MVP

A college-organization operations platform built with Flask, SQLAlchemy, PostgreSQL-compatible storage, Flask-Login and ReportLab.

## MVP features
- Organization creation and administrator registration
- Login/logout and password hashing
- Admin/member role separation
- Personal finance records private to their owner
- Institutional finance records restricted to administrators
- Classroom schedule for classes, lectures, tutorials and academic sessions
- Student, Faculty and Other account registration profiles
- Institution-scoped unique student enrollment numbers
- Account-to-account connection invitations with accept/reject workflow
- Teams with leader/member roles and invitations across institutions
- SMTP email invitations when configured, plus in-app invitation notifications
- Activity history
- Finance PDF exports
- Dark responsive dashboard

## Run locally

Python 3.10+ is recommended.

```bash
python -m venv .venv
```

Windows:
```powershell
.venv\Scripts\activate
```

macOS/Linux:
```bash
source .venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Set a secret key (PowerShell):
```powershell
$env:SECRET_KEY="replace-with-a-long-random-secret"
```

Run:
```bash
python app.py
```

Open http://127.0.0.1:5000

Register with Student, Faculty or Other. Student and Faculty accounts join an institution workspace using its institution name. New accounts receive the member role. Provision an institution administrator separately; do not promote a student account automatically. Create teams and invite existing FixFlow accounts from the Team page.

## Deployment

This repository includes `render.yaml`. Create a new Render web service from the repository and use the Blueprint option. Set a strong `SECRET_KEY` in the Render dashboard. For email invitations, also set `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER` and `APP_BASE_URL` as described in `UPGRADE_NOTES.md`.

The deployment uses PostgreSQL. Do not use ephemeral local SQLite storage for production data.

## Database tables
- organizations
- users
- transactions
- meetings (existing storage table used for Classroom sessions)
- connections
- notifications
- activity_logs

## Important MVP limitations
- Email invitations require SMTP environment variables; without them invitations remain in-app.
- Classroom sessions are stored and displayed but do not sync to Google/Outlook calendars.
- Invitations can only target registered accounts. Recipients must sign in to accept or reject.
- PDF export currently covers finance transactions.
- No payment gateway, bank connection, or audited accounting.
- File upload is intentionally excluded from this four-day MVP.
- New registrations do not automatically receive administrator privileges. Provision an institution administrator separately. Enrollment numbers are unique within each institution.
- Add production hardening before public launch: password reset, email verification, rate limiting, backups, audit retention policies, and stronger deployment security.

## Production deployment checks
- Set a unique, long `SECRET_KEY`.
- Confirm `DATABASE_URL` points to managed PostgreSQL.
- Test registration, login, role restrictions, finance privacy and PDF export on the deployed URL.
- Configure database backups.
