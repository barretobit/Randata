import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db

router = APIRouter()


class StorageCreateRequest(BaseModel):
    user: str
    password: str
    code: str
    data: dict


class StorageAuthRequest(BaseModel):
    user: str
    password: str


class StorageUpdateRequest(BaseModel):
    user: str
    password: str
    data: dict


def _hash_password(password: str) -> str:
    import bcrypt as _bcrypt
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    import bcrypt as _bcrypt
    return _bcrypt.checkpw(password.encode(), hashed.encode())


def _get_entry(code: str, db: Session):
    sql = text(
        "SELECT id, user, pass_hash, json_data, last_updated "
        "FROM file_storage WHERE code = :code"
    )
    return db.execute(sql, {"code": code}).fetchone()


def _authenticate(row, user: str, password: str):
    if row is None:
        raise HTTPException(status_code=404, detail="Code not found.")
    if row.user != user or not _verify_password(password, row.pass_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials.")


@router.post(
    "/create",
    summary="Create a file storage entry",
    description="Stores a new JSON blob under a unique code, protected by user credentials.",
)
def create_entry(body: StorageCreateRequest, db: Session = Depends(get_db)):
    existing = _get_entry(body.code, db)
    if existing:
        raise HTTPException(status_code=409, detail="Code already exists.")

    try:
        json_str = json.dumps(body.data)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Data is not valid JSON.")

    hashed = _hash_password(body.password)
    sql = text(
        "INSERT INTO file_storage (user, pass_hash, code, json_data) "
        "VALUES (:user, :pass_hash, :code, :json_data)"
    )
    db.execute(sql, {
        "user": body.user,
        "pass_hash": hashed,
        "code": body.code,
        "json_data": json_str,
    })
    db.commit()

    return {"status": "created", "code": body.code}


@router.get(
    "/list",
    summary="List all codes for a user",
    description="Returns every code for the user whose stored password matches.",
)
def list_codes(
    user: str = Query(..., description="Username"),
    password: str = Query(..., description="Password"),
    db: Session = Depends(get_db),
):
    sql = text(
        "SELECT code, pass_hash, last_updated "
        "FROM file_storage WHERE user = :user ORDER BY last_updated DESC"
    )
    rows = db.execute(sql, {"user": user}).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="No files found for user.")

    codes = []
    for row in rows:
        if _verify_password(password, row.pass_hash):
            codes.append({
                "code": row.code,
                "last_updated": str(row.last_updated),
            })

    if not codes:
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    return {"user": user, "count": len(codes), "codes": codes}


@router.get(
    "/{code}",
    summary="Retrieve JSON data by code",
    description="Returns the stored JSON if the provided credentials match.",
)
def get_entry(
    code: str,
    user: str = Query(..., description="Username"),
    password: str = Query(..., description="Password"),
    db: Session = Depends(get_db),
):
    row = _get_entry(code, db)
    _authenticate(row, user, password)

    stored = row.json_data
    if isinstance(stored, str):
        stored = json.loads(stored)

    return {
        "code": code,
        "user": row.user,
        "json": stored,
        "last_updated": str(row.last_updated),
    }


@router.put(
    "/{code}",
    summary="Update JSON data by code",
    description="Replaces the stored JSON if the provided credentials match.",
)
def update_entry(code: str, body: StorageUpdateRequest, db: Session = Depends(get_db)):
    row = _get_entry(code, db)
    _authenticate(row, body.user, body.password)

    try:
        json_str = json.dumps(body.data)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Data is not valid JSON.")

    sql = text(
        "UPDATE file_storage SET json_data = :json_data, last_updated = NOW() WHERE code = :code"
    )
    db.execute(sql, {"json_data": json_str, "code": code})
    db.commit()

    return {"status": "updated", "code": code}


@router.delete(
    "/{code}",
    summary="Delete a file storage entry",
    description="Removes the entry if the provided credentials match.",
)
def delete_entry(code: str, body: StorageAuthRequest, db: Session = Depends(get_db)):
    row = _get_entry(code, db)
    _authenticate(row, body.user, body.password)

    sql = text("DELETE FROM file_storage WHERE code = :code")
    db.execute(sql, {"code": code})
    db.commit()

    return {"status": "deleted", "code": code}
