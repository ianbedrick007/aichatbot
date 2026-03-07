import os
import json
from typing import List, Dict
from redis import asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

# Default to localhost if not set in .env
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

class RedisClient:
    def __init__(self):
        self.redis = aioredis.from_url(REDIS_URL, decode_responses=True)

    async def get_conversation_history(self, session_id: str) -> List[Dict]:
        """Retrieve conversation history from Redis."""
        key = f"chat:{session_id}"
        # Get all elements from the list (0 to -1)
        history = await self.redis.lrange(key, 0, -1)
        return [json.loads(msg) for msg in history]

    async def add_message_to_history(self, session_id: str, role: str, content: str):
        """Push a new message to the conversation history."""
        key = f"chat:{session_id}"
        message = json.dumps({"role": role, "content": content})
        # Push to the right (end) of the list
        await self.redis.rpush(key, message)
        # Set expiry (e.g., 24 hours) to prevent stale sessions from filling memory
        await self.redis.expire(key, 86400)

    async def clear_history(self, session_id: str):
        """Clear conversation history."""
        key = f"chat:{session_id}"
        await self.redis.delete(key)

# Singleton instance to be imported elsewhere
cache = RedisClient()