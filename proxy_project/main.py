import uvicorn
import logging
from fastapi import FastAPI # <--- This fixes the NameError
from app.routes import router
from app.utils import MessageFilter

# Configure logging
logging.basicConfig(level=logging.WARN, format='%(asctime)s - %(levelname)s - %(message)s')
root_logger = logging.getLogger()
root_logger.addFilter(MessageFilter())

# Initialize the FastAPI app
app = FastAPI(title="Modular Anthropic Proxy")

# Attach the routes from app/routes.py
app.include_router(router)

@app.get("/")
async def root():
    return {"message": "Anthropic Proxy is running (Modular Mode)"}

if __name__ == "__main__":
    # Match the port from your original mono file
    uvicorn.run(app, host="0.0.0.0", port=8083)