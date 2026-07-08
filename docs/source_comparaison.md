## En francais
# Comparaison des sources de données — Football Data Platform

## Tableau comparatif

| Critère | football-data.org | statbunker | understat |
|---|---|---|---|
| **Type de source** | API REST | HTML statique | HTML dynamique (JS) |
| **Outil** | requests | requests + BeautifulSoup | Playwright |
| **Difficulté de collecte** | Faible | Moyenne | Élevée |
| **Qualité des données** | Élevée (JSON structuré) | Moyenne (principalement PL) | Élevée (xG, xGA, xPTS) |
| **Fréquence de mise à jour** | Temps réel | Lente (calendrier non clair) | Quotidienne |
| **Risque lié aux CGU/ToS** | Faible (API officielle) | Faible (pas de CGU claire) | Moyen (scraping) |
| **Limite de taux** | 10 req/min | Non claire | Non claire |
| **Données spécifiques** | Calendrier, résultats | Classement de Premier League | xG, xGA, xPTS |
| **Compétitions supportées** | PL, L1 et plusieurs autres compétitions | Principalement PL (données L1 incomplètes) | PL, L1, La Liga, Bundesliga, Serie A |

## Remarques détaillées

### football-data.org

- **Avantages :** API officielle, données clairement structurées au format JSON, pas besoin de parser du HTML, stable à long terme.
- **Inconvénients :** Le palier gratuit est limité à 10 requêtes/minute et ne fournit pas de données avancées comme xG ou xGA.
- **Conclusion :** Source principale pour le calendrier des matchs et les résultats.

### statbunker.com

- **Avantages :** Pas de blocage Cloudflare, HTML statique facile à parser avec BeautifulSoup.
- **Inconvénients :** Le `comp_id` change selon la saison et doit être trouvé manuellement ; les données de Ligue 1 ne sont pas complètes ; pas de données avancées.
- **Conclusion :** Source complémentaire pour le classement de Premier League.

### understat.com

- **Avantages :** Données xG de bonne qualité, non disponibles dans les autres sources avec un palier gratuit.
- **Inconvénients :** Nécessite Playwright, plus lent que requests ; le JavaScript doit être entièrement exécuté avant de pouvoir récupérer les données.
- **Conclusion :** Source principale pour les données xG, importante pour les analyses avancées.

## Enseignements techniques

| Situation | Solution |
|---|---|
| API officielle disponible | Utiliser `requests` + clé API |
| HTML statique, sans blocage | Utiliser `requests` + `BeautifulSoup` |
| HTML dynamique (JavaScript) | Utiliser `Playwright` |
| Blocage par Cloudflare (FBref, worldfootball.net) | Changer de source ou utiliser Playwright |
| Réponse serveur 429 (Too Many Requests) | Augmenter `min_delay` dans le `RateLimiter` |



## Tiếng Việt
# So sánh nguồn dữ liệu — Football Data Platform

## Bảng so sánh

| Tiêu chí | football-data.org | statbunker | understat |
|---|---|---|---|
| **Loại nguồn** | REST API | HTML tĩnh | HTML động (JS) |
| **Công cụ** | requests | requests + BeautifulSoup | Playwright |
| **Độ khó thu thập** | Thấp | Trung bình | Cao |
| **Chất lượng dữ liệu** | Cao (structured JSON) | Trung bình (chỉ có PL) | Cao (có xG, xGA, xPTS) |
| **Tần suất cập nhật** | Real-time | Chậm (không rõ schedule) | Hàng ngày |
| **Rủi ro ToS** | Thấp (API chính thức) | Thấp (không có ToS rõ ràng) | Trung bình (scraping) |
| **Rate limit** | 10 req/phút | Không rõ | Không rõ |
| **Dữ liệu đặc biệt** | Lịch thi đấu, kết quả | Bảng xếp hạng PL | xG, xGA, xPTS |
| **Giải đấu hỗ trợ** | PL, L1, và nhiều giải khác | Chủ yếu PL (L1 thiếu dữ liệu) | PL, L1, La Liga, Bundesliga, Serie A |

## Nhận xét chi tiết

### football-data.org
- **Ưu điểm:** API chính thức, dữ liệu có cấu trúc rõ ràng (JSON), không cần parse HTML, ổn định lâu dài.
- **Nhược điểm:** Free tier giới hạn 10 req/phút và không có dữ liệu nâng cao (xG, xGA).
- **Kết luận:** Nguồn chính cho lịch thi đấu và kết quả.

### statbunker.com
- **Ưu điểm:** Không bị Cloudflare chặn, HTML tĩnh dễ parse với BeautifulSoup.
- **Nhược điểm:** `comp_id` thay đổi theo mùa giải (phải tìm thủ công), dữ liệu Ligue 1 không đầy đủ, không có dữ liệu nâng cao.
- **Kết luận:** Nguồn bổ sung cho bảng xếp hạng Premier League.

### understat.com
- **Ưu điểm:** Dữ liệu xG chất lượng cao — không có ở các nguồn khác trên free tier.
- **Nhược điểm:** Cần Playwright (chậm hơn requests), JavaScript phải chạy xong mới có dữ liệu.
- **Kết luận:** Nguồn duy nhất cho dữ liệu xG — quan trọng cho phân tích nâng cao.

## Bài học kỹ thuật

| Tình huống | Giải pháp |
|---|---|
| API chính thức có sẵn | Dùng `requests` + API key |
| HTML tĩnh, không bị chặn | Dùng `requests` + `BeautifulSoup` |
| HTML động (JavaScript) | Dùng `Playwright` |
| Bị Cloudflare chặn (FBref, worldfootball.net) | Đổi nguồn hoặc dùng Playwright |
| Server trả về 429 (Too Many Requests) | Tăng `min_delay` trong `RateLimiter` |

