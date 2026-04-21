import { useEffect, useState, useContext } from "react";
import { stores as storesApi, reviews as reviewsApi } from "../services/api";
import ReviewDetail from "../components/ReviewDetail";

// Форматирует дату
function fmtDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// Звёзды
function Stars({ rating }) {
  return (
    <span className="stars-inline">
      {"★".repeat(rating)}<span className="stars-empty">{"☆".repeat(5 - rating)}</span>
    </span>
  );
}

export default function ReviewsPage() {
  const [storeList, setStoreList] = useState([]);
  const [selectedStore, setSelectedStore] = useState(null);
  const [selectedStoreType, setSelectedStoreType] = useState("Ozon");
  const [reviewList, setReviewList] = useState([]);
  const [answered, setAnswered] = useState(false);
  const [loading, setLoading] = useState(false);
  const [ratingFilter, setRatingFilter] = useState(0);   // 0 = все
  const [detailReview, setDetailReview] = useState(null);

  // Загружаем магазины один раз
  useEffect(() => {
    storesApi.list().then((s) => {
      setStoreList(s);
      if (s.length > 0) {
        setSelectedStore(s[0].store_id);
        setSelectedStoreType(s[0].type);
      }
    });
  }, []);

  // Загружаем отзывы только при смене магазина / вкладки
  useEffect(() => {
    if (!selectedStore) return;
    setLoading(true);
    setDetailReview(null);
    reviewsApi
      .list(selectedStore, answered, 100)
      .then(setReviewList)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [selectedStore, answered]);

  function handleStoreChange(e) {
    const id = Number(e.target.value);
    setSelectedStore(id);
    const s = storeList.find((x) => x.store_id === id);
    setSelectedStoreType(s?.type ?? "Ozon");
  }

  function handleReplied(reviewId) {
    setReviewList((prev) => prev.filter((r) => r.id !== reviewId));
  }

  // Фильтр по рейтингу на клиенте — без лишних запросов
  const filtered = ratingFilter ? reviewList.filter((r) => r.rating === ratingFilter) : reviewList;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Отзывы</h1>
        <div className="header-controls">
          <select value={selectedStore ?? ""} onChange={handleStoreChange} className="store-select">
            {storeList.map((s) => (
              <option key={s.store_id} value={s.store_id}>
                {s.store_name} ({s.type})
              </option>
            ))}
          </select>

          <div className="toggle-tabs">
            <button className={`toggle-tab ${!answered ? "active" : ""}`} onClick={() => setAnswered(false)}>
              Без ответа {!answered && reviewList.length > 0 && <span className="tab-count">{reviewList.length}</span>}
            </button>
            <button className={`toggle-tab ${answered ? "active" : ""}`} onClick={() => setAnswered(true)}>
              Отвеченные
            </button>
          </div>
        </div>
      </div>

      {/* Фильтр по звёздам — клиентский, без API */}
      <div className="rating-filter">
        {[0, 1, 2, 3, 4, 5].map((r) => (
          <button
            key={r}
            className={`rating-filter-btn ${ratingFilter === r ? "active" : ""}`}
            onClick={() => setRatingFilter(r)}
          >
            {r === 0 ? "Все" : "★".repeat(r)}
            {r > 0 && (
              <span className="rating-filter-count">
                {reviewList.filter((x) => x.rating === r).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="loading">Загружаем отзывы...</div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          {answered ? "Нет отвеченных отзывов" : "Нет непрочитанных отзывов 🎉"}
        </div>
      ) : (
        <div className="reviews-table">
          <div className="reviews-table-header">
            <span>Рейтинг</span>
            <span>Товар</span>
            <span>Отзыв</span>
            <span>Дата</span>
            <span></span>
          </div>
          {filtered.map((r) => (
            <div key={r.id} className="reviews-table-row" onClick={() => setDetailReview(r)}>
              <span><Stars rating={r.rating} /></span>
              <span className="cell-product">{r.product_name || "—"}</span>
              <span className="cell-text">{r.text ? r.text.slice(0, 80) + (r.text.length > 80 ? "…" : "") : <em>без текста</em>}</span>
              <span className="cell-date">{fmtDate(r.created_at)}</span>
              <span>
                {!answered && !r.answer && (
                  <span className="badge-need-reply">Нужен ответ</span>
                )}
                {r.answer && <span className="badge-answered">✓</span>}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Детальный просмотр — модалка */}
      {detailReview && (
        <ReviewDetail
          review={detailReview}
          allReviews={filtered}
          storeId={selectedStore}
          storeType={selectedStoreType}
          onClose={() => setDetailReview(null)}
          onReplied={handleReplied}
        />
      )}
    </div>
  );
}