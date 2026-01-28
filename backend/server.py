from fastapi import FastAPI, APIRouter, Request, HTTPException, Depends, status, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from datetime import datetime, timezone
import uuid
import shutil
from typing import Optional, List

from models import (
    UserCreate, UserLogin, User, UserRole,
    OrderCreate, Order, OrderUpdate, OrderStatus, OrderSpecs
)
from auth import (
    get_password_hash, verify_password, create_access_token, decode_access_token
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(ROOT_DIR / "uploads")), name="uploads")

# Jinja2 templates
templates = Jinja2Templates(directory=str(ROOT_DIR / "templates"))

# Create API router
api_router = APIRouter(prefix="/api")

# Helper function to get current user from token
async def get_current_user(request: Request) -> Optional[User]:
    # Try to get token from Authorization header first
    auth_header = request.headers.get("Authorization")
    token = None
    
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "")
    else:
        # Fallback to cookie
        token = request.cookies.get("access_token")
    
    if not token:
        return None
    
    payload = decode_access_token(token)
    if not payload:
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        return None
    
    user_doc = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user_doc:
        return None
    
    return User(**user_doc)

async def require_auth(request: Request) -> User:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

async def require_staff(request: Request) -> User:
    user = await require_auth(request)
    if user.role != UserRole.STAFF:
        raise HTTPException(status_code=403, detail="Staff access required")
    return user

# ============ TEMPLATE ROUTES (HTML Pages) ============

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = await get_current_user(request)
    return templates.TemplateResponse("home.html", {"request": request, "user": user})

@app.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request):
    return templates.TemplateResponse("authorization.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: User = Depends(require_auth)):
    # Get user's orders
    orders = await db.orders.find({"user_id": user.id}, {"_id": 0}).sort("submitted_at", -1).to_list(100)
    return templates.TemplateResponse("client-dashboard.html", {
        "request": request,
        "user": user,
        "orders": orders
    })

@app.get("/order/new", response_class=HTMLResponse)
async def new_order(request: Request, user: User = Depends(require_auth)):
    return templates.TemplateResponse("client-order-configuration.html", {
        "request": request,
        "user": user
    })

@app.get("/staff/queue", response_class=HTMLResponse)
async def admin_queue(request: Request, user: User = Depends(require_staff)):
    # Get all orders for staff review
    orders = await db.orders.find({}, {"_id": 0}).sort("submitted_at", -1).to_list(1000)
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": user,
        "orders": orders
    })

# ============ API ROUTES ============

# Authentication APIs
@api_router.post("/auth/signup")
async def signup(user_data: UserCreate):
    # Check if user exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(user_data.password)
    
    user_doc = {
        "id": user_id,
        "email": user_data.email,
        "name": user_data.name,
        "password": hashed_password,
        "role": UserRole.CLIENT.value,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.users.insert_one(user_doc)
    
    # Create access token
    access_token = create_access_token(data={"sub": user_id})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": user_data.email,
            "name": user_data.name,
            "role": UserRole.CLIENT.value
        }
    }

@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    # Find user
    user_doc = await db.users.find_one({"email": credentials.email})
    if not user_doc:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Verify password
    if not verify_password(credentials.password, user_doc["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create access token
    access_token = create_access_token(data={"sub": user_doc["id"]})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user_doc["id"],
            "email": user_doc["email"],
            "name": user_doc["name"],
            "role": user_doc["role"]
        }
    }

@api_router.get("/auth/me")
async def get_me(user: User = Depends(require_auth)):
    return user

@api_router.post("/auth/logout")
async def logout():
    return {"message": "Logged out successfully"}

# Order APIs
@api_router.post("/orders")
async def create_order(
    specs: str = Form(...),
    gerber_file: Optional[UploadFile] = File(None),
    user: User = Depends(require_auth)
):
    # Parse specs from JSON string
    import json
    specs_data = json.loads(specs)
    order_specs = OrderSpecs(**specs_data)
    
    # Generate order ID
    order_id = f"NC-{str(uuid.uuid4())[:8].upper()}"
    
    # Handle file upload
    file_path = None
    if gerber_file:
        # Save file
        file_extension = gerber_file.filename.split('.')[-1]
        filename = f"{order_id}.{file_extension}"
        file_path = ROOT_DIR / "uploads" / filename
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(gerber_file.file, buffer)
        
        file_path = filename
    
    # Create order document
    now = datetime.now(timezone.utc)
    order_doc = {
        "order_id": order_id,
        "user_id": user.id,
        "status": OrderStatus.REVIEWING.value,
        "gerber_file": file_path,
        "specs": order_specs.model_dump(),
        "price": 0.00,
        "submitted_at": now.isoformat(),
        "updated_at": now.isoformat()
    }
    
    await db.orders.insert_one(order_doc)
    
    return {
        "order_id": order_id,
        "status": OrderStatus.REVIEWING.value,
        "message": "Order submitted successfully"
    }

@api_router.get("/orders")
async def get_user_orders(user: User = Depends(require_auth)):
    orders = await db.orders.find({"user_id": user.id}, {"_id": 0}).sort("submitted_at", -1).to_list(100)
    return orders

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str, user: User = Depends(require_auth)):
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Check if user owns the order or is staff
    if order["user_id"] != user.id and user.role != UserRole.STAFF:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return order

# Staff-only APIs
@api_router.get("/orders/all/list")
async def get_all_orders(user: User = Depends(require_staff)):
    orders = await db.orders.find({}, {"_id": 0}).sort("submitted_at", -1).to_list(1000)
    return orders

@api_router.patch("/orders/{order_id}")
async def update_order(
    order_id: str,
    update_data: OrderUpdate,
    user: User = Depends(require_staff)
):
    order = await db.orders.find_one({"order_id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Build update document
    update_doc = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if update_data.status:
        update_doc["status"] = update_data.status.value
    if update_data.price is not None:
        update_doc["price"] = update_data.price
    
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": update_doc}
    )
    
    return {"message": "Order updated successfully"}

# Include API router
app.include_router(api_router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Neurocircuit platform...")
    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.orders.create_index("order_id", unique=True)
    await db.orders.create_index("user_id")

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
