from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_db

router = APIRouter()

HOME_FIELDS = (
    "title", "street", "zip", "city", "canton", "price", "size", "rooms",
    "built", "renovated", "house_type", "floor", "url", "main_image",
    "status", "notes", "realtor_name", "realtor_phone", "realtor_email",
    "garage", "garage_included", "garage_price",
)

HOME_SELECT = (
    "id", "user_id", *HOME_FIELDS, "updated_at"
)

VISIT_SELECT = ("id", "home_id", "date", "time")
LINK_SELECT = ("id", "home_id", "title", "url")


class HomeCreateRequest(BaseModel):
    user_id: int
    title: Optional[str] = None
    street: Optional[str] = None
    zip: Optional[str] = None
    city: Optional[str] = None
    canton: Optional[str] = None
    price: Optional[float] = None
    size: Optional[float] = None
    rooms: Optional[float] = None
    built: Optional[int] = None
    renovated: Optional[int] = None
    house_type: Optional[str] = None
    floor: Optional[int] = None
    url: Optional[str] = None
    main_image: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    realtor_name: Optional[str] = None
    realtor_phone: Optional[str] = None
    realtor_email: Optional[str] = None
    garage: Optional[int] = None
    garage_included: Optional[bool] = None
    garage_price: Optional[float] = None


class HomeUpdateRequest(HomeCreateRequest):
    user_id: Optional[int] = None


class VisitCreateRequest(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None


class LinkCreateRequest(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None


def _clean(value):
    if isinstance(value, bool):
        return int(value)
    return value


def _collect_fields(body) -> dict:
    fields = {}
    for name in HOME_FIELDS:
        value = getattr(body, name)
        if value is not None:
            fields[name] = _clean(value)
    return fields


def _get_home(home_id: int, db: Session):
    sql = text(f"SELECT {', '.join(HOME_SELECT)} FROM homes WHERE id = :id")
    return db.execute(sql, {"id": home_id}).fetchone()


def _require_home(home_id: int, db: Session):
    row = _get_home(home_id, db)
    if row is None:
        raise HTTPException(status_code=404, detail="Home not found.")
    return row


def _home_to_dict(row) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "title": row.title,
        "street": row.street,
        "zip": row.zip,
        "city": row.city,
        "canton": row.canton,
        "price": float(row.price) if row.price is not None else None,
        "size": float(row.size) if row.size is not None else None,
        "rooms": float(row.rooms) if row.rooms is not None else None,
        "built": row.built,
        "renovated": row.renovated,
        "house_type": row.house_type,
        "floor": row.floor,
        "url": row.url,
        "main_image": row.main_image,
        "status": row.status,
        "notes": row.notes,
        "realtor_name": row.realtor_name,
        "realtor_phone": row.realtor_phone,
        "realtor_email": row.realtor_email,
        "garage": row.garage,
        "garage_included": bool(row.garage_included) if row.garage_included is not None else None,
        "garage_price": float(row.garage_price) if row.garage_price is not None else None,
        "updated_at": str(row.updated_at),
    }


def _visit_to_dict(row) -> dict:
    return {
        "id": row.id,
        "home_id": row.home_id,
        "date": str(row.date) if row.date is not None else None,
        "time": str(row.time) if row.time is not None else None,
    }


def _link_to_dict(row) -> dict:
    return {
        "id": row.id,
        "home_id": row.home_id,
        "title": row.title,
        "url": row.url,
    }


@router.post(
    "",
    summary="Create a home",
    description="Adds a real-estate listing under a user_id. All fields except user_id are optional.",
)
def create_home(body: HomeCreateRequest, db: Session = Depends(get_db)):
    fields = _collect_fields(body)
    fields["user_id"] = body.user_id

    cols = ", ".join(fields)
    placeholders = ", ".join(f":{name}" for name in fields)
    sql = text(f"INSERT INTO homes ({cols}) VALUES ({placeholders})")
    result = db.execute(sql, fields)
    db.commit()

    return {"status": "created", "id": result.lastrowid}


@router.get(
    "",
    summary="List homes of a user",
    description="Returns every home belonging to the given user_id, newest first.",
)
def list_homes(
    user_id: int = Query(..., description="ID of the user"),
    db: Session = Depends(get_db),
):
    sql = text(
        f"SELECT {', '.join(HOME_SELECT)} FROM homes "
        "WHERE user_id = :user_id ORDER BY updated_at DESC"
    )
    rows = db.execute(sql, {"user_id": user_id}).fetchall()
    return {"user_id": user_id, "count": len(rows), "homes": [_home_to_dict(r) for r in rows]}


@router.get(
    "/{home_id}",
    summary="Get a home with its visits and links",
    description="Returns a single home including its nested visits and links.",
)
def get_home(home_id: int, db: Session = Depends(get_db)):
    home = _require_home(home_id, db)

    visits = db.execute(
        text(f"SELECT {', '.join(VISIT_SELECT)} FROM visits "
             "WHERE home_id = :home_id ORDER BY date IS NULL, date DESC, time DESC"),
        {"home_id": home_id},
    ).fetchall()
    links = db.execute(
        text(f"SELECT {', '.join(LINK_SELECT)} FROM links "
             "WHERE home_id = :home_id ORDER BY id"),
        {"home_id": home_id},
    ).fetchall()

    result = _home_to_dict(home)
    result["visits"] = [_visit_to_dict(v) for v in visits]
    result["links"] = [_link_to_dict(l) for l in links]
    return result


@router.put(
    "/{home_id}",
    summary="Update a home",
    description="Partially updates a home. Only the provided fields are changed.",
)
def update_home(home_id: int, body: HomeUpdateRequest, db: Session = Depends(get_db)):
    _require_home(home_id, db)

    fields = _collect_fields(body)
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    sets = ", ".join(f"{name} = :{name}" for name in fields)
    sql = text(f"UPDATE homes SET {sets} WHERE id = :home_id")
    params = {**fields, "home_id": home_id}
    db.execute(sql, params)
    db.commit()

    return {"status": "updated", "id": home_id}


@router.delete(
    "/{home_id}",
    summary="Delete a home",
    description="Removes the home and its visits and links (cascade).",
)
def delete_home(home_id: int, db: Session = Depends(get_db)):
    _require_home(home_id, db)

    db.execute(text("DELETE FROM homes WHERE id = :id"), {"id": home_id})
    db.commit()

    return {"status": "deleted", "id": home_id}


@router.post(
    "/{home_id}/visits",
    summary="Create a visit",
    description="Adds a visit to a home. date and time are optional strings.",
)
def create_visit(home_id: int, body: VisitCreateRequest, db: Session = Depends(get_db)):
    _require_home(home_id, db)

    sql = text("INSERT INTO visits (home_id, date, time) VALUES (:home_id, :date, :time)")
    result = db.execute(sql, {
        "home_id": home_id,
        "date": body.date or None,
        "time": body.time or None,
    })
    db.commit()

    return {"status": "created", "id": result.lastrowid, "home_id": home_id}


@router.get(
    "/{home_id}/visits",
    summary="List visits of a home",
    description="Returns every visit for the home.",
)
def list_visits(home_id: int, db: Session = Depends(get_db)):
    _require_home(home_id, db)

    rows = db.execute(
        text(f"SELECT {', '.join(VISIT_SELECT)} FROM visits "
             "WHERE home_id = :home_id ORDER BY date IS NULL, date DESC, time DESC"),
        {"home_id": home_id},
    ).fetchall()
    return {"home_id": home_id, "count": len(rows), "visits": [_visit_to_dict(r) for r in rows]}


@router.put(
    "/{home_id}/visits/{visit_id}",
    summary="Update a visit",
    description="Partially updates a visit's date/time.",
)
def update_visit(
    home_id: int, visit_id: int, body: VisitCreateRequest, db: Session = Depends(get_db)
):
    fields = {}
    if body.date is not None:
        fields["date"] = body.date
    if body.time is not None:
        fields["time"] = body.time
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    sets = ", ".join(f"{name} = :{name}" for name in fields)
    sql = text(f"UPDATE visits SET {sets} WHERE id = :visit_id AND home_id = :home_id")
    params = {**fields, "visit_id": visit_id, "home_id": home_id}
    result = db.execute(sql, params)
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Visit not found.")
    return {"status": "updated", "id": visit_id}


@router.delete(
    "/{home_id}/visits/{visit_id}",
    summary="Delete a visit",
    description="Removes a visit from the home.",
)
def delete_visit(home_id: int, visit_id: int, db: Session = Depends(get_db)):
    result = db.execute(
        text("DELETE FROM visits WHERE id = :visit_id AND home_id = :home_id"),
        {"visit_id": visit_id, "home_id": home_id},
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Visit not found.")
    return {"status": "deleted", "id": visit_id}


@router.post(
    "/{home_id}/links",
    summary="Create a link",
    description="Adds a link (listing page, map, …) to a home.",
)
def create_link(home_id: int, body: LinkCreateRequest, db: Session = Depends(get_db)):
    _require_home(home_id, db)

    sql = text("INSERT INTO links (home_id, title, url) VALUES (:home_id, :title, :url)")
    result = db.execute(sql, {
        "home_id": home_id,
        "title": body.title or None,
        "url": body.url or None,
    })
    db.commit()

    return {"status": "created", "id": result.lastrowid, "home_id": home_id}


@router.get(
    "/{home_id}/links",
    summary="List links of a home",
    description="Returns every link attached to the home.",
)
def list_links(home_id: int, db: Session = Depends(get_db)):
    _require_home(home_id, db)

    rows = db.execute(
        text(f"SELECT {', '.join(LINK_SELECT)} FROM links "
             "WHERE home_id = :home_id ORDER BY id"),
        {"home_id": home_id},
    ).fetchall()
    return {"home_id": home_id, "count": len(rows), "links": [_link_to_dict(r) for r in rows]}


@router.put(
    "/{home_id}/links/{link_id}",
    summary="Update a link",
    description="Partially updates a link's title/url.",
)
def update_link(
    home_id: int, link_id: int, body: LinkCreateRequest, db: Session = Depends(get_db)
):
    fields = {}
    if body.title is not None:
        fields["title"] = body.title
    if body.url is not None:
        fields["url"] = body.url
    if not fields:
        raise HTTPException(status_code=400, detail="Nothing to update.")

    sets = ", ".join(f"{name} = :{name}" for name in fields)
    sql = text(f"UPDATE links SET {sets} WHERE id = :link_id AND home_id = :home_id")
    params = {**fields, "link_id": link_id, "home_id": home_id}
    result = db.execute(sql, params)
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Link not found.")
    return {"status": "updated", "id": link_id}


@router.delete(
    "/{home_id}/links/{link_id}",
    summary="Delete a link",
    description="Removes a link from the home.",
)
def delete_link(home_id: int, link_id: int, db: Session = Depends(get_db)):
    result = db.execute(
        text("DELETE FROM links WHERE id = :link_id AND home_id = :home_id"),
        {"link_id": link_id, "home_id": home_id},
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Link not found.")
    return {"status": "deleted", "id": link_id}