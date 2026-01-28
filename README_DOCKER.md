# Neurocircuit Platform - Docker Quick Start

## 🚀 One-Command Setup

```bash
docker-compose up -d
```

That's it! Your PCB pooling platform is now running at:
- **API**: http://localhost:8001
- **MongoDB**: mongodb://localhost:27017

## 📦 What's Included

### Services
- **web**: FastAPI backend with Gerbonara analysis
- **db**: MongoDB 6.0

### Features
✅ Smart Gerber file analysis  
✅ Order batching/pooling  
✅ Admin panel with superpowers  
✅ User management  
✅ JWT authentication  

## 🔧 Configuration

Edit `docker-compose.yml`:

```yaml
environment:
  - JWT_SECRET_KEY=your-secret-key-here  # Change in production!
  - MONGO_URL=mongodb://db:27017
  - DB_NAME=neurocircuit_db
```

## 📊 Test Accounts

### Client
- Email: `test@neurocircuit.io`
- Password: `test123`

### Admin
- Email: `admin@neurocircuit.io`
- Password: `admin123`

## 🛠️ Common Commands

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f web

# Restart backend
docker-compose restart web

# Stop services
docker-compose down

# Reset database
docker-compose down -v && docker-compose up -d

# Access MongoDB shell
docker-compose exec db mongosh neurocircuit_db
```

## 🔍 Health Check

```bash
# Test API
curl http://localhost:8001/api/

# Check MongoDB
docker-compose exec db mongosh --eval "db.version()"
```

## 📁 Project Structure

```
/app/
├── backend/
│   ├── server.py          # FastAPI app
│   ├── models.py          # Pydantic models
│   ├── auth.py            # JWT auth
│   ├── requirements.txt   # Python deps
│   ├── uploads/           # Gerber files
│   └── Dockerfile
├── docker-compose.yml
└── DEPLOYMENT_GUIDE.md    # Full documentation
```

## 🐛 Troubleshooting

**Port already in use:**
```bash
# Change ports in docker-compose.yml
ports:
  - "8002:8001"  # External:Internal
```

**Gerbonara analysis fails:**
```bash
# Rebuild with fresh dependencies
docker-compose build --no-cache web
```

**Database not persisting:**
```bash
# Check volumes
docker volume ls | grep neurocircuit
```

## 📚 Full Documentation

See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for:
- Complete API reference
- Database schema
- Admin panel guide
- Production deployment
- Security best practices

## 🔐 Production Checklist

Before deploying to production:

- [ ] Change `JWT_SECRET_KEY` to strong random value
- [ ] Enable MongoDB authentication
- [ ] Configure SSL/TLS certificates
- [ ] Set up proper CORS origins
- [ ] Use volume mounts for persistent storage
- [ ] Set up backup strategy
- [ ] Configure monitoring/logging
- [ ] Review security settings

## 📞 Support

Issues? Check:
1. Logs: `docker-compose logs -f`
2. MongoDB: `docker-compose exec db mongosh`
3. Uploads directory: `ls -la backend/uploads/`

---

**Built with ❤️ for PCB makers**
