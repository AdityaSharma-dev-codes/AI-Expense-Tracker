import os
import sqlite3
from flask import Flask, render_template, request, jsonify
import google.genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ===== GEMINI API KEY =====
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("WARNING: GEMINI_API_KEY not found.")

client = google.genai.Client(api_key=api_key)

# ===== SQLITE DATABASE =====
DB_PATH = "expenses.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Auto-create table (NO MANUAL SQL NEEDED)
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/add_expense", methods=["POST"])
def add_expense():
    try:
        data = request.get_json()
        amount = data.get("amount")
        description = data.get("description")
        category = data.get("category", "Other")

        if not amount or not description:
            return jsonify({"error": "Amount and description are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO expenses (amount, category, description) VALUES (?, ?, ?)",
            (amount, category, description)
        )
        conn.commit()

        # Get the newly created expense to return it or just signify success
        cursor.execute("SELECT * FROM expenses WHERE id = last_insert_rowid()")
        new_expense = dict(cursor.fetchone())

        cursor.close()
        conn.close()

        return jsonify({"message": "Expense added", "expense": new_expense})

    except Exception as e:
        print("DB Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/get_expenses", methods=["GET"])
def get_expenses():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM expenses ORDER BY date DESC")
        expenses = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return jsonify(expenses)
    except Exception as e:
        print("DB Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/delete_expense/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"message": "Expense deleted"})
    except Exception as e:
        print("DB Error:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/ask_ai", methods=["POST"])
def ask_ai():
    data = request.get_json()
    question = data.get("question")

    if not question:
        return jsonify({"answer": "Please ask a question."})

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT SUM(amount), COUNT(*) FROM expenses")
        row = cursor.fetchone()
        total = row[0] if row else 0
        count = row[1] if row else 0

        cursor.execute(
            "SELECT amount, category, description, date FROM expenses ORDER BY date DESC LIMIT 10"
        )
        expenses = cursor.fetchall()

        cursor.close()
        conn.close()

        prompt = f"""
        You are a financial assistant.

        Expense summary:
        - Total spent: {total or 0}
        - Number of expenses: {count}

        Recent expenses (last 10):
        {expenses}

        Answer the following question clearly and concisely: {question}
        """

        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompt,
        )

        return jsonify({"answer": response.text.strip()})

    except Exception as e:
        print("AI Error:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
