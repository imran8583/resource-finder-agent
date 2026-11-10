from typing import List
from pydantic import BaseModel


class SocialLinksResponse(BaseModel):
    links: List[str] = []


class ScrapedContentResponse(BaseModel):
    chunks: List[str] = []


class ContactInfoResponse(BaseModel):
    phone_numbers: List[str] = []
    addresses: List[str] = []


class DistanceResponse(BaseModel):
    distance: str = ""

