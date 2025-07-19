from fastapi import APIRouter
from fastapi import Header, HTTPException, Depends
import os
import logging
from pydantic import BaseModel
from typing import Any, Optional

# classes
from events.store_events import Events_MongoDatabase
events_database=Events_MongoDatabase()


# authentication
API_KEY = os.getenv("DEBALES_PYTHON_API_KEY")

async def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/events",   # everything in this file lives under /items
    tags=["Events"],    # shows up in the docs UI
)

class eventsRequest(BaseModel):
    event: Optional[str] = None
    timestamp: Optional[str] = None
    userLocation: Optional[str] = None
    refferPage:Optional[str] = None
    currentPage:Optional[str] = None
    nameSpace:Optional[str] = None



@router.post("", summary="Add events")

async def events(request:eventsRequest, _: str = Depends(verify_api_key)):
    try:
        event={
            "event":request.event,
            "timestamp":request.timestamp,
            "userLocation":request.userLocation,
            "refferPage":request.refferPage,
            "currentPage":request.currentPage,
            "nameSpace":request.nameSpace
        }
        events_database.insert_events(event)
        return True
        

    except Exception as e:
        logger.error("Error processing Events request: %s", str(e))
        raise HTTPException(status_code=404, detail="Bot Doesnot exist in platform")
