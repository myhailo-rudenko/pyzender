from typing import List, Optional

from pydantic import BaseModel, Field


class Data(BaseModel):
    items: dict
    key: str = Field(..., description="example: 'qbittorrent.torrent'")
    append_key: str = Field("", description="example: f'[{name}]'")
    timestamp: int
    receiver_hostname: Optional[str]
    receiver_address: Optional[str]


class Discovery(BaseModel):
    key: str = Field(..., description="example: 'qbittorrent.torrent.discovery'")
    macros: str = Field(..., description="example: '{#TORRENT_NAME}'")
    values: List[str]
    receiver_hostname: Optional[str]
    receiver_address: Optional[str]
