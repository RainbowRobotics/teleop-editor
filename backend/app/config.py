from pydantic import BaseModel


class Settings(BaseModel):
    local_default_port: int = 5005
    quest_default_port: int = 6000

    quest_ws_min_hz: int = 1
    quest_ws_max_hz: int = 200
    quest_ws_default_hz: int = 30
    
    
settings = Settings()