from .base import APIModel


class Detail(APIModel):
    detail_id: str


class DetailTikTok(Detail):
    detail_id: str = ""
    detail_url: str = ""
