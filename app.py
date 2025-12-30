import os
from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
from run_ai import get_ai_response
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from flask_migrate import Migrate
load_dotenv()
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("CHATBOT_DB")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "your-secret-key-here")

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# User model
class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    # Relationship: one user has many messages
    messages = db.relationship('Message', backref='user', lazy=True, cascade='all, delete-orphan')


# Message model
class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    sender = db.Column(db.String(10), nullable=False)  # 'user' or 'bot'
    timestamp = db.Column(db.DateTime, default=datetime.now)


@app.route('/', methods=['GET', 'POST'])
def index():
    user = User.query.filter_by(username='default_user').first()
    if not user:
        user = User(username='default_user')
        db.session.add(user)
        db.session.commit()

    if request.method == 'POST':
        user_message = request.form.get('message', '').strip()

        if user_message:
            # Get last 10 messages for context (adjust number as needed)
            recent_messages = Message.query.filter_by(user_id=user.id) \
                .order_by(Message.timestamp.desc()) \
                .all()

            conversation_history = [
                {'text': msg.text, 'sender': msg.sender}
                for msg in reversed(recent_messages)  # Reverse to get chronological order
            ]

            # Save user message
            user_msg = Message(user_id=user.id, text=user_message, sender='user')
            db.session.add(user_msg)
            db.session.commit()

            # Get AI response WITH context
            bot_response = get_ai_response(user_message, conversation_history)

            # Save bot response
            bot_msg = Message(user_id=user.id, text=bot_response, sender='bot')
            db.session.add(bot_msg)
            db.session.commit()

        return redirect(url_for('index'))

    # Display all messages
    messages = Message.query.filter_by(user_id=user.id) \
        .order_by(Message.timestamp.asc()) \
        .all()

    display_messages = [
        {
            'text': msg.text,
            'sender': msg.sender,
            'timestamp': msg.timestamp.strftime('%I:%M %p')
        }
        for msg in messages
    ]

    return render_template('index.html', messages=display_messages)


@app.route('/clear', methods=['GET', 'POST'])
def clear_messages():
    """Clear all messages for current user"""
    user = User.query.filter_by(username='default_user').first()
    if user:
        Message.query.filter_by(user_id=user.id).delete()
        db.session.commit()
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5000)