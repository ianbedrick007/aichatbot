import os
from flask import Flask, render_template, request, redirect, url_for, flash
from ai.run_ai import get_ai_response
from dotenv import load_dotenv
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash
from ai.models import db, User, Message, Product, Business
from whatsapp_bot.app.views import webhook_blueprint
from whatsapp_bot.app.config import load_configurations, configure_logging

load_dotenv()
app = Flask(__name__)

# Configure WhatsApp Bot
load_configurations(app)
configure_logging()
app.register_blueprint(webhook_blueprint)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("CHATBOT_DB")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY")

db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access the chat.'
login_manager.login_message_category = 'info'


@login_manager.user_loader
def load_user(user_id):
    """Load user from session"""
    return db.session.get(User, int(user_id))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()

        # ✅ Fix: "user not found" should not say "fill in all fields"
        if not username or not password:
            flash('Please fill in all fields.', 'error')
            return redirect(url_for('login'))

        if not user or not user.check_password(password):
            flash('Invalid username or password.', 'error')
            return redirect(url_for('login'))

        login_user(user)
        flash(f'Welcome back, {username}!', 'success')
        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """
    ✅ Signup now creates BOTH:
      - User (login)
      - Business (the account container)
    """
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip() or None
        password = request.form.get('password') or ''
        business_name = (request.form.get('business_name') or '').strip()
        # ✅ Optional: collect phone_number_id during signup
        phone_number_id = (request.form.get('phone_number_id') or '').strip() or None

        # Basic validation
        if not username or not password or not business_name:
            flash('Username, password, and business name are required.', 'error')
            return redirect(url_for('signup'))

        # Prevent duplicates
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'error')
            return redirect(url_for('signup'))

        if email and User.query.filter_by(email=email).first():
            flash('Email already exists.', 'error')
            return redirect(url_for('signup'))

        if phone_number_id and Business.query.filter_by(phone_number_id=phone_number_id).first():
            flash('This WhatsApp phone number is already registered.', 'error')
            return redirect(url_for('signup'))

        # Create new user
        new_user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
        )
        db.session.add(new_user)
        db.session.flush()  # ensures new_user.id exists before Business insert

        # Create the user's business (1:1)
        new_business = Business(
            name=business_name,
            user_id=new_user.id,
            phone_number_id=phone_number_id
        )
        db.session.add(new_business)

        db.session.commit()

        # Optional: auto-login after signup
        login_user(new_user)
        flash('Account created successfully!', 'success')
        return redirect(url_for('index'))

    return render_template("signup.html")


@app.route('/logout')
@login_required
def logout():
    """Logout user"""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    """
    ✅ Chat page - requires authentication
    Messages are now tied to the logged-in user's business.
    """
    business = current_user.business
    if not business:
        flash('No business found for this account. Please sign up again or contact support.', 'error')
        return redirect(url_for('logout'))

    if request.method == 'POST':
        user_message = request.form.get('message', '').strip()

        if user_message:
            # ✅ Get recent messages for THIS BUSINESS for context
            recent_messages = Message.query.filter_by(business_id=business.id) \
                .order_by(Message.timestamp.desc()) \
                .limit(20) \
                .all()

            conversation_history = [
                {'text': msg.text, 'sender': msg.sender}
                for msg in reversed(recent_messages)
            ]

            # ✅ Save user message (business-scoped)
            user_msg = Message(business_id=business.id, text=user_message, sender='user')
            db.session.add(user_msg)
            db.session.commit()

            # ✅ Get AI response WITH context AND business_id
            bot_response = get_ai_response(
                user_message,
                conversation_history,
                business_id=business.id
            )

            # ✅ Save bot response (business-scoped)
            bot_msg = Message(business_id=business.id, text=bot_response, sender='bot')
            db.session.add(bot_msg)
            db.session.commit()

        return redirect(url_for('index'))

    # ✅ Display all messages for THIS BUSINESS
    messages = Message.query.filter_by(business_id=business.id) \
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

    return render_template('index.html', messages=display_messages, username=current_user.username)


@app.route('/clear', methods=['GET', 'POST'])
@login_required
def clear_messages():
    """✅ Clear all messages for current business"""
    business = current_user.business
    if not business:
        flash('No business found.', 'error')
        return redirect(url_for('index'))

    Message.query.filter_by(business_id=business.id).delete()
    db.session.commit()
    flash('Messages cleared.', 'info')
    return redirect(url_for('index'))


@app.route('/add_product', methods=['POST'])
@login_required
def add_product():
    """
    ✅ Add product for the logged-in user's business.
    IMPORTANT: we do NOT accept business_id from the form anymore (prevents abuse).
    """
    business = current_user.business
    if not business:
        flash('No business found.', 'error')
        return redirect(url_for('index'))

    name = (request.form.get('name') or '').strip()
    description = (request.form.get('description') or '').strip()
    price_raw = (request.form.get('price') or '').strip()
    image_url = (request.form.get('image_url') or '').strip()

    if not name or not price_raw:
        flash('Name and price are required.', 'error')
        return redirect(url_for('index'))

    try:
        price = float(price_raw)
    except ValueError:
        flash('Price must be a valid number.', 'error')
        return redirect(url_for('index'))

    product = Product(
        name=name,
        description=description if description else None,
        price=price,
        image_url=image_url if image_url else None,
        business_id=business.id
    )
    db.session.add(product)
    db.session.commit()
    flash('Product added successfully!', 'success')
    return redirect(url_for('products'))


@app.route('/products')
@login_required
def products():
    """✅ Display products for current business only"""
    business = current_user.business
    if not business:
        flash('No business found.', 'error')
        return redirect(url_for('index'))

    products = Product.query.filter_by(business_id=business.id).all()
    return render_template('products.html', products=products)


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """✅ Settings page to configure WhatsApp phone number"""
    business = current_user.business
    if not business:
        flash('No business found.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        phone_number_id = (request.form.get('phone_number_id') or '').strip() or None
        persona = (request.form.get('persona') or '').strip() or None

        # Check if phone number is already taken by another business
        if phone_number_id:
            existing = Business.query.filter(
                Business.phone_number_id == phone_number_id,
                Business.id != business.id
            ).first()

            if existing:
                flash('This WhatsApp phone number is already registered to another business.', 'error')
                return redirect(url_for('settings'))

        business.phone_number_id = phone_number_id
        business.persona = persona
        db.session.commit()
        flash('Settings updated successfully!', 'success')
        return redirect(url_for('settings'))

    return render_template('settings.html', business=business)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(host='0.0.0.0', debug=True, port=8000)