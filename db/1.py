import requests

API_KEY = "eyJhbGciOiJFUzI1NiIsImtpZCI6IjIwMjUwOTA0djEiLCJ0eXAiOiJKV1QifQ.eyJhY2MiOjEsImVudCI6MSwiZXhwIjoxNzc2OTc3NTk4LCJpZCI6IjAxOWExMDQ1LWMyZGItN2NmMS05NzVkLWYxNmEyNDY2YTg0MSIsImlpZCI6MzYxNjE1NzYsIm9pZCI6MTM0MTYxMywicyI6NjQyLCJzaWQiOiIwYmIxNTMxOC01ODBiLTRkN2UtYTM3ZS1iYjNmOWY1ZmEwZmQiLCJ0IjpmYWxzZSwidWlkIjozNjE2MTU3Nn0.Yd5RcVtfIo4x8k3hL67pnlYdbDfUmkE_A9e6pVG4_DGKS7lm49SAmGEF_-zzOG_cpgarprnKnaCGF_Of0KDalg"
BASE_URL = "https://feedbacks-api.wildberries.ru/api/v1/feedbacks"

HEADERS = {
    "Authorization": API_KEY,
    "Content-Type": "application/json"
}


def get_feedbacks_count(is_answered: bool) -> int:
    """
    Возвращает количество отзывов:
    is_answered=True  -> отвеченные
    is_answered=False -> неотвеченные
    """

    total = 0
    take = 5000
    skip = 0

    while True:
        params = {
            "isAnswered": is_answered,
            "take": take,
            "skip": skip,
            "order": "dateDesc"
        }

        response = requests.get(BASE_URL, headers=HEADERS, params=params)
        response.raise_for_status()

        data = response.json()["data"]["feedbacks"]
        total += len(data)

        if len(data) < take:
            break

        skip += take

    return total


if __name__ == "__main__":
    answered = get_feedbacks_count(True)
    unanswered = get_feedbacks_count(False)

    print(f"Отвеченные отзывы: {answered}")
    print(f"Неотвеченные отзывы: {unanswered}")
