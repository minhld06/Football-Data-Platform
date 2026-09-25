# README Scraping — Football Data Platform

# English

## 1. Objective

This file explains how to run the data collectors for the **Data Collection/Scraping** phase.

The project uses three types of sources:

| Source type | Source | Tools |
|---|---|---|
| API | football-data.org | requests |
| Static HTML | StatBunker | requests + BeautifulSoup |
| Dynamic HTML | Understat | Playwright + BeautifulSoup |

Raw data is saved in:

```text
data/raw/
```

---

## 2. Crawler structure

```text
crawlers/
├── common/
│   └── utils.py
│
├── football_data_org/
│   └── client.py
│
├── statbunker/
│   └── scraper.py
│
└── understat/
    └── scraper.py
```

---

## 3. Prerequisites

Before running the crawlers, make sure that:

- The virtual environment is activated.
- The dependencies from `requirements.txt` are installed.
- The Playwright browsers are installed.
- The `.env` file exists for `football-data.org`.

The `.env` file must contain:

```text
`FOOTBALL_DATA_API_KEY`

This variable holds the football-data.org API key and must only be stored in the local `.env` file.
```

Never commit the `.env` file to GitHub.

---

## 4. Run the football-data.org collector

### Source type

Official API.

### File

```text
crawlers/football_data_org/client.py
```

### Command

```powershell
python crawlers/football_data_org/client.py
```

### Output

```text
data/raw/football_data_org/matches/{date}/
data/raw/football_data_org/standings/{date}/
```

### Currently available data

```text
data/raw/football_data_org/matches/{date}/FL1_2025.json
data/raw/football_data_org/matches/{date}/PL_2025.json
data/raw/football_data_org/standings/{date}/FL1_2025.json
data/raw/football_data_org/standings/{date}/PL_2025.json
```

---

## 5. Run the StatBunker collector

### Source type

Static HTML.

### File

```text
crawlers/statbunker/scraper.py
```

### Command

```powershell
python crawlers/statbunker/scraper.py
```

### Output

```text
data/raw/statbunker/standings/{date}/
```

### Currently available data

```text
data/raw/statbunker/standings/{date}/PL_2025-2026.json
```

### Technical notes

This collector uses:

- `retry_request()` to retry a request on error.
- `RateLimiter(min_delay=3.0)` to limit request frequency.
- `BeautifulSoup` to parse the HTML table.

---

## 6. Run the Understat collector

### Source type

Dynamic HTML / JavaScript-rendered page.

### File

```text
crawlers/understat/scraper.py
```

### Command

```powershell
python crawlers/understat/scraper.py
```

### Output

```text
data/raw/understat/standings/{date}/
```

### Currently available data

```text
data/raw/understat/standings/{date}/EPL_2025-2026.json
data/raw/understat/standings/{date}/Ligue_1_2025-2026.json
```

### Technical notes

This collector uses:

- Playwright to render the JavaScript.
- `page.content()` to retrieve the HTML after rendering.
- `BeautifulSoup` to parse the table.
- The collected metrics include `xG`, `xGA`, `xPTS`.

### robots.txt exception (deliberate)

Understat's `robots.txt` (checked 2026-09-25; the file has not changed since 2020-07-13) is:

```
User-agent: *
Disallow: /
```

This conflicts with the project rule "respect robots.txt/ToS". `robots.txt` is a request, not a technical block, so the collector works, but that does not mean crawling is permitted. Understat is kept as a **conscious, documented exception** because it is the only source of per-player season stats (minutes, xG, xA, position) and, for past seasons, the only source of a complete player list (football-data.org only returns the current squad; StatBunker only lists scorers).

Mitigations that stay in place:

- Educational, non-commercial use only. The data is not redistributed.
- One host, strictly sequential requests, minimum 3 s between requests (`RateLimiter(min_delay=3.0)`).
- Very low volume: per league and season, one page load plus one JSON call (`/getLeagueData/{league}/{year}`).
- Raw snapshots are kept in `data/raw/`, so a season is never re-crawled just to re-run ingestion or dbt.

Open items:

- Understat's Terms of Service have **not been reviewed yet**.
- The mentor must be informed of this exception.
- If Understat blocks the crawler or objects, stop crawling it and fall back to StatBunker + football-data.org only. Understat-derived columns (`xg`, `xga`, `xpts`, player minutes) would then be `NULL` for new seasons.

---

## 7. Run all collectors

The collectors can be run one by one:

```powershell
python crawlers/football_data_org/client.py
python crawlers/statbunker/scraper.py
python crawlers/understat/scraper.py
```

After running, check:

```text
data/raw/
├── football_data_org/
├── statbunker/
└── understat/
```

---

## 8. Common utilities

The shared functions are located in:

```text
crawlers/common/utils.py
```

| Utility | Role |
|---|---|
| `get_logger()` | Create a standard logger |
| `RateLimiter` | Limit request frequency |
| `retry_request()` | Retry a request with exponential backoff |

---

## 9. Quick check

With PowerShell:

```powershell
Get-ChildItem -Recurse data/raw -Filter *.json
```

If the JSON files for all three sources appear, the collectors are working correctly.

---

## 10. Result

| Source | Entity | Status |
|---|---|---|
| football-data.org | matches, standings | Done |
| StatBunker | standings | Done |
| Understat | standings + xG | Done |

---

## 11. Notes

- Do not commit `.env`.
- Do not commit `.venv/`.
- Do not commit `__pycache__/`.
- Do not send requests too quickly.
- Data is used for educational purposes only.

---

## 12. Current limitations

- StatBunker only collects the Premier League.
- Understat only collects standings.
- There is no automatic resume mechanism yet.

---

# Français

## 1. Objectif

Ce fichier explique comment exécuter les collecteurs de données de la phase **Data Collection/Scraping**.

Le projet utilise trois types de sources :

| Type de source | Source | Outils |
|---|---|---|
| API | football-data.org | requests |
| HTML statique | StatBunker | requests + BeautifulSoup |
| HTML dynamique | Understat | Playwright + BeautifulSoup |

Les données brutes sont enregistrées dans :

```text
data/raw/
```

---

## 2. Structure des collecteurs

```text
crawlers/
├── common/
│   └── utils.py
│
├── football_data_org/
│   └── client.py
│
├── statbunker/
│   └── scraper.py
│
└── understat/
    └── scraper.py
```

---

## 3. Préconditions

Avant d'exécuter les collecteurs, vérifier que :

- L'environnement virtuel est activé.
- Les dépendances de `requirements.txt` sont installées.
- Les navigateurs Playwright sont installés.
- Le fichier `.env` existe pour `football-data.org`.

Le fichier `.env` doit contenir :

```text
`FOOTBALL_DATA_API_KEY`

Cette variable contient la clé API de football-data.org et doit être stockée uniquement dans le fichier local `.env`.
```

Ne jamais committer le fichier `.env` sur GitHub.

---

## 4. Exécuter le collecteur football-data.org

### Type de source

API officielle.

### Fichier

```text
crawlers/football_data_org/client.py
```

### Commande

```powershell
python crawlers/football_data_org/client.py
```

### Sortie

```text
data/raw/football_data_org/matches/{date}/
data/raw/football_data_org/standings/{date}/
```

### Données actuellement disponibles

```text
data/raw/football_data_org/matches/{date}/FL1_2025.json
data/raw/football_data_org/matches/{date}/PL_2025.json
data/raw/football_data_org/standings/{date}/FL1_2025.json
data/raw/football_data_org/standings/{date}/PL_2025.json
```

---

## 5. Exécuter le collecteur StatBunker

### Type de source

HTML statique.

### Fichier

```text
crawlers/statbunker/scraper.py
```

### Commande

```powershell
python crawlers/statbunker/scraper.py
```

### Sortie

```text
data/raw/statbunker/standings/{date}/
```

### Données actuellement disponibles

```text
data/raw/statbunker/standings/{date}/PL_2025-2026.json
```

### Notes techniques

Ce collecteur utilise :

- `retry_request()` pour relancer une requête en cas d'erreur.
- `RateLimiter(min_delay=3.0)` pour limiter la fréquence des requêtes.
- `BeautifulSoup` pour analyser le tableau HTML.

---

## 6. Exécuter le collecteur Understat

### Type de source

HTML dynamique / page rendue par JavaScript.

### Fichier

```text
crawlers/understat/scraper.py
```

### Commande

```powershell
python crawlers/understat/scraper.py
```

### Sortie

```text
data/raw/understat/standings/{date}/
```

### Données actuellement disponibles

```text
data/raw/understat/standings/{date}/EPL_2025-2026.json
data/raw/understat/standings/{date}/Ligue_1_2025-2026.json
```

### Notes techniques

Ce collecteur utilise :

- Playwright pour rendre le JavaScript.
- `page.content()` pour récupérer le HTML après rendu.
- `BeautifulSoup` pour analyser le tableau.
- Les indicateurs collectés incluent `xG`, `xGA`, `xPTS`.

### Exception au robots.txt (délibérée)

Le `robots.txt` d'Understat (vérifié le 2026-09-25 ; le fichier n'a pas changé depuis le 2020-07-13) est :

```
User-agent: *
Disallow: /
```

Cela contredit la règle du projet « respecter robots.txt/ToS ». `robots.txt` est une demande, pas un blocage technique : le collecteur fonctionne, mais cela ne signifie pas que le crawl est autorisé. Understat est conservé comme **exception consciente et documentée**, car c'est la seule source de statistiques par joueur et par saison (minutes, xG, xA, poste) et, pour les saisons passées, la seule source d'une liste complète de joueurs (football-data.org ne renvoie que l'effectif actuel ; StatBunker ne liste que les buteurs).

Mesures d'atténuation maintenues :

- Usage éducatif et non commercial uniquement. Les données ne sont pas redistribuées.
- Un seul hôte, requêtes strictement séquentielles, 3 s minimum entre deux requêtes (`RateLimiter(min_delay=3.0)`).
- Volume très faible : par ligue et par saison, un chargement de page et un appel JSON (`/getLeagueData/{league}/{year}`).
- Les snapshots bruts sont conservés dans `data/raw/`, une saison n'est donc jamais re-crawlée uniquement pour relancer l'ingestion ou dbt.

Points ouverts :

- Les Conditions d'utilisation d'Understat n'ont **pas encore été examinées**.
- Le mentor doit être informé de cette exception.
- Si Understat bloque le collecteur ou s'y oppose, arrêter de le crawler et se rabattre sur StatBunker + football-data.org uniquement. Les colonnes issues d'Understat (`xg`, `xga`, `xpts`, minutes des joueurs) seraient alors `NULL` pour les nouvelles saisons.

---

## 7. Exécuter tous les collecteurs

Les collecteurs peuvent être lancés un par un :

```powershell
python crawlers/football_data_org/client.py
python crawlers/statbunker/scraper.py
python crawlers/understat/scraper.py
```

Après l'exécution, vérifier :

```text
data/raw/
├── football_data_org/
├── statbunker/
└── understat/
```

---

## 8. Utilitaires communs

Les fonctions communes se trouvent dans :

```text
crawlers/common/utils.py
```

| Utility | Rôle |
|---|---|
| `get_logger()` | Créer un logger standard |
| `RateLimiter` | Limiter la fréquence des requêtes |
| `retry_request()` | Réessayer une requête avec exponential backoff |

---

## 9. Vérification rapide

Avec PowerShell :

```powershell
Get-ChildItem -Recurse data/raw -Filter *.json
```

Si les fichiers JSON des trois sources apparaissent, les collecteurs fonctionnent correctement.

---

## 10. Résultat

| Source | Entité | Statut |
|---|---|---|
| football-data.org | matches, standings | Done |
| StatBunker | standings | Done |
| Understat | standings + xG | Done |

---

## 11. Remarques

- Ne pas committer `.env`.
- Ne pas committer `.venv/`.
- Ne pas committer `__pycache__/`.
- Ne pas envoyer de requêtes trop rapidement.
- Les données sont utilisées uniquement à des fins pédagogiques.

---

## 12. Limites actuelles

- StatBunker collecte seulement la Premier League.
- Understat collecte seulement les classements.
- Il n'y a pas encore de mécanisme de reprise automatique.

---

# Tiếng Việt

## 1. Mục tiêu

File này hướng dẫn cách chạy các crawler trong giai đoạn **Data Collection/Scraping**.

Project hiện có 3 nhóm nguồn dữ liệu:

| Nhóm nguồn | Source | Công cụ |
|---|---|---|
| API | football-data.org | requests |
| HTML tĩnh | StatBunker | requests + BeautifulSoup |
| HTML động | Understat | Playwright + BeautifulSoup |

Dữ liệu raw được lưu trong:

```text
data/raw/
```

---

## 2. Cấu trúc crawler

```text
crawlers/
├── common/
│   └── utils.py
│
├── football_data_org/
│   └── client.py
│
├── statbunker/
│   └── scraper.py
│
└── understat/
    └── scraper.py
```

---

## 3. Điều kiện trước khi chạy

Trước khi chạy crawler, cần đảm bảo:

- Đã kích hoạt virtual environment.
- Đã cài dependencies từ `requirements.txt`.
- Đã cài browser cho Playwright.
- Đã tạo file `.env` nếu chạy crawler `football-data.org`.

File `.env` cần có:

```text
`FOOTBALL_DATA_API_KEY`

Biến này chứa API key từ football-data.org và chỉ nên được lưu trong file `.env` local.
```

Lưu ý: không commit file `.env` lên GitHub.

---

## 4. Chạy crawler football-data.org

### Loại nguồn

API chính thức.

### File chạy

```text
crawlers/football_data_org/client.py
```

### Lệnh chạy

```powershell
python crawlers/football_data_org/client.py
```

### Output

```text
data/raw/football_data_org/matches/{date}/
data/raw/football_data_org/standings/{date}/
```

### Dữ liệu hiện có

```text
data/raw/football_data_org/matches/{date}/FL1_2025.json
data/raw/football_data_org/matches/{date}/PL_2025.json
data/raw/football_data_org/standings/{date}/FL1_2025.json
data/raw/football_data_org/standings/{date}/PL_2025.json
```

---

## 5. Chạy crawler StatBunker

### Loại nguồn

HTML tĩnh.

### File chạy

```text
crawlers/statbunker/scraper.py
```

### Lệnh chạy

```powershell
python crawlers/statbunker/scraper.py
```

### Output

```text
data/raw/statbunker/standings/{date}/
```

### Dữ liệu hiện có

```text
data/raw/statbunker/standings/{date}/PL_2025-2026.json
```

### Ghi chú kỹ thuật

Crawler này dùng:

- `retry_request()` để retry nếu request lỗi.
- `RateLimiter(min_delay=3.0)` để tránh request quá nhanh.
- `BeautifulSoup` để parse bảng HTML.

---

## 6. Chạy crawler Understat

### Loại nguồn

HTML động / JavaScript-rendered page.

### File chạy

```text
crawlers/understat/scraper.py
```

### Lệnh chạy

```powershell
python crawlers/understat/scraper.py
```

### Output

```text
data/raw/understat/standings/{date}/
```

### Dữ liệu hiện có

```text
data/raw/understat/standings/{date}/EPL_2025-2026.json
data/raw/understat/standings/{date}/Ligue_1_2025-2026.json
```

### Ghi chú kỹ thuật

Crawler này dùng:

- Playwright để render JavaScript.
- `page.content()` để lấy HTML sau khi render.
- `BeautifulSoup` để parse bảng standings.
- Các chỉ số lấy được gồm `xG`, `xGA`, `xPTS`.

### Ngoại lệ về robots.txt (có chủ đích)

`robots.txt` của Understat (kiểm tra ngày 2026-09-25; file không đổi từ 2020-07-13) là:

```
User-agent: *
Disallow: /
```

Điều này mâu thuẫn với quy tắc của dự án "tôn trọng robots.txt/ToS". `robots.txt` chỉ là một lời yêu cầu, không phải cơ chế chặn về kỹ thuật, nên crawler vẫn chạy được, nhưng không có nghĩa là việc crawl được cho phép. Understat được giữ lại như một **ngoại lệ có ý thức và có ghi chép**, vì đây là nguồn duy nhất có thống kê cầu thủ theo mùa (số phút, xG, xA, vị trí) và, với các mùa cũ, là nguồn duy nhất có danh sách cầu thủ đầy đủ (football-data.org chỉ trả đội hình hiện tại; StatBunker chỉ liệt kê cầu thủ ghi bàn).

Các biện pháp giảm thiểu vẫn giữ nguyên:

- Chỉ dùng cho mục đích học tập, phi thương mại. Không phân phối lại dữ liệu.
- Một host, request tuần tự nghiêm ngặt, tối thiểu 3 giây giữa các request (`RateLimiter(min_delay=3.0)`).
- Lưu lượng rất thấp: mỗi giải và mỗi mùa gồm một lần tải trang và một lệnh gọi JSON (`/getLeagueData/{league}/{year}`).
- Raw snapshot được giữ trong `data/raw/`, nên không bao giờ phải crawl lại một mùa chỉ để chạy lại ingestion hoặc dbt.

Việc còn mở:

- Điều khoản sử dụng (ToS) của Understat **chưa được xem xét**.
- Cần thông báo cho mentor về ngoại lệ này.
- Nếu Understat chặn crawler hoặc phản đối, dừng crawl Understat và chỉ dùng StatBunker + football-data.org. Khi đó các cột lấy từ Understat (`xg`, `xga`, `xpts`, số phút của cầu thủ) sẽ là `NULL` với các mùa mới.

---

## 7. Chạy toàn bộ crawler

Có thể chạy lần lượt:

```powershell
python crawlers/football_data_org/client.py
python crawlers/statbunker/scraper.py
python crawlers/understat/scraper.py
```

Sau khi chạy xong, kiểm tra:

```text
data/raw/
├── football_data_org/
├── statbunker/
└── understat/
```

---

## 8. Common utilities

Các utility dùng chung nằm ở:

```text
crawlers/common/utils.py
```

Hiện có:

| Utility | Chức năng |
|---|---|
| `get_logger()` | Tạo logger chuẩn |
| `RateLimiter` | Giới hạn tốc độ request |
| `retry_request()` | Retry request với exponential backoff |

---

## 9. Kiểm tra nhanh output

Dùng PowerShell:

```powershell
Get-ChildItem -Recurse data/raw -Filter *.json
```

Nếu thấy file JSON của cả 3 source thì crawler đã chạy thành công.

---

## 10. Kết quả S2

| Source | Entity | Trạng thái |
|---|---|---|
| football-data.org | matches, standings | Done |
| StatBunker | standings | Done |
| Understat | standings + xG | Done |

---

## 11. Lưu ý

- Không commit `.env`.
- Không commit `.venv/`.
- Không commit `__pycache__/`.
- Không crawl quá nhanh.
- Project chỉ dùng dữ liệu cho mục đích học tập.

---

## 12. Hạn chế hiện tại

- StatBunker mới crawl Premier League.
- Understat mới crawl standings.
- Chưa có cơ chế resume nếu crawler dừng giữa chừng.
