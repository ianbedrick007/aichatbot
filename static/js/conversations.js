document.addEventListener('DOMContentLoaded', function() {
    const feed = document.getElementById('conversationFeed');
    const loadingState = document.getElementById('loadingState');
    let lastMessageId = 0;
    let isFirstLoad = true;

    // Poll every 2 seconds
    setInterval(fetchMessages, 2000);
    fetchMessages(); // Initial call

    async function fetchMessages() {
        try {
            // Fetch messages newer than the last one we saw
            const response = await fetch(`/api/live-messages?after_id=${lastMessageId}`);
            if (!response.ok) return;

            const data = await response.json();

            if (data.messages.length > 0) {
                // Clear "Waiting..." state on first message
                if (loadingState) loadingState.style.display = 'none';

                data.messages.forEach(msg => {
                    appendMessage(msg);
                    lastMessageId = msg.id; // Update cursor
                });

                scrollToBottom();
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }

    function appendMessage(msg) {
        const messageDiv = document.createElement('div');

        // Style: Bot on Right (Green), Customer on Left (White)
        const alignmentClass = msg.is_bot ? 'message-bot' : 'message-user';
        const bubbleColor = msg.is_bot ? 'background: rgba(37, 211, 102, 0.2); border: 1px solid rgba(37, 211, 102, 0.3);' : '';
        const senderName = msg.is_bot ? "AI Assistant" : msg.sender;
        const nameColor = msg.is_bot ? "#25D366" : "#aaa";

        messageDiv.className = `message-item ${alignmentClass}`;
        messageDiv.innerHTML = `
            <div class="message-bubble-glass" style="${bubbleColor}">
                <div style="font-size: 0.75rem; color: ${nameColor}; margin-bottom: 4px; font-weight: bold;">
                    ${escapeHtml(senderName)}
                </div>
                <p class="message-text">${escapeHtml(msg.text)}</p>
                <span class="message-time">${msg.timestamp}</span>
            </div>
        `;

        feed.appendChild(messageDiv);
    }

    function scrollToBottom() {
        feed.scrollTop = feed.scrollHeight;
    }

    function escapeHtml(text) {
        if (!text) return "";
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});