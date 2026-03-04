"""
MongoHistoryStore: MongoDB 기반 대화 히스토리 저장소

대화 세션별 메시지를 MongoDB에 저장하고 조회합니다.
settings.mongodb_uri 및 settings.mongodb_db_name을 사용합니다.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

logger = logging.getLogger(__name__)

# 기본 컬렉션 이름
DEFAULT_COLLECTION = "chat_history"


class MongoHistoryStore:
    """MongoDB 대화 히스토리 저장소

    세션 단위로 대화 메시지를 저장하고 조회합니다.
    motor(async MongoDB 드라이버)를 사용합니다.

    Document 구조:
    {
        "session_id": str,
        "messages": [
            {"role": "user", "content": "...", "timestamp": datetime},
            {"role": "assistant", "content": "...", "timestamp": datetime},
        ],
        "metadata": {
            "created_at": datetime,
            "updated_at": datetime,
            "message_count": int,
        }
    }
    """

    def __init__(
        self,
        mongodb_uri: Optional[str] = None,
        db_name: Optional[str] = None,
        collection_name: str = DEFAULT_COLLECTION,
    ):
        """
        Args:
            mongodb_uri: MongoDB 접속 URI (None이면 settings에서 가져옴)
            db_name: 데이터베이스 이름 (None이면 settings에서 가져옴)
            collection_name: 컬렉션 이름
        """
        self._uri = mongodb_uri or settings.mongodb_uri
        self._db_name = db_name or settings.mongodb_db_name
        self._collection_name = collection_name
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None

    async def _ensure_connection(self) -> AsyncIOMotorDatabase:
        """MongoDB 연결 보장 (지연 연결)

        Returns:
            AsyncIOMotorDatabase: MongoDB 데이터베이스 인스턴스
        """
        if self._db is None:
            self._client = AsyncIOMotorClient(self._uri)
            self._db = self._client[self._db_name]
            logger.info(
                f"MongoDB 연결 완료: db={self._db_name}, "
                f"collection={self._collection_name}"
            )
        return self._db

    def _get_collection(self, db: AsyncIOMotorDatabase):
        """컬렉션 객체 반환"""
        return db[self._collection_name]

    async def create_session(self, session_id: str) -> None:
        """새 대화 세션 생성

        Args:
            session_id: 세션 ID
        """
        db = await self._ensure_connection()
        collection = self._get_collection(db)

        now = datetime.now(timezone.utc)
        document = {
            "session_id": session_id,
            "messages": [],
            "metadata": {
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
            },
        }

        await collection.insert_one(document)
        logger.info(f"세션 생성: session_id={session_id}")

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        """세션에 메시지 추가

        Args:
            session_id: 세션 ID
            role: 메시지 역할 ("user", "assistant", "system")
            content: 메시지 내용
        """
        db = await self._ensure_connection()
        collection = self._get_collection(db)

        now = datetime.now(timezone.utc)
        message = {
            "role": role,
            "content": content,
            "timestamp": now,
        }

        result = await collection.update_one(
            {"session_id": session_id},
            {
                "$push": {"messages": message},
                "$set": {"metadata.updated_at": now},
                "$inc": {"metadata.message_count": 1},
            },
        )

        if result.matched_count == 0:
            # 세션이 없으면 자동 생성
            await self.create_session(session_id)
            await collection.update_one(
                {"session_id": session_id},
                {
                    "$push": {"messages": message},
                    "$set": {"metadata.updated_at": now},
                    "$inc": {"metadata.message_count": 1},
                },
            )
            logger.info(f"세션 자동 생성 후 메시지 추가: session_id={session_id}")
        else:
            logger.debug(f"메시지 추가: session_id={session_id}, role={role}")

    async def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """세션의 메시지 히스토리 조회

        Args:
            session_id: 세션 ID
            limit: 최근 N개 메시지만 조회 (None이면 전체)

        Returns:
            List[Dict[str, str]]: 메시지 리스트 [{"role": ..., "content": ...}]
        """
        db = await self._ensure_connection()
        collection = self._get_collection(db)

        doc = await collection.find_one({"session_id": session_id})
        if doc is None:
            return []

        messages = doc.get("messages", [])

        # timestamp 필드 제거하여 반환
        clean_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
        ]

        if limit is not None:
            return clean_messages[-limit:]
        return clean_messages

    async def get_session_metadata(
        self, session_id: str
    ) -> Optional[Dict]:
        """세션 메타데이터 조회

        Args:
            session_id: 세션 ID

        Returns:
            Optional[Dict]: 메타데이터 또는 None
        """
        db = await self._ensure_connection()
        collection = self._get_collection(db)

        doc = await collection.find_one(
            {"session_id": session_id},
            {"metadata": 1, "_id": 0},
        )
        if doc is None:
            return None
        return doc.get("metadata")

    async def list_sessions(
        self, limit: int = 20
    ) -> List[Dict]:
        """최근 세션 목록 조회

        Args:
            limit: 최대 개수

        Returns:
            List[Dict]: 세션 요약 리스트
        """
        db = await self._ensure_connection()
        collection = self._get_collection(db)

        cursor = collection.find(
            {},
            {
                "session_id": 1,
                "metadata": 1,
                "_id": 0,
            },
        ).sort("metadata.updated_at", -1).limit(limit)

        return await cursor.to_list(length=limit)

    async def delete_session(self, session_id: str) -> bool:
        """세션 삭제

        Args:
            session_id: 세션 ID

        Returns:
            bool: 삭제 성공 여부
        """
        db = await self._ensure_connection()
        collection = self._get_collection(db)

        result = await collection.delete_one({"session_id": session_id})
        deleted = result.deleted_count > 0

        if deleted:
            logger.info(f"세션 삭제: session_id={session_id}")
        else:
            logger.warning(f"삭제할 세션 없음: session_id={session_id}")

        return deleted

    async def close(self) -> None:
        """MongoDB 연결 종료"""
        if self._client is not None:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB 연결 종료")
