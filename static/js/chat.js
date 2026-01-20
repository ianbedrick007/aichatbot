document.addEventListener('DOMContentLoaded', function() {
    const chatMessages = document.getElementById('chatMessages');
    const chatForm = document.getElementById('chatForm');
    const messageInput = document.getElementById('messageInput');
    const thinkingIndicator = document.getElementById('thinkingIndicator');

    // Auto-scroll to bottom on load
    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    scrollToBottom();

    // Handle form submission
    if (chatForm) {
        chatForm.addEventListener('submit', function(e) {
            const message = messageInput.value.trim();
            if (!message) {
                e.preventDefault();
                return;
            }

            // Show thinking indicator
            if (thinkingIndicator) {
                thinkingIndicator.style.display = 'flex';
                scrollToBottom();
            }
            
            // Allow form to submit normally
        });
    }

    // Focus input on load
    if (messageInput) {
        messageInput.focus();
    }
});