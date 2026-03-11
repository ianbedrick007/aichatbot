# """
# Image embedding service using Vertex AI Multimodal Embeddings.
#
# Uses multimodalembedding@001 for true image vector embeddings —
# images are embedded directly into a shared vector space with text,
# enabling cross-modal similarity search.
# """
#
# import os
# from pathlib import Path
# import vertexai
# from dotenv import load_dotenv
# from google.cloud import aiplatform
# from vertexai.vision_models import MultiModalEmbeddingModel, Image as VertexImage
#
# load_dotenv()
#
# # Vertex AI config from environment
# GCP_PROJECT = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
# GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
# EMBEDDING_DIM = 1408  # multimodalembedding@001 max dimension
#
# # Lazy initialization — avoid crashing at import if GCP isn't configured
# _model = None
#
#
# def _get_model():
#     """Lazily initialize Vertex AI and load the embedding model."""
#     global _model
#     if _model is None:
#         if not GCP_PROJECT:
#             raise ValueError("GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable not set.")
#         vertexai.init(project=GCP_PROJECT, location="us-central1")
#         _model = MultiModalEmbeddingModel.from_pretrained("multimodalembedding")
#     return _model
#
#
# def generate_image_embedding(image_path: str) -> list[float]:
#     """
#     Generate a vector embedding from a product image using Vertex AI.
#
#     Args:
#         image_path: Absolute path to the image file on disk.
#
#     Returns:
#         A list of floats (1408 dimensions). Raises Exception on failure.
#     """
#     filepath = Path(image_path)
#     if not filepath.exists():
#         raise FileNotFoundError(f"Image file not found: {image_path}")
#
#     # Load image directly from file path
#     image = VertexImage.load_from_file(str(filepath))
#
#     # Get embedding — single API call, true visual embedding
#     embeddings = _get_model().get_embeddings(
#         image=image,
#         dimension=EMBEDDING_DIM,
#     )
#
#     embedding = embeddings.image_embedding
#     if not embedding:
#         raise ValueError("Vertex AI returned empty image embedding")
#
#     print(f"[OK] Generated image embedding ({len(embedding)} dims) for {filepath.name}")
#     return list(embedding)
#
#
# def generate_image_embedding_from_base64(base64_data: str) -> list[float]:
#     """Generate embedding from base64 image string (e.g. from WhatsApp download)."""
#     import base64, tempfile
#
#     image_bytes = base64.b64decode(base64_data)
#
#     with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
#         tmp.write(image_bytes)
#         tmp_path = tmp.name
#
#     try:
#         return generate_image_embedding(tmp_path)
#     finally:
#         os.unlink(tmp_path)  # clean up temp file
#
#
# def generate_text_embedding(text: str) -> list[float]:
#     """
#     Generate a text embedding in the same vector space as image embeddings.
#     This enables cross-modal search: text queries match image vectors.
#
#     Args:
#         text: Text description to embed (e.g. "red sneakers").
#
#     Returns:
#         A list of floats (1408 dimensions). Raises Exception on failure.
#     """
#     embeddings = _get_model().get_embeddings(
#         contextual_text=text,
#         dimension=EMBEDDING_DIM,
#     )
#
#     embedding = embeddings.text_embedding
#     if not embedding:
#         raise ValueError("Vertex AI returned empty text embedding")
#
#     return list(embedding)

""" Image embedding service using Vertex AI with the new Gemini Multimodal Embeddings.
Uses gemini-embedding-2-preview for true multimodal vector embeddings — images and text
are embedded directly into a shared vector space, enabling cross-modal similarity search. """

import os
import base64
from pathlib import Path
from dotenv import load_dotenv
import config

# Import the modern Google GenAI SDK
from google import genai
from google.genai import types

from config import settings

load_dotenv()

# Vertex AI config from environment
GCP_PROJECT = settings.gcp_project_id
GCP_LOCATION = "us-central1"
EMBEDDING_DIM = 1408
MODEL_ID = "gemini-embedding-2-preview"

# Lazy initialization
_client = None


def _get_client():
    """Lazily initialize the Google GenAI client for Vertex AI."""
    global _client
    if _client is None:
        if not GCP_PROJECT:
            raise ValueError("GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable not set.")
        # Initialize the unified client targeting Vertex AI
        _client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
    return _client


def generate_image_embedding(image_path: str) -> list[float]:
    """ Generate a vector embedding from a product image using Gemini Embedding 2. """
    filepath = Path(image_path)

    if not filepath.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")

    client = _get_client()

    # Read image bytes and create a multimodal Part
    with open(filepath, "rb") as f:
        image_bytes = f.read()

    # Infer mime type (defaulting to jpeg if not png)
    mime_type = "image/png" if filepath.suffix.lower() == ".png" else "image/jpeg"
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    # Generate embedding using the unified embed_content method
    response = client.models.embed_content(
        model=MODEL_ID,
        contents=image_part,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)
    )

    if not response.embeddings or not response.embeddings[0].values:
        raise ValueError("Vertex AI returned empty image embedding")

    embedding = response.embeddings[0].values
    print(f"[OK] Generated image embedding ({len(embedding)} dims) for {filepath.name}")
    return list(embedding)


def generate_image_embedding_from_base64(base64_data: str) -> list[float]:
    """Generate embedding from base64 image string (e.g., from WhatsApp download)."""
    image_bytes = base64.b64decode(base64_data)
    client = _get_client()

    # Directly pass bytes in memory—no need for temp files anymore!
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    response = client.models.embed_content(
        model=MODEL_ID,
        contents=image_part,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)
    )

    if not response.embeddings or not response.embeddings[0].values:
        raise ValueError("Vertex AI returned empty image embedding")

    embedding = response.embeddings[0].values
    print(f"[OK] Generated image embedding ({len(embedding)} dims) from base64 data")
    return list(embedding)


def generate_text_embedding(text: str) -> list[float]:
    """ Generate a text embedding in the same vector space as image embeddings. """
    client = _get_client()

    response = client.models.embed_content(
        model=MODEL_ID,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM)
    )

    if not response.embeddings or not response.embeddings[0].values:
        raise ValueError("Vertex AI returned empty text embedding")

    embedding = response.embeddings[0].values
    return list(embedding)
