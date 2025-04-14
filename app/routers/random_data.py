from fastapi import APIRouter, Query
from pydantic import BaseModel
import uuid
import random
import secrets
from datetime import datetime, timedelta
from typing import Optional

router = APIRouter(prefix="/random", tags=["random"])

@router.get("/uuid")
async def generate_uuid():
    """Generates a random UUID (Universally Unique Identifier)."""
    return {"uuid": str(uuid.uuid4())}

@router.get("/int")
async def generate_random_integer(min: int = 0, max: int = 100):
    """Generates a random integer within a specified range."""
    return {"random_integer": random.randint(min, max)}

@router.get("/float")
async def generate_random_float(min: float = 0.0, max: float = 1.0):
    """Generates a random floating-point number within a specified range."""
    return {"random_float": random.uniform(min, max)}

@router.get("/string")
async def generate_random_string(length: int = 16):
    """Generates a random string of a specified length (using letters and numbers)."""
    characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    random_string = "".join(random.choice(characters) for _ in range(length))
    return {"random_string": random_string}

@router.get("/secure-password")
async def generate_secure_password(length: int = 20):
    """Generates a cryptographically secure random password."""
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+=-`~[]{}\|:;'<>,.?/"
    password = "".join(secrets.choice(alphabet) for _ in range(length))
    return {"secure_password": password}

@router.get("/color/hex")
async def generate_random_hex_color():
    """Generates a random hexadecimal color code."""
    return {"hex_color": f"#{random.randint(0, 0xFFFFFF):06x}"}

class RGBColor(BaseModel):
    red: int
    green: int
    blue: int

@router.get("/color/rgb", response_model=RGBColor)
async def generate_random_rgb_color():
    """Generates a random RGB color."""
    return {"red": random.randint(0, 255), "green": random.randint(0, 255), "blue": random.randint(0, 255)}

@router.get("/date")
async def generate_random_date(
    start_year: int = 2020,
    end_year: int = 2025
):
    """Generates a random date within a specified year range."""
    start_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year + 1, 1, 1) - timedelta(days=1)
    time_between_dates = end_date - start_date
    random_number_of_days = random.randint(0, time_between_dates.days)
    random_date = start_date + timedelta(days=random_number_of_days)
    return {"random_date": random_date.strftime("%Y-%m-%d")}

@router.get("/choice")
async def get_random_choice(items: str = Query(..., description="Comma-separated list of items")):
    """Chooses a random item from a comma-separated list."""
    item_list = [item.strip() for item in items.split(",")]
    if item_list:
        return {"random_choice": random.choice(item_list)}
    else:
        return {"error": "No items provided"}