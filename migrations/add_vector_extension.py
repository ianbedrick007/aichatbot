"""
One-time migration script to enable pgvector extension
and add/update the image_embedding column to the products table.

Run this once:  python migrations/add_vector_extension.py
"""

import os
import sys

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Add parent directory to path so we can import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

EMBEDDING_DIM = 1408  # Vertex AI multimodalembedding@001 dimension


def run_migration():
    db_url = os.getenv("CHATBOT_DB")
    if not db_url:
        print("[ERROR] CHATBOT_DB not set in .env")
        return

    db_url = db_url.strip().strip('"').strip("'")
    engine = create_engine(db_url)

    with engine.connect() as conn:
        # 1. Enable pgvector extension
        print("[1/4] Enabling pgvector extension...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
        print("[OK] pgvector extension enabled")

        # 2. Check if column already exists
        result = conn.execute(text("""
            SELECT column_name, udt_name FROM information_schema.columns
            WHERE table_name = 'products' AND column_name = 'image_embedding'
        """))
        row = result.fetchone()
        if row:
            # Column exists - drop and recreate with new dimension
            print("[INFO] image_embedding column exists, resizing...")
            print(f"[2/4] Resizing image_embedding to vector({EMBEDDING_DIM})...")
            conn.execute(text("ALTER TABLE products DROP COLUMN image_embedding"))
            conn.execute(text(
                f"ALTER TABLE products ADD COLUMN image_embedding vector({EMBEDDING_DIM})"
            ))
            conn.commit()
            print(f"[OK] image_embedding column resized to {EMBEDDING_DIM}")
        else:
            print(f"[2/4] Adding image_embedding column (vector({EMBEDDING_DIM}))...")
            conn.execute(text(
                f"ALTER TABLE products ADD COLUMN image_embedding vector({EMBEDDING_DIM})"
            ))
            conn.commit()
            print("[OK] image_embedding column added")

        # 3. Drop old index if exists, recreate
        conn.execute(text("DROP INDEX IF EXISTS ix_products_image_embedding"))
        conn.commit()

        print("[3/4] Creating vector similarity index...")
        conn.execute(text(f"""
            CREATE INDEX ix_products_image_embedding
            ON products USING ivfflat (image_embedding vector_cosine_ops)
            WITH (lists = 100)
        """))
        conn.commit()
        print("[OK] Vector index created")

        print("\n[DONE] Migration complete!")


if __name__ == "__main__":
    run_migration()
