from pydantic import BaseModel


class GoogleAuthRequest(BaseModel):
    code: str
    redirect_uri: str
