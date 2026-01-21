
```markdown
# 🤖 AGLLMTest (Hardware Metrics LLM)

**AGLLMTest**, yerel LLM'ler (Local Large Language Models) ile **Tool Calling (Function Calling)** yaklaşımını öğrenmek, denemek ve uçtan uca pratik etmek için geliştirilmiş bir **öğrenme projesidir**.

Bu proje, sistem metriklerini (CPU, RAM, GPU) toplar, bir veritabanına yazar ve kullanıcının doğal dil ile sorduğu soruları (örneğin: *"Son 10 dakika CPU max nedir?"*) SQL sorgularına dönüştürerek yanıtlar.

---

## ⚙️ Nasıl Çalışır?

Sistem şu 4 temel adımda işler:

1.  **Collector:** Belirli aralıklarla CPU, RAM ve GPU metriklerini toplar.
2.  **Storage:** Toplanan metrikler **PostgreSQL** veritabanına yazılır.
3.  **LLM Orchestrator:** FastAPI üzerinden gelen doğal dil soruları LLM tarafından yorumlanır.
4.  **Tool Execution:** LLM, soruyu cevaplamak için uygun **SQL tool**'unu çağırır ve elde ettiği veriyi yorumlayarak son kullanıcıya cevap üretir.

> ⚠️ **Önemli Not:** Bu sürümde `hosts`, `host_id` veya `hostname` ayrımı **yoktur**. Veriler tek bir metrik akışı olarak kabul edilir. Aynı veritabanına birden fazla collector yazarsa veriler karışabilir.

---

## 🚀 Özellikler

* **Collector Service:** `psutil` ve (varsa) `nvidia-smi` kullanarak veri toplar.
* **Database:** PostgreSQL 16.
* **API:** FastAPI tabanlı REST API.
* **LLM Orchestrator:**
    * "Son 10 dk", "Geçen 1 saat" gibi zaman ifadelerini ayrıştırır.
    * Uygun SQL fonksiyonunu seçer.
    * Sorgu sonucunu LLM'e bağlam olarak verip doğal dil cevabı üretir.
* **Otomatik Migration:** `docker-compose` içindeki `migrator` servisi, DB hazır olduğunda otomatik olarak `alembic upgrade head` çalıştırır.

---

## 📋 Gereksinimler

### Çalıştırmak İçin (Önerilen)
* **Docker Desktop** (Windows/macOS) veya **Docker Engine** (Linux)
* **Docker Compose v2**

### Local LLM İçin
* OpenAI uyumlu endpoint sunan bir yerel LLM çözümü.
* **Öneri:** [Ollama](https://ollama.com/)
* Proje `POST {LLM_BASE_URL}/chat/completions` adresine istek atar.

### GPU Metrikleri Hakkında
* Container içinde `nvidia-smi` erişimi yoksa GPU değerleri **random (rastgele)** üretilir.
* Gerçek GPU metrikleri için NVIDIA Driver + Container Runtime yapılandırması gereklidir.

---

## 📂 Proje Yapısı

* `app/services/collector.py` ➤ Metrik toplayıcı servis.
* `app/api/v1/routers/llm.py` ➤ `/api/v1/llm/ask` endpoint'i.
* `app/llm/orchestrator.py` ➤ Tool çağrıları ve cevap üretim mantığı.
* `app/llm/tools/specs/*.json` ➤ Tool şemaları (OpenAI formatı).
* `app/llm/tools/sql/*.sql` ➤ Tool'ların çalıştırdığı SQL sorguları.
* `alembic/` ➤ Veritabanı migration yönetimi.
* `docker-compose.yml` ➤ Tüm servislerin (db, api, collector, migrator) orkestrasyonu.

---

## 🔧 Kurulum ve Yapılandırma

### 1. Ortam Değişkenleri (.env)

Projeyi çalıştırmadan önce `.env` dosyası oluşturulmalıdır. Örnek dosyayı kopyalayın:

```bash
cp .env.example .env

```

**Örnek `.env` içeriği:**

```dotenv
# DB Bağlantıları
DATABASE_URL_ASYNC=postgresql+asyncpg://app:app@db:5432/hwdb
DATABASE_URL_SYNC=postgresql+psycopg://app:app@db:5432/hwdb

# LLM Ayarları (Ollama Örneği)
# Docker içinden host makinedeki Ollama'ya erişim için host.docker.internal kullanılır
LLM_BASE_URL=[http://host.docker.internal:11434/v1](http://host.docker.internal:11434/v1)
LLM_MODEL=llama3.1
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOOL_ITERATIONS=5

# Logging
LOG_LEVEL=INFO
LOG_DIR=/var/log/app

# Collector
METRICS_INTERVAL_SECONDS=10

```

### 2. Başlatma (Docker Compose)

Temiz bir başlangıç yapmak (DB dahil her şeyi sıfırdan kurmak) için:

```bash
# Eski volume'leri temizle ve yeniden build et
docker compose down -v
docker compose up --build

```

Bu işlem sırasıyla şunları yapar:

1. Postgres volume silinir (veri sıfırlanır).
2. İmajlar build edilir.
3. `migrator` servisi çalışır ve tabloları oluşturur.
4. Migration bitince `api` ve `collector` servisleri başlar.

### 3. Kontrol ve Loglar

Servislerin durumunu görmek için:

```bash
docker compose ps

```

Logları canlı izlemek için:

```bash
docker compose logs -f api      # API logları
docker compose logs -f collector # Collector logları
docker compose logs -f db       # Veritabanı logları

```

---

## 🔌 API Kullanımı

### Health Check

Sistemin ayakta olduğunu doğrulamak için:

```bash
curl http://localhost:8000/api/v1/health
# Beklenen Cevap: {"status":"ok"}

```

### LLM ile Soru Sorma

Metriklerle ilgili soru sormak için:

**Endpoint:** `POST http://localhost:8000/api/v1/llm/ask`

**Örnek İstek (Curl - Linux/Mac):**

```bash
curl -X POST http://localhost:8000/api/v1/llm/ask \
  -H "Content-Type: application/json" \
  -d '{"text":"Son 10 dk CPU max nedir?"}'

```

**Örnek İstek (PowerShell - Windows):**

```powershell
curl -X POST http://localhost:8000/api/v1/llm/ask `
  -H "Content-Type: application/json" `
  -d "{\"text\":\"Son 10 dk CPU max nedir?\"}"

```

**Beklenen Cevap:**

```json
{
  "answer": "Son 10 dakika içindeki maksimum CPU kullanımı %45 olarak ölçülmüştür."
}

```

---

## 🧠 LLM ve Prompt Kılavuzu

Sistem aşağıdaki soru tiplerine ve zaman ifadelerine duyarlıdır:

### Desteklenen Soru Tipleri

* **Zaman Aralığı:** "Son 10 dk CPU max nedir?", "Geçen 1 saat GPU max kaç?"
* **Anlık Durum:** "Şu an CPU kullanımı kaç?", "En güncel metrikleri göster." (Sistem "şu an" ifadesini pratikte son 5 dakika veya son snapshot olarak yorumlar).
* **Birimler:**
* Dakika: `dk`, `dakika`
* Saat: `saat`
* Gün: `gün`


* **Sayı İfadeleri:** "Son bir saat", "son on dakika" gibi Türkçe ifadeler desteklenir.

### Mevcut Tool'lar

LLM arka planda şu fonksiyonları çağırabilir:

* `get_latest_snapshot`
* `get_max_cpu_usage(minutes)`
* `get_max_cpu_temp(minutes)`
* `get_max_ram_usage_percent(minutes)`
* `get_max_gpu_utilization(minutes)`

---

## 🦙 Ollama Kurulumu (Local LLM)

Bu proje OpenAI uyumlu bir endpoint bekler. Ollama'yı yerel LLM sunucusu olarak kullanmak için adımlar:

1. **Kurulum:** [Ollama.com](https://ollama.com) üzerinden indirip kurun.
```bash
ollama --version

```


2. **Model İndirme:** Projede kullanacağınız modeli çekin (`.env` dosyasındaki `LLM_MODEL` ile aynı olmalıdır).
```bash
ollama pull llama3.1
# veya
ollama pull mistral

```


3. **Çalıştırma:**
```bash
ollama serve
# Default port: 11434

```


4. **Test:**
```bash
ollama run llama3.1 "Merhaba!"

```



---

## 🛠 Troubleshooting (Sorun Giderme)

| Hata / Durum | Çözüm |
| --- | --- |
| **`alembic is not recognized`** | Bu normaldir. Migration container içinde otomatik çalışır. Elle çalıştırmak için: `docker compose exec api alembic upgrade head` |
| **`relation metrics_cpu does not exist`** | Migration çalışmamış. DB'yi sıfırlayın: `docker compose down -v` ardından `docker compose up --build` |
| **LLM Bağlantı Hatası** | 1. `.env` içindeki `LLM_BASE_URL` doğru mu?<br>

<br>2. Ollama çalışıyor mu?<br>

<br>3. Model adı doğru mu? |
| **GPU Metrikleri Random Geliyor** | Container içinde NVIDIA sürücüleri yoktur. Bu proje, GPU erişimi yoksa test amaçlı rastgele veri üretir. |

---

> 📝 **Not:** Bazı metrikler sistemden okunamadığında bu proje **random** değerler yazar. Bu davranış sadece öğrenme/deneme amaçlıdır. Gerçek sistemlerde "unavailable" olarak işaretlenmesi önerilir.

```

```
