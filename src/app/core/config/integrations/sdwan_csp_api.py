from pydantic import BaseModel


class SDWANCspApiConfig(BaseModel):
    base_url: str
    cert_path: str
    username: str
    password: str
    vpc_id: str


class IntegrationsConfig(BaseModel):
    sdwan_csp_api: SDWANCspApiConfig
