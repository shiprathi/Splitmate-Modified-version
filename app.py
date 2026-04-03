from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "splitmate_v2_secret"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "splitmate.db")


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            invite_code TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            action_text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            payer_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups_table(id),
            FOREIGN KEY (payer_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expense_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (expense_id) REFERENCES expenses(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups_table(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settlement_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            from_user TEXT NOT NULL,
            to_user TEXT NOT NULL,
            amount REAL NOT NULL,
            paid_amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)

    conn.commit()
    conn.close()


def generate_invite_code(length=8):
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


def log_activity(group_id, action_text):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO activity_logs (group_id, action_text, created_at)
        VALUES (?, ?, datetime('now'))
    """, (group_id, action_text))

    conn.commit()
    conn.close()


def get_group_activities(group_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT action_text, created_at
        FROM activity_logs
        WHERE group_id = ?
        ORDER BY id DESC
        LIMIT 10
    """, (group_id,))

    activities = cursor.fetchall()
    conn.close()
    return activities


def get_group_expenses(group_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT expenses.id, expenses.group_id, expenses.payer_id, expenses.amount,
               expenses.description, expenses.category, expenses.created_at,
               users.username AS payer_name
        FROM expenses
        JOIN users ON expenses.payer_id = users.id
        WHERE expenses.group_id = ?
        ORDER BY expenses.id DESC
    """, (group_id,))
    expenses = cursor.fetchall()

    full_expenses = []

    for exp in expenses:
        cursor.execute("""
            SELECT users.id, users.username
            FROM expense_participants
            JOIN users ON expense_participants.user_id = users.id
            WHERE expense_participants.expense_id = ?
        """, (exp["id"],))
        participants = cursor.fetchall()

        expense_dict = dict(exp)
        expense_dict["participants"] = participants
        full_expenses.append(expense_dict)

    conn.close()
    return full_expenses


def get_completed_settlements(group_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT from_user, to_user, amount, paid_amount
        FROM settlement_status
        WHERE group_id = ? AND status = 'paid'
    """, (group_id,))

    completed = cursor.fetchall()
    conn.close()
    return completed


def apply_paid_settlements_to_balances(group_id, balances):
    completed_settlements = get_completed_settlements(group_id)

    for settlement in completed_settlements:
        from_user = settlement["from_user"]
        to_user = settlement["to_user"]
        amount = round(settlement["amount"], 2)

        if from_user in balances:
            balances[from_user] += amount

        if to_user in balances:
            balances[to_user] -= amount

    return balances


def calculate_group_balances(group_id):
    expenses = get_group_expenses(group_id)
    balances = {}

    for exp in expenses:
        payer_name = exp["payer_name"]
        amount = exp["amount"]
        participants = exp["participants"]

        if not participants:
            continue

        split = amount / len(participants)

        for participant in participants:
            username = participant["username"]
            balances[username] = balances.get(username, 0) - split

        balances[payer_name] = balances.get(payer_name, 0) + amount

    balances = {name: round(value, 2) for name, value in balances.items()}
    balances = apply_paid_settlements_to_balances(group_id, balances)

    final_balances = {}
    for name, value in balances.items():
        rounded_value = round(value, 2)
        if rounded_value != 0:
            final_balances[name] = rounded_value

    return final_balances


def get_settlement_payment_map(group_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT from_user, to_user, amount, paid_amount, status
        FROM settlement_status
        WHERE group_id = ?
    """, (group_id,))
    rows = cursor.fetchall()

    conn.close()

    payment_map = {}
    for row in rows:
        key = (row["from_user"], row["to_user"], round(row["amount"], 2))
        payment_map[key] = {
            "paid_amount": round(row["paid_amount"], 2),
            "status": row["status"]
        }

    return payment_map


def calculate_group_settlements(group_id):
    balances = calculate_group_balances(group_id)

    creditors = []
    debtors = []

    for person, balance in balances.items():
        if balance > 0:
            creditors.append([person, round(balance, 2)])
        elif balance < 0:
            debtors.append([person, round(-balance, 2)])

    settlements = []
    i = 0
    j = 0

    while i < len(debtors) and j < len(creditors):
        debtor_name, debt_amt = debtors[i]
        creditor_name, credit_amt = creditors[j]

        pay = min(debt_amt, credit_amt)
        original_amount = round(pay, 2)

        settlements.append({
            "from": debtor_name,
            "to": creditor_name,
            "amount": original_amount
        })

        debtors[i][1] = round(debt_amt - pay, 2)
        creditors[j][1] = round(credit_amt - pay, 2)

        if debtors[i][1] == 0:
            i += 1
        if creditors[j][1] == 0:
            j += 1

    payment_map = get_settlement_payment_map(group_id)

    updated_settlements = []
    for s in settlements:
        key = (s["from"], s["to"], round(s["amount"], 2))

        if key in payment_map:
            paid_amount = payment_map[key]["paid_amount"]
            remaining_amount = round(s["amount"] - paid_amount, 2)

            if remaining_amount > 0:
                s["paid_amount"] = paid_amount
                s["remaining_amount"] = remaining_amount
                updated_settlements.append(s)
        else:
            s["paid_amount"] = 0
            s["remaining_amount"] = s["amount"]
            updated_settlements.append(s)

    return updated_settlements


def get_settlement_summary(group_id):
    balances = calculate_group_balances(group_id)
    settlements = calculate_group_settlements(group_id)

    creditors = [person for person, amount in balances.items() if amount > 0]
    debtors = [person for person, amount in balances.items() if amount < 0]

    possible_transactions = len(debtors) * len(creditors)
    optimized_transactions = len(settlements)
    transactions_saved = possible_transactions - optimized_transactions
    total_amount_settled = round(sum(item["amount"] for item in settlements), 2)

    return {
        "settlements": settlements,
        "total_transactions": optimized_transactions,
        "total_amount_settled": total_amount_settled,
        "possible_transactions": possible_transactions,
        "optimized_transactions": optimized_transactions,
        "transactions_saved": transactions_saved
    }


def get_user_notifications(user_id, username):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT groups_table.id, groups_table.group_name
        FROM groups_table
        JOIN group_members ON groups_table.id = group_members.group_id
        WHERE group_members.user_id = ?
    """, (user_id,))
    groups = cursor.fetchall()
    conn.close()

    notifications = []

    for group in groups:
        settlements = calculate_group_settlements(group["id"])

        for s in settlements:
            amount_to_show = s.get("remaining_amount", s["amount"])

            if s["from"] == username:
                notifications.append(
                    f'You owe ₹{amount_to_show} to {s["to"]} in "{group["group_name"]}"'
                )
            elif s["to"] == username:
                notifications.append(
                    f'{s["from"]} owes you ₹{amount_to_show} in "{group["group_name"]}"'
                )

    return notifications


def get_group_summary(group_id):
    expenses = get_group_expenses(group_id)

    total_expenses = len(expenses)
    total_amount = round(sum(exp["amount"] for exp in expenses), 2)

    category_totals = {}
    for exp in expenses:
        category = exp.get("category", "Other")
        category_totals[category] = category_totals.get(category, 0) + exp["amount"]

    top_category = max(category_totals, key=category_totals.get) if category_totals else "None"

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) AS member_count
        FROM group_members
        WHERE group_id = ?
    """, (group_id,))
    member_count = cursor.fetchone()["member_count"]

    conn.close()

    return {
        "member_count": member_count,
        "total_expenses": total_expenses,
        "total_amount": total_amount,
        "top_category": top_category
    }


def get_group_reminders(group_id, current_username=None):
    settlements = calculate_group_settlements(group_id)
    reminders = []

    for s in settlements:
        amount_to_show = s.get("remaining_amount", s["amount"])

        if current_username:
            if s["from"] == current_username:
                reminders.append(f'You need to pay ₹{amount_to_show} to {s["to"]}.')
            elif s["to"] == current_username:
                reminders.append(f'{s["from"]} needs to pay you ₹{amount_to_show}.')
        else:
            reminders.append(f'{s["from"]} should pay ₹{amount_to_show} to {s["to"]}.')

    return reminders


def generate_mock_upi_link(to_user, amount):
    upi_id = "splitmate@upi"
    payee_name = to_user
    return f"upi://pay?pa={upi_id}&pn={payee_name}&am={amount}&cu=INR"


def get_group_analytics_data(group_id):
    expenses = get_group_expenses(group_id)

    category_totals = {}
    monthly_totals = {}

    for exp in expenses:
        category = exp.get("category", "Other")
        amount = exp.get("amount", 0)
        created_at = exp.get("created_at", "")

        category_totals[category] = category_totals.get(category, 0) + amount

        if created_at:
            try:
                dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                month_key = dt.strftime("%b %Y")
                monthly_totals[month_key] = monthly_totals.get(month_key, 0) + amount
            except ValueError:
                pass

    return {
        "category_labels": list(category_totals.keys()),
        "category_values": list(category_totals.values()),
        "monthly_labels": list(monthly_totals.keys()),
        "monthly_values": list(monthly_totals.values())
    }


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        if not username or not email or not password:
            flash("All fields are required!", "error")
            return redirect(url_for("signup"))

        password_hash = generate_password_hash(password)

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, password_hash)
            )
            conn.commit()
            flash("Signup successful! Please login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username or email already exists!", "error")
            return redirect(url_for("signup"))
        finally:
            conn.close()

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password!", "error")
            return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT groups_table.id, groups_table.group_name, groups_table.invite_code, groups_table.created_at
        FROM groups_table
        JOIN group_members ON groups_table.id = group_members.group_id
        WHERE group_members.user_id = ?
    """, (session["user_id"],))

    groups = cursor.fetchall()
    conn.close()

    notifications = get_user_notifications(session["user_id"], session["username"])

    return render_template(
        "dashboard.html",
        username=session["username"],
        groups=groups,
        notifications=notifications
    )


@app.route("/create-group", methods=["GET", "POST"])
def create_group():
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        group_name = request.form["group_name"].strip()

        if not group_name:
            flash("Group name is required!", "error")
            return redirect(url_for("create_group"))

        invite_code = generate_invite_code()

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO groups_table (group_name, created_by, invite_code, created_at)
            VALUES (?, ?, ?, datetime('now'))
        """, (group_name, session["user_id"], invite_code))

        group_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO group_members (group_id, user_id)
            VALUES (?, ?)
        """, (group_id, session["user_id"]))

        conn.commit()
        conn.close()

        log_activity(group_id, f'{session["username"]} created the group "{group_name}"')
        flash("Group created successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("create_group.html")


@app.route("/join-group", methods=["GET", "POST"])
def join_group():
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        invite_code = request.form["invite_code"].strip()

        if not invite_code:
            flash("Invite code is required!", "error")
            return redirect(url_for("join_group"))

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM groups_table WHERE invite_code = ?", (invite_code,))
        group = cursor.fetchone()

        if not group:
            conn.close()
            flash("Invalid invite code!", "error")
            return redirect(url_for("join_group"))

        cursor.execute("""
            SELECT * FROM group_members
            WHERE group_id = ? AND user_id = ?
        """, (group["id"], session["user_id"]))

        existing_member = cursor.fetchone()

        if existing_member:
            conn.close()
            flash("You are already in this group!", "error")
            return redirect(url_for("dashboard"))

        cursor.execute("""
            INSERT INTO group_members (group_id, user_id)
            VALUES (?, ?)
        """, (group["id"], session["user_id"]))

        conn.commit()
        conn.close()

        log_activity(group["id"], f'{session["username"]} joined the group')
        flash("Joined group successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("join_group.html")


@app.route("/join-group/<invite_code>")
def join_group_by_link(invite_code):
    if "user_id" not in session:
        flash("Please login first to join the group!", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM groups_table WHERE invite_code = ?", (invite_code,))
    group = cursor.fetchone()

    if not group:
        conn.close()
        flash("Invalid invite link!", "error")
        return redirect(url_for("dashboard"))

    cursor.execute("""
        SELECT * FROM group_members
        WHERE group_id = ? AND user_id = ?
    """, (group["id"], session["user_id"]))

    existing_member = cursor.fetchone()

    if existing_member:
        conn.close()
        flash("You are already a member of this group!", "error")
        return redirect(url_for("group_dashboard", group_id=group["id"]))

    cursor.execute("""
        INSERT INTO group_members (group_id, user_id)
        VALUES (?, ?)
    """, (group["id"], session["user_id"]))

    conn.commit()
    conn.close()

    log_activity(group["id"], f'{session["username"]} joined the group using invite link')
    flash("You joined the group successfully!", "success")
    return redirect(url_for("group_dashboard", group_id=group["id"]))


@app.route("/group/<int:group_id>")
def group_dashboard(group_id):
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM groups_table WHERE id = ?", (group_id,))
    group = cursor.fetchone()

    if not group:
        conn.close()
        flash("Group not found!", "error")
        return redirect(url_for("dashboard"))

    cursor.execute("""
        SELECT users.id, users.username, users.email
        FROM users
        JOIN group_members ON users.id = group_members.user_id
        WHERE group_members.group_id = ?
    """, (group_id,))
    members = cursor.fetchall()

    cursor.execute("""
        SELECT expenses.id, expenses.amount, expenses.description, expenses.category, expenses.created_at,
               users.username AS payer_name
        FROM expenses
        JOIN users ON expenses.payer_id = users.id
        WHERE expenses.group_id = ?
        ORDER BY expenses.id DESC
    """, (group_id,))
    expenses = cursor.fetchall()

    conn.close()

    summary = get_group_summary(group_id)
    reminders = get_group_reminders(group_id, session["username"])
    activities = get_group_activities(group_id)

    return render_template(
        "group_dashboard.html",
        group=group,
        members=members,
        expenses=expenses,
        member_count=summary["member_count"],
        total_expenses=summary["total_expenses"],
        total_amount=summary["total_amount"],
        top_category=summary["top_category"],
        reminders=reminders,
        activities=activities
    )


@app.route("/group/<int:group_id>/add-expense", methods=["GET", "POST"])
def add_group_expense(group_id):
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM groups_table WHERE id = ?", (group_id,))
    group = cursor.fetchone()

    if not group:
        conn.close()
        flash("Group not found!", "error")
        return redirect(url_for("dashboard"))

    cursor.execute("""
        SELECT users.id, users.username
        FROM users
        JOIN group_members ON users.id = group_members.user_id
        WHERE group_members.group_id = ?
    """, (group_id,))
    members = cursor.fetchall()

    if request.method == "POST":
        payer_id = request.form["payer_id"]
        description = request.form["description"].strip()
        category = request.form.get("category", "Other")

        try:
            amount = float(request.form["amount"])
            if amount <= 0:
                flash("Amount must be positive!", "error")
                return redirect(url_for("add_group_expense", group_id=group_id))
        except ValueError:
            flash("Enter a valid amount!", "error")
            return redirect(url_for("add_group_expense", group_id=group_id))

        participants = request.form.getlist("participants")
        if not participants:
            flash("Select at least one participant!", "error")
            return redirect(url_for("add_group_expense", group_id=group_id))

        cursor.execute("""
            INSERT INTO expenses (group_id, payer_id, amount, description, category, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (group_id, payer_id, amount, description, category))

        expense_id = cursor.lastrowid

        for user_id in participants:
            cursor.execute("""
                INSERT INTO expense_participants (expense_id, user_id)
                VALUES (?, ?)
            """, (expense_id, user_id))

        conn.commit()
        conn.close()

        log_activity(group_id, f'{session["username"]} added an expense of ₹{amount} for "{description}"')
        flash("Expense added successfully!", "success")
        return redirect(url_for("group_dashboard", group_id=group_id))

    conn.close()
    return render_template("add_expense.html", group=group, members=members)


@app.route("/group/<int:group_id>/expenses")
def group_expenses(group_id):
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM groups_table WHERE id = ?", (group_id,))
    group = cursor.fetchone()

    if not group:
        conn.close()
        flash("Group not found!", "error")
        return redirect(url_for("dashboard"))

    conn.close()

    expenses = get_group_expenses(group_id)

    search_query = request.args.get("search", "").strip().lower()
    selected_category = request.args.get("category", "").strip()

    filtered_expenses = []

    for exp in expenses:
        matches_search = True
        matches_category = True

        if search_query:
            payer_name = exp["payer_name"].lower()
            description = exp["description"].lower()
            matches_search = search_query in payer_name or search_query in description

        if selected_category:
            matches_category = exp["category"] == selected_category

        if matches_search and matches_category:
            filtered_expenses.append(exp)

    return render_template(
        "view_expenses.html",
        group=group,
        expenses=filtered_expenses,
        search_query=search_query,
        selected_category=selected_category
    )


@app.route("/group/<int:group_id>/balances")
def group_balances(group_id):
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM groups_table WHERE id = ?", (group_id,))
    group = cursor.fetchone()

    if not group:
        conn.close()
        flash("Group not found!", "error")
        return redirect(url_for("dashboard"))

    conn.close()

    balances = calculate_group_balances(group_id)

    return render_template("balances.html", group=group, balances=balances)


@app.route("/group/<int:group_id>/settlements")
def group_settlements(group_id):
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM groups_table WHERE id = ?", (group_id,))
    group = cursor.fetchone()

    if not group:
        conn.close()
        flash("Group not found!", "error")
        return redirect(url_for("dashboard"))

    conn.close()

    summary = get_settlement_summary(group_id)
    completed_settlements = get_completed_settlements(group_id)

    settlements_with_upi = []
    for s in summary["settlements"]:
        settlement_copy = dict(s)
        settlement_copy["upi_link"] = generate_mock_upi_link(s["to"], s["amount"])
        settlements_with_upi.append(settlement_copy)

    return render_template(
        "settlements.html",
        group=group,
        settlements=settlements_with_upi,
        total_transactions=summary["total_transactions"],
        total_amount_settled=summary["total_amount_settled"],
        possible_transactions=summary["possible_transactions"],
        optimized_transactions=summary["optimized_transactions"],
        transactions_saved=summary["transactions_saved"],
        completed_settlements=completed_settlements
    )


@app.route("/group/<int:group_id>/mark-paid")
def mark_settlement_paid(group_id):
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    from_user = request.args.get("from_user")
    to_user = request.args.get("to_user")
    amount = request.args.get("amount")

    if not from_user or not to_user or not amount:
        flash("Invalid settlement details!", "error")
        return redirect(url_for("group_settlements", group_id=group_id))

    try:
        amount = round(float(amount), 2)
    except ValueError:
        flash("Invalid amount!", "error")
        return redirect(url_for("group_settlements", group_id=group_id))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM settlement_status
        WHERE group_id = ? AND from_user = ? AND to_user = ? AND amount = ?
    """, (group_id, from_user, to_user, amount))

    existing = cursor.fetchone()

    if existing:
        cursor.execute("""
            UPDATE settlement_status
            SET paid_amount = ?, status = 'paid'
            WHERE group_id = ? AND from_user = ? AND to_user = ? AND amount = ?
        """, (amount, group_id, from_user, to_user, amount))
    else:
        cursor.execute("""
            INSERT INTO settlement_status (group_id, from_user, to_user, amount, paid_amount, status)
            VALUES (?, ?, ?, ?, ?, 'paid')
        """, (group_id, from_user, to_user, amount, amount))

    conn.commit()
    conn.close()

    log_activity(group_id, f'{from_user} paid ₹{amount} to {to_user}')
    flash("Settlement marked as paid! ✅", "success")
    return redirect(url_for("group_settlements", group_id=group_id))


@app.route("/group/<int:group_id>/partial-pay", methods=["POST"])
def partial_pay_settlement(group_id):
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    from_user = request.form.get("from_user")
    to_user = request.form.get("to_user")
    amount = request.form.get("amount")
    partial_amount = request.form.get("partial_amount")

    if not from_user or not to_user or not amount or not partial_amount:
        flash("Incomplete payment details!", "error")
        return redirect(url_for("group_settlements", group_id=group_id))

    try:
        amount = round(float(amount), 2)
        partial_amount = round(float(partial_amount), 2)
    except ValueError:
        flash("Invalid payment amount!", "error")
        return redirect(url_for("group_settlements", group_id=group_id))

    if partial_amount <= 0:
        flash("Partial payment must be positive!", "error")
        return redirect(url_for("group_settlements", group_id=group_id))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT * FROM settlement_status
        WHERE group_id = ? AND from_user = ? AND to_user = ? AND amount = ?
    """, (group_id, from_user, to_user, amount))

    existing = cursor.fetchone()

    if existing:
        new_paid_amount = round(existing["paid_amount"] + partial_amount, 2)

        if new_paid_amount >= amount:
            cursor.execute("""
                UPDATE settlement_status
                SET paid_amount = ?, status = 'paid'
                WHERE group_id = ? AND from_user = ? AND to_user = ? AND amount = ?
            """, (amount, group_id, from_user, to_user, amount))
            flash("Settlement fully paid! ✅", "success")
        else:
            cursor.execute("""
                UPDATE settlement_status
                SET paid_amount = ?, status = 'pending'
                WHERE group_id = ? AND from_user = ? AND to_user = ? AND amount = ?
            """, (new_paid_amount, group_id, from_user, to_user, amount))
            flash(f"Partial payment recorded! Remaining: ₹{round(amount - new_paid_amount, 2)}", "success")
    else:
        if partial_amount >= amount:
            cursor.execute("""
                INSERT INTO settlement_status (group_id, from_user, to_user, amount, paid_amount, status)
                VALUES (?, ?, ?, ?, ?, 'paid')
            """, (group_id, from_user, to_user, amount, amount))
            flash("Settlement fully paid! ✅", "success")
        else:
            cursor.execute("""
                INSERT INTO settlement_status (group_id, from_user, to_user, amount, paid_amount, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            """, (group_id, from_user, to_user, amount, partial_amount))
            flash(f"Partial payment recorded! Remaining: ₹{round(amount - partial_amount, 2)}", "success")

    conn.commit()
    conn.close()

    log_activity(group_id, f'{from_user} recorded a partial payment of ₹{partial_amount} to {to_user}')
    return redirect(url_for("group_settlements", group_id=group_id))


@app.route("/group/<int:group_id>/delete-expense/<int:expense_id>")
def delete_group_expense(group_id, expense_id):
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM expenses WHERE id = ? AND group_id = ?", (expense_id, group_id))
    expense = cursor.fetchone()

    if not expense:
        conn.close()
        flash("Expense not found!", "error")
        return redirect(url_for("group_expenses", group_id=group_id))

    expense_amount = expense["amount"]
    expense_description = expense["description"]

    cursor.execute("DELETE FROM expense_participants WHERE expense_id = ?", (expense_id,))
    cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))

    conn.commit()
    conn.close()

    log_activity(group_id, f'{session["username"]} deleted an expense of ₹{expense_amount} for "{expense_description}"')
    flash("Expense deleted successfully!", "success")
    return redirect(url_for("group_expenses", group_id=group_id))


@app.route("/group/<int:group_id>/edit-expense/<int:expense_id>", methods=["GET", "POST"])
def edit_group_expense(group_id, expense_id):
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM groups_table WHERE id = ?", (group_id,))
    group = cursor.fetchone()

    if not group:
        conn.close()
        flash("Group not found!", "error")
        return redirect(url_for("dashboard"))

    cursor.execute("SELECT * FROM expenses WHERE id = ? AND group_id = ?", (expense_id, group_id))
    expense = cursor.fetchone()

    if not expense:
        conn.close()
        flash("Expense not found!", "error")
        return redirect(url_for("group_expenses", group_id=group_id))

    cursor.execute("""
        SELECT users.id, users.username
        FROM users
        JOIN group_members ON users.id = group_members.user_id
        WHERE group_members.group_id = ?
    """, (group_id,))
    members = cursor.fetchall()

    cursor.execute("""
        SELECT user_id FROM expense_participants WHERE expense_id = ?
    """, (expense_id,))
    participant_rows = cursor.fetchall()
    selected_participants = [row["user_id"] for row in participant_rows]

    if request.method == "POST":
        payer_id = request.form["payer_id"]
        description = request.form["description"].strip()
        category = request.form.get("category", "Other")

        try:
            amount = float(request.form["amount"])
            if amount <= 0:
                flash("Amount must be positive!", "error")
                return redirect(url_for("edit_group_expense", group_id=group_id, expense_id=expense_id))
        except ValueError:
            flash("Enter a valid amount!", "error")
            return redirect(url_for("edit_group_expense", group_id=group_id, expense_id=expense_id))

        participants = request.form.getlist("participants")
        if not participants:
            flash("Select at least one participant!", "error")
            return redirect(url_for("edit_group_expense", group_id=group_id, expense_id=expense_id))

        cursor.execute("""
            UPDATE expenses
            SET payer_id = ?, amount = ?, description = ?, category = ?
            WHERE id = ?
        """, (payer_id, amount, description, category, expense_id))

        cursor.execute("DELETE FROM expense_participants WHERE expense_id = ?", (expense_id,))
        for user_id in participants:
            cursor.execute("""
                INSERT INTO expense_participants (expense_id, user_id)
                VALUES (?, ?)
            """, (expense_id, user_id))

        conn.commit()
        conn.close()

        log_activity(group_id, f'{session["username"]} updated an expense to ₹{amount} for "{description}"')
        flash("Expense updated successfully!", "success")
        return redirect(url_for("group_expenses", group_id=group_id))

    conn.close()
    return render_template(
        "edit_expense.html",
        group=group,
        expense=expense,
        members=members,
        selected_participants=selected_participants
    )


@app.route("/group/<int:group_id>/analytics")
def group_analytics(group_id):
    if "user_id" not in session:
        flash("Please login first!", "error")
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM groups_table WHERE id = ?", (group_id,))
    group = cursor.fetchone()

    if not group:
        conn.close()
        flash("Group not found!", "error")
        return redirect(url_for("dashboard"))

    conn.close()

    analytics = get_group_analytics_data(group_id)

    return render_template(
        "analytics.html",
        group=group,
        category_labels=analytics["category_labels"],
        category_values=analytics["category_values"],
        monthly_labels=analytics["monthly_labels"],
        monthly_values=analytics["monthly_values"]
    )


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully!", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)