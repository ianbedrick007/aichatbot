import base64
import os
import tempfile

import requests
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.image_embeddings import generate_text_embedding, generate_image_embedding
from models import Product

load_dotenv()

BASE_URL = os.getenv("VAULTA_BASE_URL")
VAULTA_BASE_URL = BASE_URL
VAULTA_API_KEY = os.getenv("VAULTA_API_KEY")
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current temperature for a specific geographic location using latitude and longitude"
            ,
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "latitude": {
                        "type": "number",
                        "description": "Latitude of the location"
                    },
                    "longitude": {
                        "type": "number",
                        "description": "Longitude of the location"
                    }
                },
                "required": ["latitude", "longitude"],
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_exchange_rate",
            "description": "Get the exchange rate and metadata for a specific currency pair",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "local_currency": {
                        "type": "string",
                        "description": "The base currency code (e.g., 'USD')"
                    },
                    "foreign_currency": {
                        "type": "string",
                        "description": "The target currency code (e.g., 'EUR')"
                    }
                },
                "required": ["local_currency", "foreign_currency"],
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_products",
            "description": "Get the list of products for the current user's business",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_rate",
            "description": "Create a quote for a crypto-fiat pair using the VAULTA API",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "pair": {
                        "type": "string",
                        "description": "Trading instrument pair (e.g., 'BTC-GHS')"
                    },
                    "side": {
                        "type": "string",
                        "description": "Order side, either 'buy' or 'sell'"
                    },
                    "amount_crypto": {
                        "type": "number",
                        "description": "Amount of base cryptocurrency"
                    },
                    "amount_fiat": {
                        "type": "number",
                        "description": "Amount of quote currency"
                    }
                },
                "required": ["pair", "side", "amount_crypto", "amount_fiat"],
                "additionalProperties": False,
            }
        }
    },
    {
        "name": "initialize_payment",
        "description": "Initialize a Paystack payment transaction. Amount should be provided in major currency units (e.g., GHS). Returns authorization URL and transaction reference.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "customer_email": {
                    "type": "string",
                    "description": "The customer's actual email address. Ask them for it if not known."
                },
                "amount": {
                    "type": "number",
                    "description": "Amount in major units (e.g., 10.50 for GHS 10.50)"
                },
                "callback_url": {
                    "type": "string",
                    "description": "Optional callback URL for Paystack redirect",
                    "nullable": True
                },
                "currency": {
                    "type": "string",
                    "description": "Currency code (default: GHS)",
                    "default": "GHS"
                }
            },
            "required": ["customer_email", "amount"]
        }
    },
    {
        "name": "verify_payment",
        "description": "Verify a Paystack transaction using its reference. Returns transaction status, metadata, and payment details.",
        "parameters": {
            "type": "object",
            "properties": {
                "reference": {
                    "type": "string",
                    "description": "The Paystack transaction reference to verify"
                }
            },
            "required": ["reference"]
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_similar_products",
            "description": "Search for products that are visually or semantically similar to a text description. Use when a customer describes what they're looking for or wants to find products similar to something.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text description of what the user is looking for (e.g., 'red sneakers', 'leather handbag', 'gold necklace')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 5)"
                    }
                },
                "required": ["query", "limit"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_image",
            "description": "Search for products similar to an image by generating an image embedding from a provided image URL. Use when a customer uploads or shares an image and wants to find visually similar products.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "image_url": {
                        "type": "string",
                        "description": "Publicly accessible URL of the image to search with"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 5)"
                    }
                },
                "required": ["image_url", "limit"],
                "additionalProperties": False
            }
        }
    }

]


def get_weather(latitude: float, longitude: float):
    """Get the current weather for a specific geographic location."""
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={latitude}&longitude={longitude}"
            "&current=temperature_2m,wind_speed_10m"
        )

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        return data.get("current", {})

    except Exception as e:
        return {"error": str(e)}


def get_exchange_rate(local_currency, foreign_currency):
    "Get the exchange rate for a specific currency pair"
    try:
        response = requests.get(
            f"https://api.exchangerate-api.com/v4/latest/{local_currency}"
        )
        response.raise_for_status()
        data = response.json()
        exchange_rate = data['rates'][foreign_currency]
        return {
            "local_currency": local_currency,
            "foreign_currency": foreign_currency,
            "rate": exchange_rate,
            "date": data.get("date")
        }
    except Exception as e:
        return {"error": str(e)}


def get_products(db: Session, business_id: int):
    """
    Get the list of products for a business.
    """
    try:
        if not business_id:
            return {"error": "Business ID is required"}

        result = db.execute(select(Product).where(Product.business_id == business_id))
        products = result.scalars().all()

        product_list = []
        for p in products:
            product_list.append({
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": p.price,
                "image_url": p.image_url
            })

        return product_list
    except Exception as e:
        return {"error": str(e)}


def get_rate(pair, side, amount_crypto, amount_fiat):
    quotes_url = f"{VAULTA_BASE_URL}/get_quote"
    headers = {
        "x-api-key": VAULTA_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "pair": pair,
        "side": side,
        "amount_crypto": amount_crypto,
        "amount_fiat": amount_fiat
    }

    try:
        response = requests.post(quotes_url, headers=headers, json=payload)
        response.raise_for_status()
        quote = response.json()
        print("Quote created successfully:")
        print(quote)
        return quote
    except Exception as e:
        return {"error": str(e)}


def search_similar_products(query: str, limit: int = 5, db: Session = None, business_id: int = None):
    """
    Search for products similar to a text description using vector embeddings.
    """
    try:
        if not db or not business_id:
            return {"error": "Database session and business ID required"}

        # Generate embedding from query text
        try:
            query_embedding = generate_text_embedding(query)
        except Exception as e:
            return {"error": f"Failed to generate text embedding: {str(e)}"}

        # Query using pgvector cosine distance
        results = db.query(Product).filter(
            Product.business_id == business_id,
            Product.image_embedding.isnot(None)
        ).order_by(
            Product.image_embedding.cosine_distance(query_embedding)
        ).limit(limit or 5).all()

        if not results:
            return {"message": "No products with image embeddings found. Try uploading product images first."}

        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": p.price,
                "image_url": p.image_url
            }
            for p in results
        ]
    except Exception as e:
        return {"error": str(e)}


def search_by_image(image_url: str, limit: int = 5, db: Session = None, business_id: int = None):
    try:
        if not db or not business_id:
            return {"error": "Database session and business ID required"}

        try:
            print(f"Generating image embedding for URL: {image_url}")
            query_embedding = generate_image_embedding(image_url)
        except Exception as e:
            return {"error": f"Failed to generate image embedding: {str(e)}"}

        # Query using pgvector cosine distance
        print(f"Searching for similar products in business {business_id}...")
        results = db.query(Product).filter(
            Product.business_id == business_id,
            Product.image_embedding.isnot(None)
        ).order_by(
            Product.image_embedding.cosine_distance(query_embedding)
        ).limit(limit or 5).all()

        if not results:
            return {"message": "No products with image embeddings found. Try uploading product images first."}

        print(f"Found {len(results)} similar products.")
        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "price": p.price,
                "image_url": p.image_url
            }
            for p in results
        ]
    except Exception as e:
        return {"error": str(e)}
