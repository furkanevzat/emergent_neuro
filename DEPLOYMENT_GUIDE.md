# Neurocircuit Platform - Complete Deployment Guide

## 🚀 Overview

Neurocircuit is a PCB prototyping and pooling platform with:
- **FastAPI Backend** with MongoDB
- **Client-Side HTML** with JavaScript
- **Smart Gerber Analysis** using Gerbonara
- **Order Batching/Pooling** for cost optimization
- **Admin Panel** with superpowers

---

## 🐳 Docker Deployment

### Prerequisites
- Docker & Docker Compose installed
- Ports 8001 (API) and 27017 (MongoDB) available

### Quick Start

```bash
# Clone or navigate to project directory
cd /app

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f web

# Stop services
docker-compose down

# Stop and remove volumes (reset database)
docker-compose down -v
```

### Environment Variables

Edit `docker-compose.yml` to customize:

```yaml
environment:
  - MONGO_URL=mongodb://db:27017
  - DB_NAME=neurocircuit_db
  - JWT_SECRET_KEY=your-secret-key-change-in-production
  - CORS_ORIGINS=http://localhost:3000,http://localhost:8001
```

### Production Deployment

For production, update:
1. Set strong `JWT_SECRET_KEY`
2. Use MongoDB with authentication
3. Configure proper CORS origins
4. Set up SSL/TLS certificates
5. Use volume mounts for persistent uploads

---

## 📦 Features Implemented

### 1. 👑 Super Admin Capabilities

#### Global Order Visibility
- **Endpoint**: `GET /api/orders/all/list`
- Admin sees ALL orders from ALL users
- Sortable by date, status, user

#### User Management
- **Endpoint**: `GET /api/users/all`
- View all registered users
- See email, join date, role, user ID
- UI: Admin Panel → Users Tab

#### File Download
- Download Gerber files directly from admin panel
- Files stored in `/app/backend/uploads/`
- Naming: `{ORDER_ID}.{extension}`

### 2. 🧠 Smart File Analysis (Gerbonara)

**Automatic Gerber Analysis on Upload:**

When a user uploads a Gerber ZIP file:
1. **Gerbonara** extracts layer stack
2. Analyzes:
   - Layer count (actual copper layers)
   - Board dimensions (width × height in mm)
3. Saves to `specs` field in MongoDB

**Example Order Document:**
```json
{
  "order_id": "NC-ABC12345",
  "specs": {
    "layers": 4,
    "thickness": "1.6 mm",
    "quantity": 20,
    "analysis": "success",
    "layer_count": 4,
    "board_width_mm": 50.8,
    "board_height_mm": 75.2
  }
}
```

**Fallback Behavior:**
- If analysis fails: `{"analysis": "failed", "error": "..."}`
- Upload is NOT blocked
- Order proceeds with user-provided specs

### 3. 📦 Logical Batching System

**Create Production Batches:**
1. Admin selects orders in "Reviewing" status
2. Clicks "Create Batch"
3. System:
   - Creates `Batch` document in MongoDB
   - Updates order status to `"pooling"`
   - Links orders to `batch_id`

**Batch Model:**
```json
{
  "batch_id": "BATCH-12345678",
  "status": "active",
  "created_at": "2025-01-28T12:00:00Z",
  "orders_included": ["NC-ABC", "NC-DEF"],
  "total_orders": 2
}
```

**Admin Features:**
- View all active batches
- See orders in each batch
- Update batch status (active → processing → completed)

**Note:** This is **logical pooling only**. Physical Gerber merging is not implemented.

---

## 🛠️ API Reference

### Authentication

**POST /api/auth/signup**
```json
{
  "email": "user@example.com",
  "password": "secure123",
  "name": "John Doe"
}
```

**POST /api/auth/login**
```json
{
  "email": "user@example.com",
  "password": "secure123"
}
```
Returns JWT token.

### Orders

**POST /api/orders** (Client)
- Multipart form with specs + optional Gerber file
- Automatically analyzes Gerber with Gerbonara
- Returns order_id and analysis results

**GET /api/orders** (Client)
- Get logged-in user's orders

**GET /api/orders/all/list** (Admin only)
- Get ALL orders from ALL users

**PATCH /api/orders/{order_id}** (Admin only)
```json
{
  "status": "quoted",
  "price": 145.50
}
```

### Batches (Admin Only)

**POST /api/batches**
```json
{
  "order_ids": ["NC-ABC", "NC-DEF"]
}
```

**GET /api/batches**
- List all batches

**GET /api/batches/{batch_id}**
- Get batch details with orders

**PATCH /api/batches/{batch_id}**
```json
{
  "status": "processing"
}
```

### Users (Admin Only)

**GET /api/users/all**
- List all registered users
- Excludes password field

---

## 🗄️ Database Schema

### Collections

1. **users**
```json
{
  "id": "uuid",
  "email": "user@example.com",
  "name": "John Doe",
  "password": "bcrypt_hash",
  "role": "client" | "staff",
  "created_at": "ISO datetime"
}
```

2. **orders**
```json
{
  "order_id": "NC-12345678",
  "user_id": "uuid",
  "status": "reviewing" | "quoted" | "pooling" | "production" | "shipped" | "delivered",
  "gerber_file": "filename.zip",
  "batch_id": "BATCH-12345678", // optional
  "specs": {
    "substrate": "FR-4 Standard (TG150)",
    "layers": 4,
    "thickness": "1.6 mm",
    "quantity": 20,
    "finish": "HASL (Lead-Free)",
    "mask_color": "Green",
    "silkscreen": "White",
    "copper_weight": "1oz",
    // Gerbonara analysis results:
    "analysis": "success",
    "layer_count": 4,
    "board_width_mm": 50.8,
    "board_height_mm": 75.2
  },
  "price": 0.00,
  "submitted_at": "ISO datetime",
  "updated_at": "ISO datetime"
}
```

3. **batches**
```json
{
  "batch_id": "BATCH-12345678",
  "status": "active" | "processing" | "completed",
  "created_at": "ISO datetime",
  "orders_included": ["NC-ABC", "NC-DEF"],
  "total_orders": 2
}
```

---

## 🔐 Security

### Authentication
- JWT tokens (7-day expiry)
- Bcrypt password hashing
- Role-based access control (client/staff)

### Authorization
- Clients: Can only see their own orders
- Staff: Full access to all orders, users, batches

### File Security
- Uploaded files validated by extension
- Stored with UUID-based order IDs
- Download requires authentication

---

## 🧪 Testing

### Manual Testing

**1. Test Order Creation with Gerber Analysis:**
```bash
# Create test Gerber ZIP (optional)
# Upload via UI or API

curl -X POST "http://localhost:8001/api/orders" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F 'specs={"substrate":"FR-4","layers":4,"thickness":"1.6 mm","quantity":10,"finish":"HASL","mask_color":"Green","silkscreen":"White","copper_weight":"1oz"}' \
  -F 'gerber_file=@test.zip'
```

**2. Test Admin Order Update:**
```bash
curl -X PATCH "http://localhost:8001/api/orders/NC-ABC12345" \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"quoted","price":125.00}'
```

**3. Test Batch Creation:**
```bash
curl -X POST "http://localhost:8001/api/batches" \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"order_ids":["NC-ABC","NC-DEF"]}'
```

### Test Accounts

**Client:**
- Email: `test@neurocircuit.io`
- Password: `test123`

**Admin:**
- Email: `admin@neurocircuit.io`
- Password: `admin123`

---

## 📊 Admin Panel Features

Access: `/admin.html` (requires staff role)

### Tabs

1. **Order Queue**
   - View all orders with status
   - See Gerber analysis results
   - Update order status and pricing
   - Download Gerber files
   - Select orders for batching
   - Create production batches

2. **Batches**
   - View all active batches
   - See orders in each batch
   - Track batch status

3. **Users**
   - View all registered users
   - See email, join date, role
   - User ID for support

### Batch Workflow
1. Filter orders with "Reviewing" status
2. Select checkboxes next to orders
3. Click "Create Batch"
4. Orders move to "Pooling" status
5. View batch in Batches tab

---

## 🚧 Known Limitations

1. **Physical Panelization**: Not implemented
   - Current batching is logical grouping only
   - No automatic Gerber file merging
   - Manual panelization required

2. **Gerber Analysis**:
   - Requires valid Gerber file format
   - Analysis failures are logged but don't block upload
   - Complex boards may have partial analysis

3. **Scaling**:
   - File storage is local filesystem
   - For production, use S3/object storage
   - MongoDB should use replica sets

---

## 📝 Development Notes

### Adding New Order Status

1. Update `OrderStatus` enum in `models.py`
2. Add badge styling in `admin.html`
3. Update status dropdown in update modal

### Adding Batch Status

1. Update batch status options in UI
2. Add corresponding badge colors
3. Update status transitions in admin panel

### Customizing Gerber Analysis

Edit the Gerbonara section in `server.py`:
```python
# Add more analysis metrics
stack = LayerStack.from_zip_file(str(file_path))
drill_count = len(stack.drill_layers)
# etc.
```

---

## 🐛 Troubleshooting

### Gerbonara Import Error
```bash
# Reinstall with system dependencies
pip install gerbonara --force-reinstall
```

### MongoDB Connection Failed
```bash
# Check MongoDB is running
docker-compose ps

# View MongoDB logs
docker-compose logs db
```

### File Upload Fails
```bash
# Check uploads directory permissions
chmod 777 /app/backend/uploads/
```

### Admin Can't See Orders
```bash
# Verify user role
mongo neurocircuit_db
db.users.find({email: "admin@neurocircuit.io"})

# Should show: role: "staff"
```

---

## 📈 Next Steps

1. **Email Notifications**
   - Send quote notifications
   - Status update alerts

2. **Physical Panelization**
   - Integrate Gerber manipulation library
   - Merge multiple designs into single panel
   - Generate manufacturing files

3. **Cost Calculation**
   - Automatic pricing based on specs
   - Pooling discounts
   - Quantity breaks

4. **Payment Integration**
   - Stripe checkout
   - Quote acceptance workflow
   - Invoice generation

5. **Production Tracking**
   - Manufacturer integration
   - Real-time status updates
   - Shipping notifications

---

## 📞 Support

For issues or questions:
1. Check logs: `docker-compose logs -f web`
2. Verify database: `mongo neurocircuit_db`
3. Test endpoints with curl/Postman
4. Check admin panel browser console

---

## 📄 License

Proprietary - Neurocircuit Platform
