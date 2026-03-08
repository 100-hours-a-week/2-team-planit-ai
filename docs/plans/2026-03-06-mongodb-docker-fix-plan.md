# MongoDB Docker Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix MongoDB Docker containers failing to start due to authorization/keyFile mismatch by removing auth for development.

**Architecture:** Remove `MONGODB_INITDB_ROOT_USERNAME/PASSWORD` env vars that trigger authorization (which requires keyFile with replica sets). Remove all auth references from mongot config and init scripts. Add healthcheck for proper startup ordering.

**Tech Stack:** Docker Compose, MongoDB Community Server, MongoDB Community Search (mongot)

---

### Task 1: Remove auth from docker-compose.mongodb.yml

**Files:**
- Modify: `docker-compose.mongodb.yml`

**Step 1: Remove environment section from mongod service**

Remove lines 16-18 (`environment` block with `MONGODB_INITDB_ROOT_USERNAME` and `MONGODB_INITDB_ROOT_PASSWORD`).

```yaml
# DELETE these lines from mongod service:
    environment:
      - MONGODB_INITDB_ROOT_USERNAME=admin
      - MONGODB_INITDB_ROOT_PASSWORD=adminpass
```

**Step 2: Add healthcheck to mongod service**

Add after `extra_hosts` block (after line 20), before `volumes`:

```yaml
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
```

**Step 3: Remove passwordFile volume mount from mongot service**

Remove line 42 (`./docker/mongodb/passwordFile:/mongot-community/pwfile:ro`).

```yaml
# DELETE this line from mongot volumes:
      - ./docker/mongodb/passwordFile:/mongot-community/pwfile:ro
```

**Step 4: Change mongot depends_on to use healthcheck condition**

Replace lines 45-46:

```yaml
# BEFORE:
    depends_on:
      - mongod

# AFTER:
    depends_on:
      mongod:
        condition: service_healthy
```

**Step 5: Update header comment with new connection string**

Replace line 6:

```yaml
# BEFORE:
# 접속: mongosh "mongodb://admin:adminpass@localhost:27017/?authSource=admin&directConnection=true"

# AFTER:
# 접속: mongosh "mongodb://localhost:27017/?directConnection=true"
```

**Step 6: Commit**

```bash
git add docker-compose.mongodb.yml
git commit -m "fix: remove auth from mongod, add healthcheck for mongot ordering"
```

---

### Task 2: Remove auth credentials from mongot.conf

**Files:**
- Modify: `docker/mongodb/mongot.conf`

**Step 1: Remove username and passwordFile from syncSource**

Replace the entire file content:

```yaml
syncSource:
  replicaSet:
    hostAndPort: "mongod:27017"
storage:
  dataPath: "/data/mongot"
server:
  grpc:
    address: "0.0.0.0:27028"
    tls:
      mode: "disabled"
metrics:
  enabled: true
  address: "0.0.0.0:9946"
healthCheck:
  address: "0.0.0.0:8080"
logging:
  verbosity: INFO
```

Lines removed: `username: mongotUser` and `passwordFile: "/mongot-community/pwfile"` from `syncSource.replicaSet`.

**Step 2: Commit**

```bash
git add docker/mongodb/mongot.conf
git commit -m "fix: remove auth credentials from mongot config"
```

---

### Task 3: Simplify init-mongo.sh

**Files:**
- Modify: `docker/mongodb/init-mongo.sh`

**Step 1: Replace init-mongo.sh with resilient version**

Replace the entire file:

```bash
#!/bin/bash
# MongoDB replica set 초기화
# docker-entrypoint-initdb.d에 마운트되어 bootstrap 단계에서 자동 호출됩니다.

echo "=== MongoDB Replica Set 초기화 ==="
mongosh --eval '
  try {
    rs.initiate({
      _id: "rs0",
      members: [{ _id: 0, host: "mongod.search-community:27017" }]
    });
    print("Replica set initiated successfully");
  } catch(e) {
    print("Replica set already initialized: " + e.message);
  }
'

echo "=== Replica Set 안정화 대기 (3초) ==="
sleep 3

echo "=== 초기화 완료 ==="
```

Changes:
- Removed `set -e` (allow graceful error handling)
- Wrapped `rs.initiate()` in try/catch (handles `--replSetMember` conflict)
- Removed `mongotUser` creation (unnecessary without auth)

**Step 2: Commit**

```bash
git add docker/mongodb/init-mongo.sh
git commit -m "fix: make init-mongo.sh resilient, remove auth user creation"
```

---

### Task 4: Simplify init-replica-set.sh

**Files:**
- Modify: `docker/mongodb/init-replica-set.sh`

**Step 1: Replace init-replica-set.sh with no-auth version**

Replace the entire file:

```bash
#!/bin/bash
# MongoDB replica set 초기화 (호스트에서 실행)
# 사용법: 컨테이너 시작 후 최초 1회 실행
#   ./docker/mongodb/init-replica-set.sh

echo "=== MongoDB Replica Set 초기화 ==="
docker exec planit-mongod mongosh --eval '
  try {
    rs.initiate({
      _id: "rs0",
      members: [{ _id: 0, host: "mongod.search-community:27017" }]
    });
    print("Replica set initiated successfully");
  } catch(e) {
    print("Replica set already initialized: " + e.message);
  }
'

echo "=== Replica Set 안정화 대기 (5초) ==="
sleep 5

echo "=== Replica Set 상태 확인 ==="
docker exec planit-mongod mongosh --eval 'rs.status().ok'

echo "=== 초기화 완료 ==="
echo "MongoDB URI: mongodb://localhost:27017/?directConnection=true"
```

Changes:
- Removed `set -e`
- Wrapped `rs.initiate()` in try/catch
- Removed `mongotUser` creation
- Updated comment

**Step 2: Commit**

```bash
git add docker/mongodb/init-replica-set.sh
git commit -m "fix: simplify init-replica-set.sh, remove auth user creation"
```

---

### Task 5: Clean start and verify

**Step 1: Tear down existing containers and volumes**

```bash
docker compose -f docker-compose.mongodb.yml down -v 2>/dev/null || true
```

**Step 2: Create external network if not exists**

```bash
docker network create search-community 2>/dev/null || true
```

**Step 3: Start containers**

```bash
docker compose -f docker-compose.mongodb.yml up -d
```

Expected: Both containers start without errors.

**Step 4: Check mongod logs**

```bash
docker logs planit-mongod 2>&1 | tail -20
```

Expected: No `BadValue: security.keyFile` error. Should see successful startup and replica set initialization.

**Step 5: Check mongot logs**

```bash
docker logs planit-mongot 2>&1 | tail -20
```

Expected: No `MongoTimeoutException` or `Connection refused`. Should see successful connection to mongod.

**Step 6: Verify mongod is healthy**

```bash
docker exec planit-mongod mongosh --eval "db.adminCommand('ping')"
```

Expected: `{ ok: 1 }`

**Step 7: Verify replica set status**

```bash
docker exec planit-mongod mongosh --eval "rs.status().ok"
```

Expected: `1`

**Step 8: Test connection from host**

```bash
mongosh "mongodb://localhost:27017/?directConnection=true" --eval "db.adminCommand('ping')"
```

Expected: `{ ok: 1 }` (requires mongosh installed on host; skip if not available)

---

### Task 6: Update .env mongodb_uri

**Files:**
- Modify: `.env` (not tracked in git)

**Step 1: Update mongodb_uri**

Ensure `.env` has the no-auth connection string:

```
mongodb_uri=mongodb://localhost:27017/?directConnection=true
```

If it currently has `admin:adminpass@` in the URI, remove the credentials.

**Step 2: No commit needed** (.env is gitignored)
