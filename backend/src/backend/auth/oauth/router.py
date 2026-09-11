"""`/auth/oauth` endpoints, mounted onto the `/auth` router."""

from fastapi import APIRouter

router = APIRouter(prefix="/oauth")
