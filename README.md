# ভূমিপত্র: ডিজিটাল ভূমি রেকর্ড, যাচাই ও ই-মিউটেশন (প্রোটোটাইপ)

LandTech Innovation Hackathon 2026, ডাফোডিল ইন্টারন্যাশনাল ইউনিভার্সিটি। শুধু কাল্পনিক তথ্য ব্যবহার করুন, আসল NID বা জমির তথ্য নয়। এটি সরকারি সফটওয়্যার নয়।

## কীভাবে কাজ করে

```
ব্রাউজার ──▶ nginx ──▶ Next.js (ফ্রন্টএন্ড + নিরাপদ প্রক্সি) ──▶ Django API ──▶ PostgreSQL
                         (টোকেন httpOnly কুকিতে)                (হ্যাশ চেইন, সাইন, অডিট)
```

## ফোল্ডার

| ফোল্ডার | কী আছে |
|---|---|
| `core/` | হ্যাশ চেইন, Ed25519 সিগনেচার, workflow, আপলোড যাচাই (Django ছাড়াই চলে ও টেস্ট হয়) |
| `accounts/` | ইউজার, রোল, নিবন্ধন, লগইন (JWT), লকআউট, `create_staff_user` |
| `audit/` | হ্যাশ-চেইনযুক্ত অডিট লগ |
| `records/` | জমি, মালিক, ইতিহাস, চেকপয়েন্ট, সার্চ/QR/যাচাই API, `verify_integrity`, `seed_demo` |
| `mutations/` | নামজারির আবেদন, ধাপ, ফাইল, নোটিফিকেশন |
| `frontend/` | Next.js (বাংলা/ইংরেজি, মোবাইল-ফ্রেন্ডলি, রোল অনুযায়ী ড্যাশবোর্ড) |
| `deploy/`, `Dockerfile`, `docker-compose.prod.yml` | সব একসাথে চালানোর ব্যবস্থা |
| `scripts/` | `start_demo.sh`, `check_all.sh`, `reset_demo_db.sh`, `backup_db.sh` |
| `SECURITY.md` | ঝুঁকি, প্রতিরোধ, বাকি কাজ, প্রোডাকশন চেকলিস্ট |
| `docs/PRESENTATION.md` | উপস্থাপনা ও ডেমোর স্ক্রিপ্ট, প্রশ্নোত্তর |
| `website/index.html` | পরিচিতির ওয়েবসাইট (হ্যাশ চেইনের ইন্টারঅ্যাক্টিভ ডেমোসহ) |

## প্রথমবার চালানো (Linux)

1. `sudo apt install -y python3-venv python3-pip postgresql nodejs npm` (Node ১৮.১৭ বা নতুন লাগবে)
2. `cp .env.example .env`, তারপর চারটি গোপন মান ও সিগনেচার চাবি বসান (কমান্ড `.env.example`-এর ওপরে লেখা আছে)
3. ডাটাবেস: `sudo -u postgres psql -c "CREATE USER bhumipatra WITH PASSWORD '<DB_PASSWORD>' CREATEDB;"` ও `sudo -u postgres psql -c "CREATE DATABASE bhumipatra OWNER bhumipatra;"`
4. `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
5. `python manage.py makemigrations accounts audit records mutations` (**এই ফাইলগুলো প্রজেক্টের অংশ, রেখে দিন, Docker-এও লাগবে**)
6. `python manage.py migrate`
7. `cd frontend && npm install && cp .env.example .env.local && cd ..`
8. `bash scripts/check_all.sh`: সব পরীক্ষা এক কমান্ডে
9. `python manage.py seed_demo` (ডেমো অ্যাকাউন্টের পাসওয়ার্ড একবারই দেখায়)
10. `bash scripts/start_demo.sh` তারপর http://localhost:3000

কাজ না করলে `check_all.sh`-এর কোন ধাপ FAIL হলো সেটা দেখুন। রোজ ডেমোর আগে `bash scripts/reset_demo_db.sh` দিয়ে নতুন ডেটা নিন।

## অফিসার অ্যাকাউন্ট বানানো

```
python manage.py create_staff_user --username officer_x --role ac_land
```
পাসওয়ার্ড কমান্ডে লিখতে হয় না, জিজ্ঞেস করে (লুকানো)। রোল: `ac_land`, `surveyor`, `lawyer`, `admin`।

## সার্ভারে চালানো (Docker/Podman)

1. `.env`-এ আসল (নতুন) গোপন মান বসান। উন্নয়নের চাবি আর নয়।
2. `docker compose -f docker-compose.prod.yml up -d --build` (podman হলে `podman-compose -f ...`)
3. http://localhost:8080 (পোর্ট বদলাতে `.env`-এ `HTTP_PORT`, QR-এর ঠিকানার জন্য `PUBLIC_URL`)
4. শুধু nginx বাইরে খোলা। Django ও ডাটাবেস ভেতরের নেটওয়ার্কে।
5. HTTPS ছাড়া কুকি কাজ করবে না। সত্যিকারের ব্যবহারে `deploy/nginx/default.conf.template`-এ TLS বসান। শুধু `http://localhost`-এ পরখ করতে `.env`-এ `COOKIE_SECURE=false` দিন।
6. ব্যাকআপ: `bash scripts/backup_db.sh`

> Docker অংশ আমি এখানে চালিয়ে পরীক্ষা করতে পারিনি। প্রথমবার চালানোর সময় এরর এলে সেটা পেস্ট করে জানান।

## API এক নজরে

- `POST /api/auth/register|login|refresh|logout/`, `GET /api/auth/me/`
- `GET /api/parcels/search/`, `GET /api/parcels/<id>/`, `GET /api/parcels/<id>/qr.svg`
- `GET /api/verify/<id>/<head_prefix>/` (লগইন ছাড়া, ব্যক্তিগত তথ্য ছাড়া)
- `POST /api/mutations/`, `GET /api/mutations/mine|queue/`, `GET /api/mutations/<id>/`
- `POST /api/mutations/<id>/action/` (survey_verify, survey_reject, approve, reject, cancel)
- `POST|GET /api/mutations/<id>/documents/[<doc_id>/]`, `GET /api/notifications/`

## অবস্থা

Day 1-7 সম্পন্ন। এটি প্রোটোটাইপ। সরকারি ব্যবহারের আগে `SECURITY.md`-র "যা এখনো বাকি" তালিকা শেষ করতে হবে।
