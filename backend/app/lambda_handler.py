"""AWS Lambda entry point: adapts the FastAPI app to API Gateway's event/response shape."""

from mangum import Mangum

from .main import app

handler = Mangum(app)
