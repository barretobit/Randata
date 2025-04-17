from fastapi import APIRouter, Query
from slugify import slugify
import markdown
import lorem

router = APIRouter(prefix="/text", tags=["text_utilities"])

@router.get("/slugify")
async def generate_slug(text: str = Query(..., description="Text to convert to a slug")):
    """Generates a URL-friendly slug from a given text."""
    return {"original_text": text, "slug": slugify(text)}

@router.get("/word-count")
async def count_words(text: str = Query(..., description="Text to count words in")):
    """Counts the number of words in a given text."""
    words = text.split()
    return {"text": text, "word_count": len(words)}

@router.get("/markdown-to-html")
async def convert_markdown(md: str = Query(..., description="Markdown text to convert")):
    """Converts Markdown text to HTML."""
    html = markdown.markdown(md)
    return {"markdown": md, "html": html}

@router.get("/lorem-ipsum")
async def generate_lorem_ipsum(
    paragraphs: int = Query(1, ge=1, description="Number of paragraphs to generate"),
    words_per_paragraph: int = Query(30, ge=1, description="Number of words per paragraph")
):
    """Generates Lorem Ipsum placeholder text."""
    text_list = [lorem.paragraph(words_per_paragraph) for _ in range(paragraphs)]
    text = "\n\n".join(text_list)
    return {"paragraphs": paragraphs, "words_per_paragraph": words_per_paragraph, "lorem_ipsum": text}