import os
from flask import Flask, render_template, request, jsonify
import mysql.connector
import google.genai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ===== GEMINI API KEY =====
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    # Ensure you have GEMINI_API_KEY in your .env file
    print("WARNING: GEMINI_API_KEY not found in environment variables.")

client = google.genai.Client(api_key=api_key)

# ===== MySQL Connection =====
db_config = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "ai_expense_tracker")
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

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

        sql = "INSERT INTO expenses (amount, category, description) VALUES (%s, %s, %s)"
        cursor.execute(sql, (amount, category, description))
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"message": "Expense added", "category": category})

    except Exception as e:
        print("DB Error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/get_expenses", methods=["GET"])
def get_expenses():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM expenses ORDER BY date DESC")
        expenses = cursor.fetchall()
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
        cursor.execute("DELETE FROM expenses WHERE id = %s", (expense_id,))
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
        cursor = conn.cursor(dictionary=True) # Return results as dictionaries
        
        # Get total summary
        cursor.execute("SELECT SUM(amount) as total, COUNT(*) as count FROM expenses")
        summary = cursor.fetchone()
        
        # Get recent expenses
        cursor.execute("SELECT amount, category, description, date FROM expenses ORDER BY date DESC LIMIT 10")
        expenses = cursor.fetchall()
        
        cursor.close()
        conn.close()

        prompt = f"""
        You are a financial assistant.
        
        Expense summary:
        - Total spent: {summary['total'] if summary['total'] else 0}
        - Number of expenses: {summary['count']}
        
        Recent expenses (last 10):
        {expenses}
        
        Answer the following question clearly and concisely based on the data provided: {question}
        If the data is empty, tell the user to add some expenses first.
        """

        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=prompt,
            )
        except Exception as e:
            error_str = str(e)
            if "RESOURCE_EXHAUSTED" in error_str:
                return jsonify({
                    "answer": "AI limit reached. Please wait a bit or try again later."
                }), 429
            if "API_KEY_INVALID" in error_str or "INVALID_ARGUMENT" in error_str:
                return jsonify({
                    "answer": "Invalid API key. Please check your .env file and ensure GEMINI_API_KEY is correct."
                }), 400
            if "NOT_FOUND" in error_str:
                return jsonify({
                    "answer": "The AI model was not found. Please contact support."
                }), 404
            raise

        if response and response.text:
            answer = response.text.strip()
        else:
            answer = "I'm sorry, I couldn't generate a response. Please try again."

        return jsonify({"answer": answer})
    except Exception as e:
        print("AI/DB Error:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run()
