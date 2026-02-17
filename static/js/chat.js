document.addEventListener('DOMContentLoaded', function() {
    const chatMessages = document.getElementById('chatMessages');
    const chatForm = document.getElementById('chatForm');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const thinkingBubble = document.getElementById('thinkingBubble');

    if (!chatMessages || !chatForm || !messageInput) return;

    // Auto-scroll to bottom
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    scrollToBottom();

    // Enable/disable send button
    if (sendButton) {
        messageInput.addEventListener('input', function() {
            sendButton.disabled = !this.value.trim();
        });
    }

    // Handle form submission
    chatForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        const message = messageInput.value.trim();
        if (!message) return;

        // Add user message
        appendMessage(message, 'user');
        messageInput.value = '';
        if (sendButton) sendButton.disabled = true;

        // Show thinking bubble
        if (thinkingBubble) {
            thinkingBubble.style.display = 'flex';
            scrollToBottom();
        }

        try {
            // Simulate API call (Replace with actual API endpoint)
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });
            const data = await response.json();

            // Hide thinking bubble
            if (thinkingBubble) thinkingBubble.style.display = 'none';

            // Add bot response
            appendMessage(data.response, 'bot');

        } catch (error) {
            console.error('Error:', error);
            if (thinkingBubble) thinkingBubble.style.display = 'none';
            appendMessage("Sorry, something went wrong. Please try again.", 'bot');
        }
    });

    function appendMessage(text, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message-item ${sender === 'user' ? 'message-user' : 'message-bot'}`;

        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        messageDiv.innerHTML = `
            <div class="message-bubble-glass">
                <p class="message-text">${escapeHtml(text)}</p>
                <span class="message-time">${time}</span>
            </div>
        `;

        // Insert before thinking bubble
        if (thinkingBubble) {
            chatMessages.insertBefore(messageDiv, thinkingBubble);
        } else {
            chatMessages.appendChild(messageDiv);
        }
        scrollToBottom();

        // Remove empty state if present
        const emptyState = document.querySelector('.empty-state-glass');
        if (emptyState) emptyState.remove();
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});