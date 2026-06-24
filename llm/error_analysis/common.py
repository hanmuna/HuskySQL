import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_JSON = os.path.join(ROOT, "data", "dev.json")
DB_ROOT = os.path.join(ROOT, "data", "dev_databases")
OUT_DIR = os.path.join(HERE, "outputs")

BIRD_SEP = "\t----- bird -----\t"

os.makedirs(OUT_DIR, exist_ok=True)


def _load_dotenv():
    path = os.path.join(HERE, ".env")
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.2-chat-latest")
BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.aimlapi.com/v1")


def db_path(db_id):
    return os.path.join(DB_ROOT, db_id, f"{db_id}.sqlite")


def load_dataset():
    with open(DATA_JSON, "r") as f:
        return json.load(f)


def load_questions():
    """Full BIRD dev set (all 1534 questions, 11 dbs)."""
    data = load_dataset()
    return list(enumerate(data))


def get_openai_client():
    from openai import OpenAI

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY not set (put your AIML key in error_analysis/.env)")
    return OpenAI(api_key=key, base_url=BASE_URL)


def chat(client, prompt, max_completion_tokens=2048):
    """GPT-5 series: no stop / no custom temperature; use max_completion_tokens."""
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=max_completion_tokens,
    )
    return resp.choices[0].message.content


def write_jsonl(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    with open(path, "r") as f:
        return [json.loads(line) for line in f if line.strip()]
