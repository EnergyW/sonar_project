import { useEffect, useState } from "react";
import { stores as storesApi, reviews as reviewsApi } from "../services/api";
import ReviewCard from "../components/ReviewCard";

export default function ReviewsPage() {
  const [storeList, setStoreList] = useState([]);
  const [selectedStore, setSelectedStore] = useState(null);
  const [reviewList, setReviewList] = useState([]);
  const [answered, setAnswered] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    storesApi.list().then((s) => {
      setStoreList(s);
      if (s.length > 0) setSelectedStore(s[0].store_id);
    });
  }, []);

  useEffect(() => {
    if (!selectedStore) return;
    setLoading(true);
    reviewsApi
      .list(selectedStore, answered, 50)
      .then(setReviewList)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selectedStore, answered]);

  function handleReplied(reviewId) {
    setReviewList((prev) => prev.filter((r) => r.id !== reviewId));
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Отзывы</h1>
        <div className="header-controls">
          <select
            value={selectedStore ?? ""}
            onChange={(e) => setSelectedStore(Number(e.target.value))}
            className="store-select"
          >
            {storeList.map((s) => (
              <option key={s.store_id} value={s.store_id}>
                {s.store_name} ({s.type})
              </option>
            ))}
          </select>

          <div className="toggle-tabs">
            <button
              className={`toggle-tab ${!answered ? "active" : ""}`}
              onClick={() => setAnswered(false)}
            >
              Без ответа
            </button>
            <button
              className={`toggle-tab ${answered ? "active" : ""}`}
              onClick={() => setAnswered(true)}
            >
              Отвеченные
            </button>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="loading">Загружаем отзывы...</div>
      ) : reviewList.length === 0 ? (
        <div className="empty-state">
          {answered ? "Нет отвеченных отзывов" : "Нет непрочитанных отзывов 🎉"}
        </div>
      ) : (
        <div className="reviews-list">
          {reviewList.map((r) => (
            <ReviewCard
              key={r.id}
              review={r}
              storeId={selectedStore}
              onReplied={() => handleReplied(r.id)}
              showReply={!answered}
            />
          ))}
        </div>
      )}
    </div>
  );
}
