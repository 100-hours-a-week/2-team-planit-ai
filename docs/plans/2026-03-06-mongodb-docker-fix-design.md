# MongoDB Docker Fix Design

## Problem

MongoDB Docker containers fail to start. Root cause:
- `MONGODB_INITDB_ROOT_USERNAME/PASSWORD` env vars enable `authorization` automatically
- MongoDB requires `security.keyFile` when authorization is enabled with replica sets
- `mongod.conf` lacks `security.keyFile` configuration
- mongod crashes -> mongot connection refused (cascading failure)

## Error Messages

**mongod:**
```
BadValue: security.keyFile is required when authorization is enabled with replica sets
```

**mongot:**
```
MongoTimeoutException: Connection refused to mongod:27017
```

## Solution: Remove Authentication (Development)

Remove auth for development simplicity. Auth can be re-enabled for staging/production later using Approach 1 (keyFile + authorization).

### Changes

#### 1. `docker-compose.mongodb.yml`

- Remove `MONGODB_INITDB_ROOT_USERNAME/PASSWORD` environment variables
- Add `healthcheck` to mongod service
- Change mongot `depends_on` to `condition: service_healthy`
- Remove `passwordFile` volume mount from mongot

#### 2. `docker/mongodb/mongot.conf`

- Remove `username` and `passwordFile` from `syncSource.replicaSet`

#### 3. `docker/mongodb/init-mongo.sh`

- Wrap `rs.initiate()` in try/catch (may conflict with `--replSetMember` flag)
- Remove `mongotUser` creation (unnecessary without auth)

#### 4. `.env`

- Update `mongodb_uri` to remove auth credentials:
  `mongodb://localhost:27017/?directConnection=true`

### Clean Start Procedure

```bash
docker compose -f docker-compose.mongodb.yml down -v
docker network create search-community 2>/dev/null || true
docker compose -f docker-compose.mongodb.yml up -d
```

### Future: Re-enabling Auth (Staging/Production)

When auth is needed:
1. Add `security.keyFile` and `security.authorization: enabled` to `mongod.conf`
2. Mount keyfile in docker-compose with correct permissions (chmod 400, uid 999)
3. Restore `MONGODB_INITDB_ROOT_USERNAME/PASSWORD` env vars
4. Restore mongot auth credentials in `mongot.conf`
5. Restore `mongotUser` creation in `init-mongo.sh`
