from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from ai.run_ai import get_ai_response
app = Flask(__name__)

@app.route("/whatsapp", methods=['GET', 'POST'])
def message_reply():
    # get incoming text and sender from Twilio's webhook parameters
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    print(f"Incoming message from {from_number}: {incoming_msg}")

    resp = MessagingResponse()
    if incoming_msg:
        resp.message(get_ai_response(incoming_msg))
    else:
        resp.message("No message received.")

    return str(resp)

if __name__ == "__main__":
    app.run(debug=True, port=8080)