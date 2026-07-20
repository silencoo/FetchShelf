from pydantic import BaseModel


class APIModel(BaseModel):
    # Optional collector-pool override.  An empty value uses policy routing;
    # explicit cookie/proxy values and an unconfigured pool retain legacy
    # compatibility inside the server dispatcher.
    identity_id: str = ""
    cookie: str = ""
    proxy: str = ""
    source: bool = False
