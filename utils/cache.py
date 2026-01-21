import asyncio
import logging
import time
from typing import Dict, Any, Set, List
from db.database import AsyncDatabase
from utils.api_utils import get_store_reviews, get_store_questions

logger = logging.getLogger(__name__)

class StoreCache:
    def __init__(self):
        self.cache: Dict[int, Dict[str, Any]] = {}
        self.last_updated: Dict[int, float] = {}
        self.pending_updates: Set[int] = set()
        self.update_interval = 60
        self._lock = asyncio.Lock()
        self._update_semaphore = asyncio.Semaphore(5)
        self._background_semaphore = asyncio.Semaphore(3)

    async def get_unanswered_counts(self, store_id: int) -> Dict[str, int]:
        current_time = time.time()

        async with self._lock:
            cache_entry = self.cache.get(store_id)
            last_update = self.last_updated.get(store_id, 0)

            needs_immediate_update = (
                    cache_entry is None or
                    current_time - last_update > 300
            )

            needs_background_update = (
                    not needs_immediate_update and
                    current_time - last_update > self.update_interval and
                    store_id not in self.pending_updates
            )

        if needs_immediate_update:
            logging.info(f"🔄 Immediate cache update for store {store_id}")
            await self._update_store_data(store_id)
        elif needs_background_update:
            async with self._lock:
                self.pending_updates.add(store_id)
            asyncio.create_task(self._update_pending_store(store_id))

        async with self._lock:
            return self.cache.get(store_id, {"reviews": 0, "questions": 0}).copy()

    async def _update_pending_store(self, store_id: int):
        try:
            await self._update_store_data(store_id)
        except Exception as e:
            logging.error(f"❌ Error in background update for store {store_id}: {e}")
        finally:
            async with self._lock:
                self.pending_updates.discard(store_id)

    async def _update_store_data(self, store_id: int):
        async with self._update_semaphore:
            try:
                async with AsyncDatabase() as db:
                    store = await db.get_store_details(store_id)
                    if not store:
                        logging.warning(f"Store {store_id} not found in database")
                        return

                reviews_task = get_store_reviews(store, answered=False, limit=100)
                questions_task = get_store_questions(store_id, answered=False, limit=100)

                unanswered_reviews, unanswered_questions = await asyncio.gather(
                    reviews_task, questions_task, return_exceptions=True
                )

                if isinstance(unanswered_reviews, Exception):
                    logging.error(f"❌ Error fetching reviews for store {store_id}: {unanswered_reviews}")
                    reviews_count = 0
                else:
                    reviews_count = len(unanswered_reviews)

                if isinstance(unanswered_questions, Exception):
                    logging.error(f"❌ Error fetching questions for store {store_id}: {unanswered_questions}")
                    questions_count = 0
                else:
                    questions_data = unanswered_questions.get("questions", [])
                    questions_count = len(questions_data) if isinstance(questions_data, list) else 0

                async with self._lock:
                    self.cache[store_id] = {
                        "reviews": reviews_count,
                        "questions": questions_count,
                        "store_name": store.get("store_name", "Unknown"),
                        "last_full_update": time.time()
                    }
                    self.last_updated[store_id] = time.time()

                logging.info(
                    f"✅ Cache updated for store {store_id}: {reviews_count} reviews, {questions_count} questions")

            except Exception as e:
                logging.error(f"❌ Error updating cache for store {store_id}: {e}")
                async with self._lock:
                    self.cache[store_id] = {"reviews": 0, "questions": 0, "error": True}
                    self.last_updated[store_id] = time.time()

    async def add_store(self, store_id: int):
        logging.info(f"🆕 Adding store {store_id} to cache with immediate update")
        await self._update_store_data(store_id)

    async def update_all_stores(self):
        try:
            async with AsyncDatabase() as db:
                store_ids = await db.get_all_stores()

            if not store_ids:
                logging.info("💤 No stores found for cache update")
                return

            logging.info(f"🔄 Starting background update for {len(store_ids)} stores")

            batch_size = 10
            for i in range(0, len(store_ids), batch_size):
                batch = store_ids[i:i + batch_size]

                async with self._background_semaphore:
                    tasks = [self._update_store_data(store_id) for store_id in batch]
                    await asyncio.gather(*tasks, return_exceptions=True)

                if i + batch_size < len(store_ids):
                    await asyncio.sleep(2)

            logging.info("✅ Background store update completed")

        except Exception as e:
            logging.error(f"❌ Error updating all stores cache: {e}")

    async def invalidate_store(self, store_id: int):
        async with self._lock:
            if store_id in self.last_updated:
                self.last_updated[store_id] = 0
                logging.info(f"🔄 Store {store_id} invalidated, will update on next request")

    async def decrement_review_count(self, store_id: int):
        async with self._lock:
            if store_id in self.cache:
                old_count = self.cache[store_id]["reviews"]
                self.cache[store_id]["reviews"] = max(0, self.cache[store_id]["reviews"] - 1)
                logging.info(
                    f"📉 Decremented review count for store {store_id}: {old_count} -> {self.cache[store_id]['reviews']}")

    async def decrement_question_count(self, store_id: int):
        async with self._lock:
            if store_id in self.cache:
                old_count = self.cache[store_id]["questions"]
                self.cache[store_id]["questions"] = max(0, self.cache[store_id]["questions"] - 1)
                logging.info(
                    f"📉 Decremented question count for store {store_id}: {old_count} -> {self.cache[store_id]['questions']}")

    async def get_cache_stats(self) -> Dict[str, Any]:
        async with self._lock:
            total_stores = len(self.cache)
            now = time.time()

            fresh = 0
            recent = 0
            stale = 0

            for store_id in self.cache:
                last_update = self.last_updated.get(store_id, 0)
                age = now - last_update

                if age < 60:
                    fresh += 1
                elif age < 300:
                    recent += 1
                else:
                    stale += 1

            return {
                "total_stores": total_stores,
                "fresh": fresh,
                "recent": recent,
                "stale": stale,
                "pending_updates": len(self.pending_updates)
            }

store_cache = StoreCache()

async def start_background_updater():
    logging.info("🚀 Starting initial cache population...")
    await store_cache.update_all_stores()
    logging.info("✅ Initial cache population completed")

    while True:
        try:
            await asyncio.sleep(120)

            stats = await store_cache.get_cache_stats()
            logging.info(f"📊 Cache stats: {stats['total_stores']} stores, "
                         f"{stats['fresh']} fresh, {stats['recent']} recent, "
                         f"{stats['stale']} stale, {stats['pending_updates']} pending")

            if stats['stale'] > 10 or stats['total_stores'] == 0:
                await store_cache.update_all_stores()
            else:
                logging.info("💤 Skipping background update - data is fresh enough")

        except Exception as e:
            logging.error(f"❌ Background updater error: {e}")
            await asyncio.sleep(60)