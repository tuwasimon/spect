import os
import requests
import logging
import re
import smtplib
from email.mime.text import MIMEText
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chatbot.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Define User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    chats = db.relationship('Chat', backref='user', lazy=True)

# Define Chat model
class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user_message = db.Column(db.Text, nullable=False)
    bot_response = db.Column(db.Text, nullable=False)

# Create database tables
with app.app_context():
    db.create_all()

# Load school info
SCHOOL_INFO_FILE = "school_info.txt"
if os.path.exists(SCHOOL_INFO_FILE):
    with open(SCHOOL_INFO_FILE, "r", encoding="utf-8") as file:
        school_info = file.read()
else:
    school_info = "School information not available."

# Extract car names from school_info.txt
car_name_pattern = re.compile(r'\d+\.\s*([^\n]+?)\s{2,}', re.MULTILINE)
car_names = car_name_pattern.findall(school_info)

def find_image_file(car_name):
    base = car_name.strip().replace(' ', '_').lower()
    for ext in ['jpg', 'jpeg', 'png', 'webp']:
        path = f"static/cars/{base}.{ext}"
        if os.path.exists(path):
            return f"{base}.{ext}"
    return None

CAR_IMAGES = {}
for name in car_names:
    filename = find_image_file(name)
    if filename:
        CAR_IMAGES[name.strip()] = filename

# Build a mapping from brand to a car name and image
BRAND_IMAGES = {}
for car_name in car_names:
    brand = car_name.split()[0].lower()
    if brand not in BRAND_IMAGES:
        BRAND_IMAGES[brand] = {
            "car_name": car_name,
            "filename": CAR_IMAGES[car_name]
        }

# Replace with your actual Groq API key
GROQ_API_KEY = "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"

app.secret_key = 'your_secret_key_here'  # Change this to a secure random value

# Admin credentials (for demo, use env vars or DB in production)
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD_HASH = generate_password_hash('admin123')

def send_registration_email(name, phone):
    sender = "simonsteve1076@gmail.com"
    recipient = "simonsteve1076@gmail.com"  # Change to your admin email
    subject = "New User Registration Notification"
    body = f"A new user has registered and initiated a chat with the bot.\n\nName: {name}\nPhone: {phone}"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:  # For Gmail
            server.login("simonsteve1076@gmail.com", "btzr mumz avbx wmho")
            server.sendmail(sender, recipient, msg.as_string())
    except Exception as e:
        logging.error(f"Failed to send registration email: {e}")

@app.route("/register", methods=["POST"])
def register_user():
    data = request.json
    name = data.get("name")
    phone = data.get("phone")

    if not name or not phone:
        return jsonify({"error": "Name and phone are required."}), 400

    existing_user = User.query.filter_by(phone=phone).first()
    if existing_user:
        return jsonify({"message": "User already registered."})

    new_user = User(name=name, phone=phone)
    db.session.add(new_user)
    db.session.commit()

    # Send email notification
    send_registration_email(name, phone)

    return jsonify({"message": "User registered successfully."})

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_id = data.get("user_id")
    message = data.get("message", "").lower()

    user = User.query.filter_by(phone=user_id).first()
    if not user:
        return jsonify({"error": "User not registered."}), 400

    # Address/location keywords
    location_keywords = ["address", "location", "where are you", "find sarkin mota", "where is sarkin mota", "office address"]
    if any(keyword in message for keyword in location_keywords):
        # Extract the first line from school_info.txt as the address
        address = school_info.splitlines()[0].strip()
        response = f"Our address is: {address}"
        # Save chat to database
        new_chat = Chat(user_id=user.id, user_message=message, bot_response=response)
        db.session.add(new_chat)
        db.session.commit()
        return jsonify({"response": response})

    image_url = None
    car_found = None

    # Only show image if user intent is visual
    visual_triggers = ["image", "show", "see", "picture", "photo", "display"]
    if any(trigger in message for trigger in visual_triggers):
        # Try to match any part of the car name or brand
        for car_name, filename in CAR_IMAGES.items():
            car_name_lower = car_name.lower()
            car_words = car_name_lower.split()
            if any(word in message for word in car_words) or car_words[0] in message:
                image_url = url_for('static', filename=f'cars/{filename}', _external=True)
                car_found = car_name
                break

        # If not found, try to match by brand name only
        if not image_url:
            for brand, info in BRAND_IMAGES.items():
                if brand in message:
                    image_url = url_for('static', filename=f'cars/{info["filename"]}', _external=True)
                    car_found = info["car_name"]
                    break

    if image_url:
        response = (
            f"Here is the image of {car_found}:<br>"
            f"<img src='{image_url}' alt='{car_found}' style='max-width:300px; margin-top:10px;'>"
        )
    elif any(trigger in message for trigger in visual_triggers):
        response = "Please specify which car you'd like to see an image of (e.g., 'show me Toyota Corolla 2012')."
    else:
        try:
            groq_response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama3-8b-8192",
                    "messages": [
                        {
                            "role": "system",
                            "content": f"You are a helpful assistant for Sarkin Mota. Only answer using the info below:\n\n{school_info}"
                        },
                        {"role": "user", "content": message}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 512
                }
            )

            logging.debug(f"Groq API response: {groq_response.text}")
            if groq_response.status_code == 200:
                response_json = groq_response.json()
                response = response_json["choices"][0]["message"]["content"]
                # Fallback: if bot can't answer, provide phone number
                fallback_phrases = [
                    "i don't know", "i'm not sure", "i don't have", "cannot answer", "no information", "not available"
                ]
                if any(phrase in response.lower() for phrase in fallback_phrases):
                    response += "<br><br>If you need further assistance, please call us at <b>123456789</b>."
            else:
                response = f"Error: {groq_response.status_code} - {groq_response.text}"

        except Exception as e:
            logging.error(f"Error communicating with Groq API: {e}")
            response = f"Error: {str(e)}"

    new_chat = Chat(user_id=user.id, user_message=message, bot_response=response)
    db.session.add(new_chat)
    db.session.commit()

    return jsonify({"response": response})

@app.route("/ui")
def chat_ui():
    return render_template("chat.html")

@app.route("/users", methods=["GET"])
def users():
    users = User.query.all()
    user_data = [{"id": user.id, "name": user.name, "phone": user.phone} for user in users]
    return jsonify(user_data)

@app.route("/users_page", methods=["GET"])
def users_page():
    return render_template("users.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['admin_logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('login'))

@app.route("/dashboard", methods=["GET"])
def dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    return render_template("dashboard.html")

@app.route("/user_chats/<int:user_id>", methods=["GET"])
def user_chats(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found."}), 404

    chats = Chat.query.filter_by(user_id=user_id).all()
    chat_data = [
        {
            "id": chat.id,  # <-- Make sure this is included!
            "user_message": chat.user_message,
            "bot_response": chat.bot_response
        }
        for chat in chats
    ]

    return jsonify({"user": {"name": user.name, "phone": user.phone}, "chats": chat_data})

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        username = request.form.get('username')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if username != ADMIN_USERNAME:
            return render_template('reset_password.html', error='Invalid username')
        if new_password != confirm_password:
            return render_template('reset_password.html', error='Passwords do not match')
        global ADMIN_PASSWORD_HASH
        ADMIN_PASSWORD_HASH = generate_password_hash(new_password)
        flash('Password reset successful. Please log in with your new password.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route("/delete_chat/<int:chat_id>", methods=["POST"])
def delete_chat(chat_id):
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 403
    chat = Chat.query.get(chat_id)
    if not chat:
        return jsonify({"error": "Chat not found"}), 404
    db.session.delete(chat)
    db.session.commit()
    return jsonify({"message": "Chat deleted"})

@app.route("/delete_user_chats/<int:user_id>", methods=["POST"])
def delete_user_chats(user_id):
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 403
    chats = Chat.query.filter_by(user_id=user_id).all()
    for chat in chats:
        db.session.delete(chat)
    db.session.commit()
    return jsonify({"message": "All chats deleted for user"})

@app.route("/delete_user/<int:user_id>", methods=["POST"])
def delete_user(user_id):
    if not session.get('admin_logged_in'):
        return jsonify({"error": "Unauthorized"}), 403
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    # Delete all chats for this user
    Chat.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User and all their chats deleted"})

@app.route("/")
def index():
    return redirect(url_for('chat_ui'))

if __name__ == "__main__":
    app.run(debug=True)
