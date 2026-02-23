"""
Image embedding service using Vertex AI Multimodal Embeddings.

Uses multimodalembedding@001 for true image vector embeddings — 
images are embedded directly into a shared vector space with text,
enabling cross-modal similarity search.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import aiplatform
from vertexai.vision_models import MultiModalEmbeddingModel, Image as VertexImage

load_dotenv()

# Vertex AI config from environment
GCP_PROJECT = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
EMBEDDING_DIM = 1408  # multimodalembedding@001 max dimension

# Lazy initialization — avoid crashing at import if GCP isn't configured
_model = None


def _get_model():
    """Lazily initialize Vertex AI and load the embedding model."""
    global _model
    if _model is None:
        aiplatform.init(project=GCP_PROJECT, location=GCP_LOCATION)
        _model = MultiModalEmbeddingModel.from_pretrained("multimodalembedding@001")
    return _model


def generate_image_embedding(image_path: str) -> list[float] | None:
    """
    Generate a vector embedding from a product image using Vertex AI.

    Args:
        image_path: Absolute path to the image file on disk.

    Returns:
        A list of floats (1408 dimensions) or None if embedding fails.
    """
    try:
        filepath = Path(image_path)
        if not filepath.exists():
            print(f"[ERROR] Image file not found: {image_path}")
            return None

        # Load image directly from file path
        image = VertexImage.load_from_file(str(filepath))

        # Get embedding — single API call, true visual embedding
        embeddings = _get_model().get_embeddings(
            image=image,
            dimension=EMBEDDING_DIM,
        )

        embedding = embeddings.image_embedding
        if not embedding:
            print("[ERROR] Vertex AI returned empty image embedding")
            return None

        print(f"[OK] Generated image embedding ({len(embedding)} dims) for {filepath.name}")
        return list(embedding)

    except Exception as e:
        print(f"[ERROR] Error generating image embedding: {e}")
        return None


def generate_text_embedding(text: str) -> list[float] | None:
    """
    Generate a text embedding in the same vector space as image embeddings.
    This enables cross-modal search: text queries match image vectors.

    Args:
        text: Text description to embed (e.g. "red sneakers").

    Returns:
        A list of floats (1408 dimensions) or None if embedding fails.
    """
    try:
        embeddings = _get_model().get_embeddings(
            contextual_text=text,
            dimension=EMBEDDING_DIM,
        )

        embedding = embeddings.text_embedding
        if not embedding:
            print("[ERROR] Vertex AI returned empty text embedding")
            return None

        return list(embedding)

    except Exception as e:
        print(f"[ERROR] Error generating text embedding: {e}")
        return None
