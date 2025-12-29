from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
from run_ai import get_ai_response

app = Flask(__name__)

# In-memory storage for messages (in production, use a database)
messages = []


@app.route('/', methods=['GET', 'POST'])
def index():
    """Handle both displaying messages and processing new messages"""
    if request.method == 'POST':
        user_message = request.form.get('message', '').strip()
        
        if user_message:
            # Add user message
            messages.append({
                'text': user_message,
                'sender': 'user',
                'timestamp': datetime.now().strftime('%I:%M %p')
            })

            # Here you can add logic to process the message and generate a response
            bot_response = get_ai_response(user_message)

            messages.append({
                'text': bot_response,
                'sender': 'bot',
                'timestamp': datetime.now().strftime('%I:%M %p')
            })
        
        # Redirect to avoid form resubmission on refresh
        return redirect(url_for('index'))
    
    # GET request - just display the page with messages
    return render_template('index.html', messages=messages)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
