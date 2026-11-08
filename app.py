import os
import secrets
import smtplib
from email.message import EmailMessage
from datetime import datetime, date
from functools import wraps
from io import BytesIO
from urllib.parse import urljoin, urlparse

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func, UniqueConstraint
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

app = Flask(__name__, instance_path="/tmp/instance")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-development-secret")
database_url = os.environ.get("DATABASE_URL", "sqlite:///fixflow.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
csrf = CSRFProtect(app)


# ------------------------------ DATABASE SCHEMA ------------------------------

class Organization(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class User(UserMixin, db.Model):
    __table_args__ = (UniqueConstraint("organization_id", "enrollment_number", name="uq_user_org_enrollment"),)
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="member", nullable=False)
    account_type = db.Column(db.String(20), default="Other", nullable=False)
    enrollment_number = db.Column(db.String(40), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    organization = db.relationship("Organization")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    creator = db.relationship("User", foreign_keys=[created_by])


class TeamMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    member_role = db.Column(db.String(20), default="member", nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_user"),)
    team = db.relationship("Team", backref=db.backref("team_members", lazy=True))
    user = db.relationship("User")


class Invitation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("team.id"), nullable=True, index=True)
    invite_type = db.Column(db.String(20), nullable=False, default="connection")
    status = db.Column(db.String(20), nullable=False, default="pending")
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)
    sender = db.relationship("User", foreign_keys=[sender_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])
    team = db.relationship("Team")


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    scope = db.Column(db.String(20), nullable=False)  # personal or institutional
    kind = db.Column(db.String(20), nullable=False)   # income or expense
    category = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(180), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    transaction_date = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    owner = db.relationship("User")


class Meeting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    agenda = db.Column(db.Text)
    location = db.Column(db.String(160))
    meeting_at = db.Column(db.DateTime, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    creator = db.relationship("User")


class Connection(db.Model):
    """A private contact saved by an individual workspace user."""
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(160))
    enrollment_number = db.Column(db.String(40))
    institution = db.Column(db.String(160), nullable=False)
    connection_type = db.Column(db.String(30), nullable=False, default="Friend")
    notes = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    owner = db.relationship("User", foreign_keys=[user_id])


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    message = db.Column(db.String(240), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    action = db.Column(db.String(220), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ------------------------------ HELPERS ------------------------------

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def log_activity(action):
    db.session.add(ActivityLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action=action
    ))


def notify_user(user_id, message):
    db.session.add(Notification(user_id=user_id, message=message))


def send_invitation_email(recipient, sender, invitation, kind, team_name=None):
    """Send mail when SMTP is configured; in-app invitation remains available otherwise."""
    host = os.environ.get("MAIL_SERVER")
    username = os.environ.get("MAIL_USERNAME")
    password = os.environ.get("MAIL_PASSWORD")
    sender_email = os.environ.get("MAIL_DEFAULT_SENDER", username or "")
    if not all([host, username, password, sender_email]):
        app.logger.warning("SMTP is not configured; invitation %s is in-app only", invitation.id)
        return False
    base_url = os.environ.get("APP_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
    url = f"{base_url}{url_for('open_invitation', token=invitation.token)}"
    subject = f"FixFlow invitation from {sender.name}"
    description = f"join the team {team_name}" if kind == "team" else "connect on FixFlow"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = recipient.email
    msg.set_content(f"{sender.name} invited you to {description}. Sign in to FixFlow to review the invitation: {url}\n\nIf you do not have a FixFlow account, register first using the email address this invitation was sent to.")
    try:
        with smtplib.SMTP(host, int(os.environ.get("MAIL_PORT", "587")), timeout=15) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        return True
    except Exception:
        app.logger.exception("Could not send invitation email")
        return False


def org_users():
    return User.query.filter_by(organization_id=current_user.organization_id).order_by(User.name).all()


@app.context_processor
def inject_globals():
    if current_user.is_authenticated:
        unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {"unread_notifications": unread}
    return {"unread_notifications": 0}


@app.template_filter("inr")
def inr(value):
    try:
        return "₹{:,.2f}".format(float(value or 0))
    except (ValueError, TypeError):
        return "₹0.00"


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


# ------------------------------ AUTHENTICATION ------------------------------

@app.route("/")
def home():
    return redirect(url_for("dashboard")) if current_user.is_authenticated else redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        account_type = request.form.get("account_type", "").strip().title()
        institution_name = " ".join(request.form.get("organization", "").split())
        enrollment_number = request.form.get("enrollment_number", "").strip().upper()
        allowed_types = {"Student", "Faculty", "Other"}
        if account_type not in allowed_types:
            flash("Choose Student, Faculty or Other.", "error")
        elif not name or not email or not password:
            flash("Name, Gmail and password are required.", "error")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
        elif "@" not in email or len(email) > 160:
            flash("Enter a valid email address.", "error")
        elif account_type in {"Student", "Faculty"} and not institution_name:
            flash("Institution name is required for students and faculty.", "error")
        elif account_type == "Student" and not enrollment_number:
            flash("Enrollment number is required for students.", "error")
        elif account_type != "Student" and enrollment_number:
            flash("Enrollment number is only used for student accounts.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            org_name = institution_name if account_type in {"Student", "Faculty"} else f"Other / {email}"
            org = Organization.query.filter(func.lower(Organization.name) == org_name.lower()).first()
            is_new_org = org is None
            if is_new_org:
                org = Organization(name=org_name)
                db.session.add(org)
                db.session.flush()
            if account_type == "Student" and User.query.filter_by(organization_id=org.id, enrollment_number=enrollment_number).first():
                db.session.rollback()
                flash("That enrollment number is already registered at this institution.", "error")
            else:
                user = User(name=name, email=email, organization_id=org.id, role="member", account_type=account_type, enrollment_number=enrollment_number or None)
                user.set_password(password)
                db.session.add(user)
                db.session.commit()
                login_user(user)
                flash("Your FixFlow account is ready.", "success")
                return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            next_url = request.args.get("next")
            if next_url and urlparse(urljoin(request.host_url, next_url)).netloc == urlparse(request.host_url).netloc:
                return redirect(next_url)
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "error")
    return render_template("auth.html", mode="login")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ------------------------------ DASHBOARD ------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    org_id = current_user.organization_id
    org_transactions = Transaction.query.filter_by(organization_id=org_id, scope="institutional")
    personal_transactions = Transaction.query.filter_by(organization_id=org_id, user_id=current_user.id, scope="personal")

    def totals(query):
        income = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.id.in_(query.with_entities(Transaction.id).filter(Transaction.kind == "income"))
        ).scalar() or 0
        expenses = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.id.in_(query.with_entities(Transaction.id).filter(Transaction.kind == "expense"))
        ).scalar() or 0
        return float(income), float(expenses)

    org_income, org_expenses = totals(org_transactions)
    personal_income, personal_expenses = totals(personal_transactions)
    connections_count = Invitation.query.filter_by(sender_id=current_user.id, invite_type="connection", status="accepted").count() + Invitation.query.filter_by(recipient_id=current_user.id, invite_type="connection", status="accepted").count()
    upcoming_classrooms_count = Meeting.query.filter_by(organization_id=org_id).filter(
        Meeting.meeting_at >= datetime.now()
    ).count()
    classrooms = Meeting.query.filter_by(organization_id=org_id).filter(
        Meeting.meeting_at >= datetime.now()
    ).order_by(Meeting.meeting_at).limit(4).all()
    recent_activity = ActivityLog.query.filter_by(organization_id=org_id).order_by(
        ActivityLog.created_at.desc()
    ).limit(6).all()
    recent_transactions = Transaction.query.filter_by(
        organization_id=org_id, scope="institutional"
    ).order_by(Transaction.transaction_date.desc()).limit(5).all()
    monthly = []
    for month in range(1, 13):
        inc = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.organization_id == org_id, Transaction.scope == "institutional",
            Transaction.kind == "income",
            func.extract("month", Transaction.transaction_date) == month,
            func.extract("year", Transaction.transaction_date) == date.today().year
        ).scalar() or 0
        exp = db.session.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
            Transaction.organization_id == org_id, Transaction.scope == "institutional",
            Transaction.kind == "expense",
            func.extract("month", Transaction.transaction_date) == month,
            func.extract("year", Transaction.transaction_date) == date.today().year
        ).scalar() or 0
        monthly.append({"income": float(inc), "expense": float(exp)})
    return render_template(
        "dashboard.html", org_income=org_income, org_expenses=org_expenses,
        org_balance=org_income-org_expenses, personal_balance=personal_income-personal_expenses,
        connections_count=connections_count, upcoming_classrooms_count=upcoming_classrooms_count,
        classrooms=classrooms,
        activity=recent_activity, transactions=recent_transactions, monthly=monthly
    )


# ------------------------------ FINANCE ------------------------------

@app.route("/finance", methods=["GET", "POST"])
@login_required
def finance():
    if request.method == "POST":
        scope = request.form.get("scope", "personal")
        if scope not in ("personal", "institutional"):
            abort(400)
        if scope == "institutional" and current_user.role != "admin":
            abort(403)
        try:
            amount = float(request.form.get("amount", "0"))
            if amount <= 0:
                raise ValueError()
            item = Transaction(
                organization_id=current_user.organization_id,
                user_id=current_user.id, scope=scope,
                kind=request.form.get("kind", "expense"),
                category=request.form.get("category", "Other"),
                description=request.form.get("description", "").strip(),
                amount=amount, transaction_date=parse_date(request.form.get("transaction_date")) or date.today()
            )
            if item.kind not in ("income", "expense") or not item.description:
                raise ValueError()
            db.session.add(item)
            log_activity(f"Added {scope} {item.kind}: {item.description}")
            db.session.commit()
            flash("Transaction saved.", "success")
            return redirect(url_for("finance", scope=scope))
        except (ValueError, TypeError):
            db.session.rollback()
            flash("Enter a valid description and positive amount.", "error")

    scope = request.args.get("scope", "personal")
    if scope not in ("personal", "institutional"):
        scope = "personal"
    if scope == "institutional" and current_user.role != "admin":
        abort(403)
    query = Transaction.query.filter_by(
        organization_id=current_user.organization_id, scope=scope
    )
    if scope == "personal":
        query = query.filter_by(user_id=current_user.id)
    items = query.order_by(Transaction.transaction_date.desc(), Transaction.id.desc()).all()
    income = sum(float(x.amount) for x in items if x.kind == "income")
    expenses = sum(float(x.amount) for x in items if x.kind == "expense")
    return render_template("finance.html", items=items, scope=scope, income=income, expenses=expenses)


# ------------------------------ CLASSROOM ------------------------------

@app.route("/classroom", methods=["GET", "POST"])
@login_required
def classroom():
    if request.method == "POST":
        try:
            classroom_at = datetime.strptime(request.form.get("meeting_at"), "%Y-%m-%dT%H:%M")
            title = request.form.get("title", "").strip()
            if not title:
                raise ValueError()
            item = Meeting(
                organization_id=current_user.organization_id, title=title,
                agenda=request.form.get("agenda", "").strip(),
                location=request.form.get("location", "").strip(),
                meeting_at=classroom_at, created_by=current_user.id
            )
            db.session.add(item)
            log_activity(f"Scheduled classroom session: {title}")
            for user in org_users():
                if user.id != current_user.id:
                    notify_user(user.id, f"New classroom session scheduled: {title}")
            db.session.commit()
            flash("Classroom session scheduled.", "success")
            return redirect(url_for("classroom"))
        except ValueError:
            flash("Enter a session title and valid date/time.", "error")
    items = Meeting.query.filter_by(organization_id=current_user.organization_id).order_by(Meeting.meeting_at).all()
    return render_template("classroom.html", items=items)


@app.route("/meetings")
@login_required
def legacy_meetings_url():
    # Keep old bookmarks working while the visible module is now Classroom.
    return redirect(url_for("classroom"), code=301)


# ------------------------------ CONNECTIONS ------------------------------

@app.route("/connections", methods=["GET", "POST"])
@login_required
def connections():
    if request.method == "POST":
        connection_type = request.form.get("connection_type", "").strip().title()
        email = request.form.get("email", "").strip().lower()
        enrollment_number = request.form.get("enrollment_number", "").strip().upper()
        target = None
        if connection_type == "Student":
            if not enrollment_number:
                flash("Student enrollment number is required.", "error")
            else:
                target = User.query.filter_by(organization_id=current_user.organization_id, enrollment_number=enrollment_number, account_type="Student").first()
        elif connection_type in {"Faculty", "Other", "Team member", "Friend"}:
            if not email:
                flash("Gmail address is required.", "error")
            else:
                target = User.query.filter(func.lower(User.email) == email, User.account_type == connection_type).first()
        else:
            flash("Choose a valid connection type.", "error")
        if target:
            if target.id == current_user.id:
                flash("You cannot invite your own account.", "error")
            elif Invitation.query.filter_by(sender_id=current_user.id, recipient_id=target.id, invite_type="connection", status="pending").first():
                flash("A connection invitation is already pending.", "error")
            elif Invitation.query.filter_by(sender_id=target.id, recipient_id=current_user.id, invite_type="connection", status="accepted").first() or Invitation.query.filter_by(sender_id=current_user.id, recipient_id=target.id, invite_type="connection", status="accepted").first():
                flash("You are already connected.", "error")
            else:
                invitation = Invitation(sender_id=current_user.id, recipient_id=target.id, invite_type="connection", token=secrets.token_urlsafe(32))
                db.session.add(invitation)
                notify_user(target.id, f"{current_user.name} invited you to connect on FixFlow.")
                db.session.commit()
                email_sent = send_invitation_email(target, current_user, invitation, "connection")
                flash("Invitation created and email sent." if email_sent else "Invitation added to their FixFlow inbox. Email delivery is not configured or failed.", "success")
                return redirect(url_for("connections"))
        elif connection_type in {"Student", "Faculty", "Other", "Team member", "Friend"} and ((connection_type == "Student" and enrollment_number) or (connection_type != "Student" and email)):
            flash("No matching registered FixFlow account was found. Ask them to register with these details first.", "error")
    incoming = Invitation.query.filter_by(recipient_id=current_user.id, invite_type="connection").order_by(Invitation.created_at.desc()).all()
    outgoing = Invitation.query.filter_by(sender_id=current_user.id, invite_type="connection").order_by(Invitation.created_at.desc()).all()
    accepted = [i for i in incoming + outgoing if i.status == "accepted"]
    items = Connection.query.filter_by(user_id=current_user.id).order_by(Connection.name.asc()).all()
    return render_template("connections.html", items=items, incoming=incoming, outgoing=outgoing, accepted=accepted)

@app.route("/connections/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_connection(item_id):
    item = Connection.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash("Connection removed.", "success")
    return redirect(url_for("connections"))


# ------------------------------ TEAM ------------------------------

@app.route("/team", methods=["GET", "POST"])
@login_required
def team():
    if request.method == "POST":
        action = request.form.get("action", "create_team")
        if action == "create_team":
            team_name = request.form.get("team_name", "").strip()
            if not team_name:
                flash("Enter a team name.", "error")
            else:
                new_team = Team(name=team_name, created_by=current_user.id)
                db.session.add(new_team)
                db.session.flush()
                db.session.add(TeamMember(team_id=new_team.id, user_id=current_user.id, member_role="leader"))
                db.session.commit()
                flash("Team created. You are its leader.", "success")
                return redirect(url_for("team"))
        elif action == "invite":
            team_id = request.form.get("team_id", type=int)
            selected_team = Team.query.filter_by(id=team_id, created_by=current_user.id).first()
            email = request.form.get("email", "").strip().lower()
            enrollment_number = request.form.get("enrollment_number", "").strip().upper()
            invite_type = request.form.get("invite_type", "Other").strip().title()
            target = None
            if not selected_team:
                flash("Only the team leader can invite members.", "error")
            elif invite_type == "Student" and enrollment_number:
                target = User.query.filter_by(organization_id=current_user.organization_id, enrollment_number=enrollment_number, account_type="Student").first()
            elif invite_type != "Student" and email:
                target = User.query.filter(func.lower(User.email) == email, User.account_type == invite_type).first()
            else:
                flash("Provide the required student enrollment number or Gmail address.", "error")
            if target:
                exists = TeamMember.query.filter_by(team_id=selected_team.id, user_id=target.id).first()
                pending = Invitation.query.filter_by(team_id=selected_team.id, recipient_id=target.id, status="pending").first()
                if target.id == current_user.id or exists or pending:
                    flash("That person is already in the team or has a pending invitation.", "error")
                else:
                    inv = Invitation(sender_id=current_user.id, recipient_id=target.id, team_id=selected_team.id, invite_type="team", token=secrets.token_urlsafe(32))
                    db.session.add(inv)
                    notify_user(target.id, f"{current_user.name} invited you to join team {selected_team.name}.")
                    db.session.commit()
                    email_sent = send_invitation_email(target, current_user, inv, "team", selected_team.name)
                    flash("Team invitation created and email sent." if email_sent else "Team invitation added to their FixFlow inbox. Email delivery is not configured or failed.", "success")
                    return redirect(url_for("team"))
            elif selected_team and ((invite_type == "Student" and enrollment_number) or (invite_type != "Student" and email)):
                flash("No matching registered FixFlow account was found.", "error")
    my_teams = Team.query.join(TeamMember).filter(TeamMember.user_id == current_user.id).order_by(Team.created_at.desc()).all()
    pending_invites = Invitation.query.filter_by(recipient_id=current_user.id, invite_type="team", status="pending").all()
    sent_team_invites = Invitation.query.filter_by(sender_id=current_user.id, invite_type="team").order_by(Invitation.created_at.desc()).all()
    return render_template("team.html", members=org_users(), teams=my_teams, pending_invites=pending_invites, sent_team_invites=sent_team_invites)


@app.route("/invite/<token>")
@login_required
def open_invitation(token):
    invitation = Invitation.query.filter_by(token=token, recipient_id=current_user.id).first_or_404()
    if invitation.invite_type == "team":
        return redirect(url_for("team"))
    return redirect(url_for("connections"))


@app.route("/invitations/<int:invitation_id>/<decision>", methods=["POST"])
@login_required
def respond_invitation(invitation_id, decision):
    if decision not in {"accept", "reject"}:
        abort(404)
    invitation = Invitation.query.filter_by(id=invitation_id, recipient_id=current_user.id, status="pending").first_or_404()
    invitation.status = "accepted" if decision == "accept" else "rejected"
    invitation.responded_at = datetime.utcnow()
    if decision == "accept" and invitation.invite_type == "team" and invitation.team_id:
        if not TeamMember.query.filter_by(team_id=invitation.team_id, user_id=current_user.id).first():
            db.session.add(TeamMember(team_id=invitation.team_id, user_id=current_user.id, member_role="member"))
        notify_user(invitation.sender_id, f"{current_user.name} accepted your invitation to join {invitation.team.name}.")
    elif decision == "accept":
        notify_user(invitation.sender_id, f"{current_user.name} accepted your connection invitation.")
    else:
        notify_user(invitation.sender_id, f"{current_user.name} declined your invitation.")
    db.session.commit()
    flash("Invitation " + ("accepted." if decision == "accept" else "rejected."), "success")
    return redirect(url_for("team" if invitation.invite_type == "team" else "connections"))

# ------------------------------ NOTIFICATIONS & ACTIVITY ------------------------------

@app.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    for item in items:
        item.is_read = True
    db.session.commit()
    invitations = Invitation.query.filter_by(recipient_id=current_user.id, status="pending").order_by(Invitation.created_at.desc()).all()
    sent_invitations = Invitation.query.filter_by(sender_id=current_user.id).order_by(Invitation.created_at.desc()).limit(30).all()
    return render_template("notifications.html", items=items, invitations=invitations, sent_invitations=sent_invitations)


@app.route("/activity")
@login_required
def activity():
    items = ActivityLog.query.filter_by(organization_id=current_user.organization_id).order_by(ActivityLog.created_at.desc()).limit(100).all()
    return render_template("activity.html", items=items)


# ------------------------------ REPORTS / PDF ------------------------------

@app.route("/reports")
@login_required
def reports():
    return render_template("reports.html")


@app.route("/reports/finance.pdf")
@login_required
def finance_pdf():
    scope = request.args.get("scope", "personal")
    if scope not in ("personal", "institutional"):
        abort(400)
    if scope == "institutional" and current_user.role != "admin":
        abort(403)
    query = Transaction.query.filter_by(organization_id=current_user.organization_id, scope=scope)
    if scope == "personal":
        query = query.filter_by(user_id=current_user.id)
    items = query.order_by(Transaction.transaction_date.desc()).all()

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 55
    pdf.setTitle("FixFlow Finance Report")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(48, y, "FixFlow Workspace")
    y -= 25
    pdf.setFont("Helvetica", 11)
    pdf.drawString(48, y, f"{scope.title()} Finance Report | {current_user.organization.name}")
    y -= 28
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(48, y, "DATE")
    pdf.drawString(130, y, "TYPE")
    pdf.drawString(205, y, "CATEGORY / DESCRIPTION")
    pdf.drawRightString(width - 48, y, "AMOUNT")
    y -= 12
    pdf.line(48, y, width - 48, y)
    y -= 18
    total_income = total_expense = 0
    for item in items:
        if y < 65:
            pdf.showPage()
            y = height - 55
        amount = float(item.amount)
        if item.kind == "income":
            total_income += amount
        else:
            total_expense += amount
        pdf.setFont("Helvetica", 8)
        pdf.drawString(48, y, item.transaction_date.strftime("%d %b %Y"))
        pdf.drawString(130, y, item.kind.title())
        label = f"{item.category}: {item.description}"[:55]
        pdf.drawString(205, y, label)
        pdf.drawRightString(width - 48, y, f"INR {amount:,.2f}")
        y -= 17
    y -= 8
    pdf.line(48, y, width - 48, y)
    y -= 22
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(48, y, f"Income: INR {total_income:,.2f}")
    y -= 17
    pdf.drawString(48, y, f"Expenses: INR {total_expense:,.2f}")
    y -= 17
    pdf.drawString(48, y, f"Net: INR {total_income-total_expense:,.2f}")
    pdf.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f"fixflow-{scope}-finance-report.pdf", mimetype="application/pdf")


# ------------------------------ ERROR HANDLERS / STARTUP ------------------------------

@app.errorhandler(403)
def forbidden(_):
    return render_template("error.html", code=403, message="You do not have permission to access this page."), 403


@app.errorhandler(404)
def not_found(_):
    return render_template("error.html", code=404, message="The page or record you requested could not be found."), 404


with app.app_context():
    db.create_all()
    # Add profile columns and the per-institution enrollment uniqueness rule safely.
    from sqlalchemy import inspect
    user_columns = {column["name"] for column in inspect(db.engine).get_columns("user")}
    connection_columns = {column["name"] for column in inspect(db.engine).get_columns("connection")}
    with db.engine.begin() as connection:
        if "account_type" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE user ADD COLUMN account_type VARCHAR(20) NOT NULL DEFAULT 'Other'")
        if "enrollment_number" not in user_columns:
            connection.exec_driver_sql("ALTER TABLE user ADD COLUMN enrollment_number VARCHAR(40)")
        if "enrollment_number" not in connection_columns:
            connection.exec_driver_sql("ALTER TABLE connection ADD COLUMN enrollment_number VARCHAR(40)")
        try:
            connection.exec_driver_sql('CREATE UNIQUE INDEX IF NOT EXISTS uq_user_org_enrollment ON "user" (organization_id, enrollment_number) WHERE enrollment_number IS NOT NULL')
        except Exception:
            # Do not destroy legacy records; log any duplicate data that blocks the index.
            app.logger.exception("Could not create unique enrollment index; resolve duplicate enrollment numbers.")

if __name__ == "__main__":
    app.run(debug=True)
