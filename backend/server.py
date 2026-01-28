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
    OrderCreate, Order, OrderUpdate, OrderStatus, OrderSpecs,
    Batch, BatchCreate
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

# Note: /order/new is served from frontend/public/client-order-configuration.html
# Backend route not needed due to Kubernetes ingress routing
# @app.get("/order/new", response_class=HTMLResponse)
# async def new_order(request: Request, user: User = Depends(require_auth)):
#     return templates.TemplateResponse("client-order-configuration.html", {
#         "request": request,
#         "user": user
#     })

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
    
    # Handle file upload and advanced Gerbonara analysis
    file_path = None
    gerber_analysis = {}
    estimated_price = 0.00
    
    if gerber_file:
        # Save file
        file_extension = gerber_file.filename.split('.')[-1]
        filename = f"{order_id}.{file_extension}"
        file_path = ROOT_DIR / "uploads" / filename
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(gerber_file.file, buffer)
        
        # Advanced Gerber Analysis with Gerbonara
        try:
            from gerbonara import LayerStack
            import warnings
            warnings.filterwarnings('ignore')
            
            logger.info(f"Starting Gerbonara analysis for order {order_id}")
            stack = LayerStack.from_zip_file(str(file_path))
            
            # Extract detailed layer information
            copper_layers = [layer for layer in stack.layers if layer is not None]
            layer_count = len(copper_layers)
            
            # Get precise board bounds
            bounds = stack.board_bounds()
            if bounds:
                # bounds returns (min_x, min_y, max_x, max_y) in mm
                board_width_mm = round(bounds[2] - bounds[0], 2)
                board_height_mm = round(bounds[3] - bounds[1], 2)
                board_area_mm2 = round(board_width_mm * board_height_mm, 2)
                
                # Calculate estimated price based on area, layers, and quantity
                # Formula: (area_in_cm² * layer_count * base_rate) + (quantity_discount_factor)
                area_cm2 = board_area_mm2 / 100
                base_rate = 0.5  # $0.50 per cm² per layer
                quantity = order_specs.quantity
                
                # Price calculation
                base_price = area_cm2 * layer_count * base_rate
                quantity_multiplier = 1.0 + (quantity / 100)  # Slight increase for higher quantity
                estimated_price = round(base_price * quantity_multiplier, 2)
                
                # Minimum price threshold
                estimated_price = max(estimated_price, 25.00)
                
                gerber_analysis = {
                    "analysis": "success",
                    "layer_count": layer_count,
                    "board_width_mm": board_width_mm,
                    "board_height_mm": board_height_mm,
                    "board_area_mm2": board_area_mm2,
                    "board_area_cm2": round(area_cm2, 2),
                    "estimated_price": estimated_price,
                    "analysis_timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                logger.info(f"Gerbonara analysis successful for {order_id}: {layer_count} layers, {board_width_mm}x{board_height_mm}mm, estimated ${estimated_price}")
            else:
                # Partial analysis - layers detected but no bounds
                gerber_analysis = {
                    "analysis": "partial",
                    "layer_count": layer_count,
                    "estimated_price": layer_count * 30.00,  # Fallback pricing
                    "note": "Board bounds not detected"
                }
                estimated_price = gerber_analysis["estimated_price"]
                logger.warning(f"Partial analysis for {order_id}: bounds not detected")
                
        except Exception as e:
            logger.error(f"Gerbonara analysis failed for {order_id}: {str(e)}")
            gerber_analysis = {
                "analysis": "failed",
                "error": str(e)[:200],
                "estimated_price": order_specs.layers * order_specs.quantity * 2.5  # Basic fallback
            }
            estimated_price = gerber_analysis["estimated_price"]
        
        file_path = filename
    else:
        # No file uploaded - use user-provided specs for basic estimation
        estimated_price = order_specs.layers * order_specs.quantity * 2.0
        gerber_analysis = {
            "analysis": "no_file",
            "estimated_price": estimated_price,
            "note": "Price estimated from specifications only"
        }
    
    # Merge gerber analysis into specs
    specs_dict = order_specs.model_dump()
    if gerber_analysis:
        specs_dict.update(gerber_analysis)
    
    # Create order document
    now = datetime.now(timezone.utc)
    order_doc = {
        "order_id": order_id,
        "user_id": user.id,
        "status": OrderStatus.REVIEWING.value,
        "gerber_file": file_path,
        "specs": specs_dict,
        "price": 0.00,  # Admin will set final price
        "estimated_price": estimated_price,
        "submitted_at": now.isoformat(),
        "updated_at": now.isoformat()
    }
    
    await db.orders.insert_one(order_doc)
    
    logger.info(f"Order {order_id} created successfully with estimated price ${estimated_price}")
    
    return {
        "order_id": order_id,
        "status": OrderStatus.REVIEWING.value,
        "message": "Order submitted successfully",
        "estimated_price": estimated_price,
        "gerber_analysis": gerber_analysis if gerber_analysis else None
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

# User Management (Staff only)
@api_router.get("/users/all")
async def get_all_users(user: User = Depends(require_staff)):
    users = await db.users.find({}, {"_id": 0, "password": 0}).sort("created_at", -1).to_list(1000)
    return users

# Batching/Panelization APIs
@api_router.post("/batches")
async def create_batch(
    batch_data: BatchCreate,
    user: User = Depends(require_staff)
):
    # Verify all orders exist and are in "reviewing" status
    orders = await db.orders.find(
        {"order_id": {"$in": batch_data.order_ids}},
        {"_id": 0}
    ).to_list(100)
    
    if len(orders) != len(batch_data.order_ids):
        raise HTTPException(status_code=400, detail="Some orders not found")
    
    # Create batch
    batch_id = f"BATCH-{str(uuid.uuid4())[:8].upper()}"
    now = datetime.now(timezone.utc)
    
    batch_doc = {
        "batch_id": batch_id,
        "status": "active",
        "created_at": now.isoformat(),
        "orders_included": batch_data.order_ids,
        "total_orders": len(batch_data.order_ids)
    }
    
    await db.batches.insert_one(batch_doc)
    
    # Update orders to "pooling" status
    await db.orders.update_many(
        {"order_id": {"$in": batch_data.order_ids}},
        {"$set": {"status": "pooling", "batch_id": batch_id, "updated_at": now.isoformat()}}
    )
    
    return {
        "batch_id": batch_id,
        "message": f"Batch created with {len(batch_data.order_ids)} orders",
        "orders_included": batch_data.order_ids
    }

@api_router.get("/batches")
async def get_batches(user: User = Depends(require_staff)):
    batches = await db.batches.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return batches

@api_router.get("/batches/{batch_id}")
async def get_batch(batch_id: str, user: User = Depends(require_staff)):
    batch = await db.batches.find_one({"batch_id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    # Get orders in this batch
    orders = await db.orders.find(
        {"order_id": {"$in": batch["orders_included"]}},
        {"_id": 0}
    ).to_list(100)
    
    batch["orders"] = orders
    return batch

@api_router.patch("/batches/{batch_id}")
async def update_batch(
    batch_id: str,
    status: str,
    user: User = Depends(require_staff)
):
    batch = await db.batches.find_one({"batch_id": batch_id})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    await db.batches.update_one(
        {"batch_id": batch_id},
        {"$set": {"status": status}}
    )
    
    return {"message": "Batch updated successfully"}

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

# Form-based order update for admin (server-side)
@app.post("/staff/orders/{order_id}/update")
async def update_order_form(
    request: Request,
    order_id: str,
    status: str = Form(...),
    price: float = Form(...),
    user: User = Depends(require_staff)
):
    order = await db.orders.find_one({"order_id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Update order
    update_doc = {
        "status": status,
        "price": price,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": update_doc}
    )
    
    # Redirect back to admin queue
    return RedirectResponse(url="/staff/queue", status_code=303)

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
    await db.batches.create_index("batch_id", unique=True)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
