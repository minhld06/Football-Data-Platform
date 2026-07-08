# README Scraping — Football Data Platform

# 🇫🇷 Français

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

# 🇻🇳 Tiếng Việt

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