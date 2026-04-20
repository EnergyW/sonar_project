"""
Роутер для работы с отзывами.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from db.database import AsyncDatabase
from utils.api_utils import get_store_reviews, post_review_answer
from utils.ai_utils import generate_reply
from backend.auth_utils import get_current_user

router = APIRouter()


class ReplyRequest(BaseModel):
    text: str


class AIReplyRequest(BaseModel):
    review_text: str
    rating: int
    product_name: Optional[str] = None
    sku: Optional[str] = None
    pros: Optional[str] = None
    cons: Optional[str] = None
    offer_id: Optional[str] = None
    product_id: Optional[str] = None
    user_display: Optional[str] = None


# ---------- GET /stores/{id}/reviews ----------
@router.get("/{store_id}/reviews")
async def list_reviews(
    store_id: int,
    answered: bool = Query(False),
    limit: int = Query(50, le=100),
    current_user: dict = Depends(get_current_user),
):
    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
    if not store:
        raise HTTPException(404, "Магазин не найден")

    reviews = await get_store_reviews(store, answered=answered, limit=limit)

    return [
        {
            "id": r["id"],
            "text": r["text"],
            "rating": r["rating"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "product_name": r.get("product_name", ""),
            "sku": r.get("sku", ""),
            "answer": r.get("answer", ""),
            "user_name": r.get("user_name", ""),
            "pros": r.get("pros", ""),
            "cons": r.get("cons", ""),
            "supplier_article": r.get("supplierArticle", ""),
        }
        for r in reviews
    ]


# ---------- POST /stores/{id}/reviews/{review_id}/reply ----------
@router.post("/{store_id}/reviews/{review_id}/reply")
async def reply_to_review(
    store_id: int,
    review_id: str,
    data: ReplyRequest,
    current_user: dict = Depends(get_current_user),
):
    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
    if not store:
        raise HTTPException(404, "Магазин не найден")

    success = await post_review_answer(
        client_id=store.get("client_id", ""),
        api_key=store["api_key"],
        review_id=review_id,
        answer_text=data.text,
        platform=store["type"],
    )
    if not success:
        raise HTTPException(500, "Ошибка при отправке ответа")

    return {"message": "Ответ отправлен"}


# ---------- POST /stores/{id}/reviews/generate-reply ----------
@router.post("/{store_id}/reviews/generate-reply")
async def generate_ai_reply(
    store_id: int,
    data: AIReplyRequest,
    current_user: dict = Depends(get_current_user),
):
    async with AsyncDatabase() as db:
        store = await db.get_store_details(store_id)
        store_settings = await db.get_store_settings(store_id)
    if not store:
        raise HTTPException(404, "Магазин не найден")

    result = await generate_reply(
        review_text=data.review_text,
        rating=data.rating,
        client_config={
            "client_id": store.get("client_id", ""),
            "api_key": store["api_key"],
            "platform": store["type"],
        },
        store_settings=store_settings,
        product_name=data.product_name,
        sku=data.sku,
        pros=data.pros,
        cons=data.cons,
        offer_id=data.offer_id,
        product_id=data.product_id,
        user_display=data.user_display,
    )

    if not result.get("success"):
        raise HTTPException(500, result.get("error", "Ошибка генерации"))

    return {"text": result["text"]}
