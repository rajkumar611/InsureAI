# Port Configuration Guide — InsureAI

Complete reference for all ports used in development, testing, and production.

---

## 🚀 Local Development (Recommended Setup)

Running the application locally requires **3 active ports**:

| Service | Port | Protocol | URL | Status |
|---------|------|----------|-----|--------|
| **PostgreSQL** | 5432 | TCP | `postgresql://dbinsureai:125QueenStreet@localhost:5432/aus_underwriting` | ✅ Required |
| **FastAPI Backend** | 8081 | HTTP | `http://localhost:8081` | ✅ Required |
| **Streamlit Frontend** | 8501 | HTTP | `http://localhost:8501` | ✅ Required |

### Quick Startup Checklist

```bash
# Terminal 1: PostgreSQL (if not already running)
docker compose -f deployment/docker-compose.yml up postgres -d

# Terminal 2: FastAPI Backend
cd backend && uv run python run.py
# Listens on: http://0.0.0.0:8081

# Terminal 3: Streamlit Frontend
cd frontend && uv run streamlit run underwriter_portal.py
# Listens on: http://localhost:8501
```

### Verify All Ports Are Open

```bash
# Windows PowerShell
netstat -ano | findstr ":5432"   # PostgreSQL
netstat -ano | findstr ":8081"   # FastAPI
netstat -ano | findstr ":8501"   # Streamlit

# Or test connectivity
curl http://localhost:8081/health         # Should return JSON
Invoke-WebRequest http://localhost:8501   # Should show Streamlit UI
psql -h localhost -U dbinsureai -d aus_underwriting -c "SELECT 1"  # Should return 1
```

---

## 🐳 Docker Compose Deployment

**Note:** docker-compose.yml uses different ports than local dev.

| Service | Port | URL | Notes |
|---------|------|-----|-------|
| **postgres** | 5432 | `postgres:5432` | Internal to Docker network |
| **api** | 8000 | `http://localhost:8000` | Exposed port (not 8081!) |
| **dashboard** | 8501 | `http://localhost:8501` | Streamlit unchanged |

### Docker Startup

```bash
cd deployment
docker compose up
# Waits for postgres health check
# API on http://localhost:8000
# UI on http://localhost:8501
```

**⚠️ Port Mismatch Alert:**
- **Local dev:** API on 8081 (from run.py)
- **Docker:** API on 8000 (from docker-compose.yml)

This difference is intentional:
- Local dev uses 8081 to avoid conflicts during development
- Docker uses 8000 (standard convention)

---

## ☁️ Azure/Production Deployment

### Azure Container Instances (ACI)
```bash
az container create \
  --resource-group mygroup \
  --name insureai-api \
  --image myregistry.azurecr.io/insureai-api:latest \
  --ports 8000  # Single public port for API
```

**Exposed Ports:**
| Service | Port | Protocol |
|---------|------|----------|
| FastAPI | 8000 | HTTP |
| Streamlit | 8501 | HTTP (if exposed) |
| PostgreSQL | None | Internal only (managed service) |

### Azure App Service
```bash
az webapp config appsettings set \
  --name insureai-api \
  --resource-group mygroup \
  --settings WEBSITES_PORT=8000
```

### Kubernetes (AKS)
```yaml
apiVersion: v1
kind: Service
metadata:
  name: insureai-api
spec:
  type: LoadBalancer
  ports:
  - port: 80           # External HTTP
    targetPort: 8000   # Internal API port
    protocol: TCP
  selector:
    app: insureai-api
```

**Port Mapping:**
- External: `http://api.yourcompany.com` (Port 80/443)
- Internal: Pod listens on 8000

---

## 🔌 Optional Services (Not Currently Active)

### Redis (for distributed rate limiting)
**Status:** ⏸️ Deferred to Phase 3

If enabled:
```
Port: 6379
Protocol: TCP
URL: redis://localhost:6379/0

Current: In-memory rate limiter
Future: Would use Redis for multi-instance deployments
```

**Enable in Phase 3:**
```bash
docker run -d -p 6379:6379 redis:latest
# Then update rate_limiter.py to use redis.Redis()
```

### Azure Services (Production Only)
**Not mapped to local ports; accessed via managed APIs:**

- **Azure Cognitive Services** (OCR)
  - Endpoint: `https://<region>.cognitiveservices.azure.com/`
  - No local port needed

- **Azure Monitor** (Observability)
  - Accessed via Application Insights SDK
  - No local port needed

- **Key Vault** (Secrets)
  - Accessed via Azure SDK
  - No local port needed

---

## 📊 Port Availability Checklist

### Before Starting Services

```bash
# Check if ports are free
function check_port {
    if netstat -ano 2>/dev/null | findstr ":$1" > /dev/null 2>&1; then
        echo "❌ Port $1 is IN USE"
        return 1
    else
        echo "✅ Port $1 is FREE"
        return 0
    fi
}

check_port 5432   # PostgreSQL
check_port 8081   # FastAPI
check_port 8501   # Streamlit
```

### If Port Is Already In Use

```bash
# Find and kill process on port (e.g., 8081)
$pid = (netstat -ano | findstr ":8081" | % {$_.split()[-1]})
taskkill /PID $pid /F

# Or change port (not recommended for consistency)
# Edit backend/run.py line 16: port=8082
```

---

## 🔐 Port Security Considerations

### Development (Local Machine)
- All ports listen on `0.0.0.0` (all interfaces)
- ✅ **Safe:** Protected by local firewall
- ✅ **Fast:** No HTTPS overhead
- ❌ **Not for production**

### Production (Azure/Kubernetes)
- API behind Load Balancer (manages TLS)
- Database behind managed service (not exposed)
- ✅ **Secure:** Private network only
- ✅ **Scalable:** Load balanced across instances
- ✅ **Encrypted:** TLS 1.3 enforced

---

## 📈 Port Configuration in Code

### FastAPI Backend

**Local dev (backend/run.py):**
```python
config = uvicorn.Config(
    "main:app",
    host="0.0.0.0",      # All interfaces
    port=8081,           # Local dev port
    reload=False,        # No auto-reload in production
)
```

**Docker (deployment/docker-compose.yml):**
```yaml
api:
  ports:
    - "8000:8000"        # Host:Container port mapping
  command: uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Streamlit Frontend

**Default (frontend/underwriter_portal.py):**
```python
# No explicit port config in code
# Uses streamlit default: 8501
```

**Override via CLI:**
```bash
streamlit run frontend/underwriter_portal.py --server.port 9000
```

**Override via .streamlit/config.toml:**
```toml
[server]
port = 9000
```

### PostgreSQL Database

**.env file:**
```
DATABASE_URL=postgresql+asyncpg://dbinsureai:125QueenStreet@localhost:5432/aus_underwriting
```

---

## 🚦 Networking Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      LOCAL DEVELOPMENT                       │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  User Browser                                                │
│    │                                                          │
│    ├─→ http://localhost:8501 → Streamlit (Port 8501)        │
│    │     └─→ API calls to Port 8081                          │
│    │                                                          │
│    └─→ http://localhost:8081 → FastAPI (Port 8081)          │
│          └─→ Database queries to Port 5432                   │
│                                                               │
│  Services Running:                                           │
│    • PostgreSQL:5432 (Docker container)                      │
│    • FastAPI:8081 (Python process)                           │
│    • Streamlit:8501 (Python process)                         │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│               DOCKER COMPOSE DEPLOYMENT                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  User Browser                                                │
│    │                                                          │
│    ├─→ http://localhost:8000 → API Container (Port 8000)    │
│    │                                                          │
│    └─→ http://localhost:8501 → Dashboard Container (8501)   │
│                                                               │
│  Docker Network (internal):                                  │
│    • postgres:5432 (service name, internal only)            │
│    • api:8000 (exposed to host as :8000)                    │
│    • dashboard:8501 (exposed to host as :8501)              │
│                                                               │
└─────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│            AZURE KUBERNETES (AKS) PRODUCTION                 │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  Users (Internet)                                             │
│    │                                                           │
│    └─→ LoadBalancer (Port 80/443)                            │
│         ├─→ Pod 1: API (Port 8000 internal)                  │
│         ├─→ Pod 2: API (Port 8000 internal)                  │
│         └─→ Pod 3: API (Port 8000 internal)                  │
│              │                                                │
│              └─→ CloudSQL PostgreSQL (managed, not exposed)  │
│                                                                │
│  Streamlit: Deployed separately (optional)                    │
│    └─→ Pod: Dashboard (Port 8501 internal)                   │
│         └─→ Same CloudSQL connection                         │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔧 Troubleshooting Port Issues

### Issue: "Address already in use"
```
Error: [Errno 10048] error while attempting to bind on address ('0.0.0.0', 8081)
```

**Solution:**
```bash
# Find what's using the port
netstat -ano | findstr ":8081"

# Kill it (if it's an old process)
taskkill /PID <PID> /F

# Or use a different port
# Edit backend/run.py and change port=8081 to port=8082
```

### Issue: "Cannot connect to database"
```
psycopg2.OperationalError: could not connect to server
```

**Solution:**
```bash
# Check PostgreSQL is running
docker ps | findstr postgres

# Check it's listening on 5432
netstat -ano | findstr ":5432"

# Verify connection string in .env
echo $env:DATABASE_URL
# Should be: postgresql+asyncpg://dbinsureai:125QueenStreet@localhost:5432/aus_underwriting

# Start PostgreSQL if not running
docker compose -f deployment/docker-compose.yml up postgres -d
```

### Issue: "Connection refused" from FastAPI
```
Failed to connect to http://localhost:8081/health
```

**Solution:**
```bash
# Check FastAPI is running
netstat -ano | findstr ":8081"

# Start it
cd backend && uv run python run.py

# Check logs for errors
# Should see: "Uvicorn running on http://0.0.0.0:8081"
```

### Issue: Streamlit on wrong port
```
# If you want Streamlit on a different port
streamlit run frontend/underwriter_portal.py --server.port 9000
```

---

## Summary Table

| Scenario | Ports | Status |
|----------|-------|--------|
| **Local Dev** | 5432 (PG), 8081 (API), 8501 (UI) | 3 ports needed |
| **Docker Compose** | 5432 (PG), 8000 (API), 8501 (UI) | 3 ports needed |
| **Azure ACI** | 80/443 (LB), 8000 (API internal) | 2 public, 1 internal |
| **Azure AKS** | 80/443 (LB), 8000 (API internal) | 2 public, 1 internal |
| **Production (future)** | +6379 (Redis optional) | +1 port if enabled |

---

**Last Updated:** 2026-05-30  
**Version:** 1.0  
**Maintainer:** Raj Kumar
