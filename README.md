# AGLLMTest

# AGLLMTest (hardware-metrics-llm)

Bu proje, **local LLM’ler ile tool calling (function calling)** yaklaşımını öğrenmek ve uçtan uca pratik etmek için yapılmış bir **öğrenme/deneme projesidir**.

Sistem şu şekilde çalışır:
1) Collector belirli aralıklarla **CPU / RAM / GPU** metriklerini toplar.  
2) Metrikler **PostgreSQL**’e yazılır.  
3) FastAPI üzerinden gelen doğal dil soruları, LLM tarafından yorumlanır.  
4) LLM, uygun **SQL tool**’unu çağırır ve sonuçlara dayanarak kullanıcıya cevap üretir.

> Bu sürümde **hosts/host_id/hostname tamamen yoktur**. Veriler tek bir metrik akışı gibi tutulur. Aynı DB’ye birden fazla collector yazarsa veriler karışır.

---

## Özellikler

- **Collector service**: psutil + (varsa) `nvidia-smi`
- **DB**: PostgreSQL 16
- **API**: FastAPI
- **LLM Orchestrator**:
  - “son 10 dk / son 1 saat / geçen 30 dakika” gibi ifadelerden süre çıkarır
  - Uygun SQL tool’unu çağırır
  - Tool sonucunu LLM’e “bilgilendirici metin” olarak verip final cevabı üretir
- **Migration otomasyonu**: docker-compose içindeki `migrator` servisi, DB hazır olunca `alembic upgrade head` çalıştırır

---

## Gereksinimler

### Çalıştırmak için (önerilen)
- Docker Desktop (Windows/macOS) veya Docker Engine (Linux)
- Docker Compose v2

### Local LLM için
- OpenAI-compatible endpoint sunan bir local LLM çözümü (öneri: **Ollama**)
- Proje `POST {LLM_BASE_URL}/chat/completions` çağırır (OpenAI uyumlu)

### GPU metrikleri
- Container içinde `nvidia-smi` yoksa GPU değerleri **random** yazılır.
- Gerçek GPU metrikleri için NVIDIA driver + container runtime yapılandırması gerekir.

---

## Proje Yapısı (kısa)

- `app/services/collector.py` → metrik toplayıcı
- `app/api/v1/routers/llm.py` → `/api/v1/llm/ask`
- `app/llm/orchestrator.py` → tool çağrıları + final cevap üretimi
- `app/llm/tools/specs/*.json` → tool şemaları
- `app/llm/tools/sql/*.sql` → tool’ların SQL sorguları
- `alembic/` → migration yönetimi
- `docker-compose.yml` → db + migrator + api + collector

---

## Ortam Değişkenleri (.env)

Projede `.env` dosyası gerekir. `.env.example`’ı kopyalayıp düzenle:

```bash
cp .env.example .env

Örnek içerik:

# DB
DATABASE_URL_ASYNC=postgresql+asyncpg://app:app@db:5432/hwdb
DATABASE_URL_SYNC=postgresql+psycopg://app:app@db:5432/hwdb

# LLM (Ollama örneği)
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.1
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOOL_ITERATIONS=5

# Logging
LOG_LEVEL=INFO
LOG_DIR=/var/log/app

# Collector
METRICS_INTERVAL_SECONDS=10

    Not: Yanlış env isimleri sessizce yok sayılabilir; bu yüzden isimleri doğru yaz.

Kurulum ve Çalıştırma
1) Temiz başlangıç (DB dahil her şey sıfırlanır)

docker compose down -v
docker compose up --build

Bu akışta:

    Postgres volume silinir (tüm veriler gider)

    İmajlar build edilir

    migrator çalışır → alembic upgrade head

    Migration başarılı olunca api ve collector başlar

2) Servisleri kontrol et

docker compose ps

3) Logları izle

docker compose logs -f migrator
docker compose logs -f api
docker compose logs -f collector
docker compose logs -f db

    Uygulama logları ayrıca host makinede ./var/log/ altında birikir.

API Kullanımı
Health check

curl http://localhost:8000/api/v1/health

Beklenen:

{"status":"ok"}

LLM ile soru sorma

Endpoint:

    POST http://localhost:8000/api/v1/llm/ask

Body:

{"text":"Son 10 dk CPU max nedir?"}

Windows PowerShell örneği:

curl -X POST http://localhost:8000/api/v1/llm/ask `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"Son 10 dk CPU max nedir?\"}"

Cevap formatı:

{"answer":"..."}

Hangi Sorular Sorulmalı?

Sistem özellikle şu tip sorulara göre tasarlandı:
Zaman aralığı içeren sorular

    “Son 10 dk CPU max nedir?”

    “Son 1 saat GPU max kaç?”

    “Geçen 30 dakika RAM max kullanım yüzdesi nedir?”

    “Son 2 gün CPU sıcaklık max nedir?”

Desteklenen birimler:

    dk, dakika

    saat

    gün

Türkçe temel sayı kelimeleri desteklenir:

    “son bir saat”, “son on dakika”, “son otuz dk” vb.

“Şu an / şimdi” gibi ifadeler

    “Şu an CPU max nedir?”

        Sistem bunu pratikte son 5 dakika olarak yorumlar.

Snapshot (en güncel değerler)

    “En güncel metrikleri göster”

    “Son snapshot”

    “Şu an sistem durumu nedir?”

Mevcut Tool’lar

    get_latest_snapshot

    get_max_cpu_usage(minutes)

    get_max_cpu_temp(minutes)

    get_max_ram_usage_percent(minutes)

    get_max_gpu_utilization(minutes)

    Host filtresi yoktur. Tüm sorgular tek akış üzerinden çalışır.

Terminalde Sık Kullanılan Komutlar
Sistemi başlat

docker compose up --build

Arka planda çalıştır

docker compose up -d --build

Durdur

docker compose down

DB dahil her şeyi sil

docker compose down -v

DB’ye girip kontrol (psql)

docker compose exec db psql -U app -d hwdb

Örnek sorgular:

\dt
select * from metrics_cpu order by ts desc limit 5;
select max(usage_percent) from metrics_cpu where ts >= now() - interval '10 minutes';

Migration durumunu kontrol (container içinde)

docker compose exec api alembic current
docker compose exec api alembic heads

LLM’i Ollama ile Kurma (model pull / serve / test)

Bu proje OpenAI-compatible bir endpoint bekler. Ollama’yı local LLM olarak kullanmak için:
1) Ollama kurulumu

Ollama’yı resmi dağıtımından kur ve doğrula:

ollama --version

2) Model indirme (pull)

Örnek:

ollama pull llama3.1

Alternatifler:

ollama pull mistral
ollama pull qwen2.5

Mevcut modelleri listeleme:

ollama list

3) Ollama’yı çalıştırma (serve)

Çoğu kurulumda servis olarak arka planda çalışır. Gerekirse:

ollama serve

Ollama default:

    http://localhost:11434

4) Projeyi Ollama’ya bağlama (.env)

Docker container içinden host’taki Ollama’ya erişmek için .env:

LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.1

5) Hızlı test

Ollama’nın çalıştığını test et:

ollama run llama3.1 "Merhaba!"

Proje üzerinden tool calling test:

curl -X POST http://localhost:8000/api/v1/llm/ask `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"Son 10 dk CPU max nedir?\"}"

Troubleshooting
“alembic is not recognized” (Windows PowerShell)

Bu normaldir; alembic host makinede kurulu olmayabilir. Migration otomatik migrator servisiyle çalışır. Elle çalıştırmak istersen:

docker compose exec api alembic upgrade head

“relation metrics_cpu does not exist”

Migration çalışmamış demektir:

docker compose logs migrator
docker compose down -v
docker compose up --build

LLM endpoint’e bağlanamıyor

    .env içindeki LLM_BASE_URL doğru mu?

    Ollama çalışıyor mu?

    Model adı .env ile aynı mı?

GPU metrikleri hep random

Container içinde nvidia-smi yoktur veya erişim yoktur. Gerçek GPU metrikleri için NVIDIA container runtime yapılandırması gerekir.
Notlar

    Bazı metrikler okunamazsa bu proje random değer yazar (öğrenme/deneme amaçlı).

    Gerçek sistemlerde bunun yerine “unavailable” işaretleme veya ayrı alanlarla işaretlemek daha doğrudur.