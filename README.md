# 💸 SplitMate – Smart Expense Splitter

SplitMate is a full-stack web application designed to simplify group expense management.
It allows users to create groups, add shared expenses, and automatically calculate optimized settlements — reducing the number of transactions required.

🚀 **Live Demo:** https://shipra.pythonanywhere.com

---

## ✨ Features

### 👥 User & Group Management

* User signup & login system
* Create and join groups using invite codes
* Share group links for easy collaboration

### 💸 Expense Tracking

* Add expenses with:

  * payer
  * amount
  * category (Food, Travel, etc.)
  * description
* Select participants involved in each expense

### ⚖️ Smart Balances

* Automatically calculates:

  * who owes whom
  * how much each person should pay/receive

### 🤝 Optimized Settlements (DSA Logic)

* Minimizes number of transactions using balance simplification
* Outputs clean settlements like:

  * “A pays B ₹200”

### 📊 Analytics Dashboard

* Category-wise expense breakdown
* Monthly spending visualization (Chart.js)

### 🔔 Notifications

* Shows:

  * “You owe ₹X”
  * “You are owed ₹X”

### 💳 Mock UPI Payments

* “Pay via UPI” button (simulation)
* Mark settlements as paid

### 📁 Session History

* Stores past group sessions
* Displays complete expense logs

### 🧾 Edit/Delete Expenses

* Modify or remove expenses anytime

---

## 🛠️ Tech Stack

* **Frontend:** HTML, CSS (Custom UI)
* **Backend:** Flask (Python)
* **Database:** SQLite
* **Charts:** Chart.js
* **Deployment:** PythonAnywhere

---

## 🧠 Key Concepts Used

* Flask routing & templating (Jinja2)
* Session-based authentication
* Database design & queries (SQLite)
* Graph-based settlement optimization
* REST-like route handling
* Dynamic UI rendering

---

## 📂 Project Structure

```
Splitmate-Modified-version/
│
├── app.py
├── requirements.txt
├── splitmate.db
│
├── templates/
│   ├── add_expense.html
│   ├── analytics.html
│   ├── balances.html
│   ├── base.html
│   ├── create_group.html
│   ├── dashboard.html
│   ├── edit_expense.html
│   ├── group_dashboard.html
│   ├── home.html
│   ├── join_group.html
│   ├── login.html
│   ├── settlements.html
│   ├── signup.html
│   └── view_expenses.html
│
├── static/
│   └── style.css

...

---

## 🚀 How to Run Locally

```bash
git clone https://github.com/your-username/splitmate_v2.git
cd splitmate_v2
python3 -m venv myvenv
source myvenv/bin/activate
pip install -r requirements.txt
python app.py
```

---

## 💡 Future Improvements

* Real UPI integration
* Mobile responsive UI
* Push notifications
* Multi-currency support
* Cloud database (PostgreSQL)

---

## 👩‍💻 Author

**Shipra Rathi**
Computer Science Student | Full-Stack Developer

---

## ⭐ Why This Project Stands Out

* Real-world problem solving
* Full-stack implementation
* DSA (graph-based settlement optimization)
* Live deployed application
* Scalable architecture

---

If you like this project, feel free to ⭐ the repo!
