# app/__init__.py
from flask import Flask, g, request, render_template, redirect, url_for
from .config import Config
from .commands import register_commands
from .routes import wablas_bp, stream_bp
from .service.chat_history import get_history

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.runnables.history import RunnableWithMessageHistory
from chromadb import HttpClient

import hashlib
import json
from pathlib import Path
from langchain_core.messages import SystemMessage


def create_app() -> Flask:
    import os
    # Use absolute path for static folder to ensure WSGI compatibility
    # static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
    app = Flask(__name__,  static_url_path="/static")
    app.config.from_object(Config)
    app.secret_key = app.config.get("SECRET_KEY")  # Flask expects SECRET_KEY
    app.config["MEMORY_EXCHANGES"] = 1
    @app.after_request
    def add_security_headers(response):
        # Content Security Policy to prevent XSS
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'; "
            "font-src 'self' https://fonts.gstatic.com; "
            "object-src 'none'; "
            "base-uri 'self';"
        )

        # Additional security headers
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response
    required = [
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_EMBEDDING_MODEL",
        "CHROMA_HOST",
        "CHROMA_PORT",
        "CHROMA_COLLECTION_NAME",
    ]
    missing = [k for k in required if not app.config.get(k)]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")
    # LLMs
    STREAM_SYSTEM_PREPROMPT = SystemMessage(content="""
    Kamu adalah **Tasya** alias Tanya Saya  asisten milik DTMI UGM 
    DTMI singkatan dari Departemen Teknik mesin dan Industri 
    TI adalah Teknik Industri TM adalah Teknik Mesin
    Kamu digunakan Untuk Membantu dosen maupun mahasiswa untuk menjawab informasi terkait administrasi dan informasi 
    DTMI dengan RAG ( Jangan dibilang secara eksplisit)
                            
    1. Jangan jawab pertanyaan umum seperti politik/sara, arahkan ke topik DTMI
    2. Tangani Basa basi dengan baik
    3. Gunakan konteks percakapan untuk jawaban yang berkesinambungan dan natural
    4. Jangan melakukan pencarian eksternal
    5. Berikan jawaban yang membantu dan relevan
                                     
    jika merupakan pertanyaan dengan konteks KLNTEKS RAG maka jawab 

    1. Jawab dengan informatif dan detil namun mudah dipahami
    2. Gunakan informasi dari context di atas
    3. Jika ada konteks percakapan, berikan jawaban yang berkesinambungan
    4. Jika dapat ditampilkan sebagai list maka tampilkan sebagai list
    5. PENTING: Jika tidak ada konteks yang relevan, jangan menggunakan general knowledge, cukup jawab:
    "Mohon maaf, data tidak ditemukan. Silakan hubungi administrasi DTMI UGM 🙏"
    6. Gunakan format yang baik dan tepat
    
    
    """)

    WABLASS_SYSTEM_PREPROMPT = SystemMessage(content="""
    Kamu adalah **Tasya** asisten DTMI UGM untuk WhatsApp Business.
    Berikan jawaban singkat, ramah, dan langsung to the point.
    Gunakan emoji yang sesuai dan bahasa yang casual tapi tetap informatif.
    
    Jika tidak ada konteks yang relevan, jawab:
    "Maaf data tidak ditemukan 😅 Coba hubungi admin DTMI ya 📞"
    """)

    # Create LLMs - system messages will be handled in prompt construction
    app.streaming_llm = ChatOpenAI(
        api_key=app.config["OPENAI_API_KEY"],
        model=app.config["OPENAI_MODEL"],
        # temperature=0,
        streaming=True,
    )

    # Agent LLM - no system preprompt (fully agnostic)
    app.agent = ChatOpenAI(
        api_key=app.config["OPENAI_API_KEY"],
        model=app.config["OPENAI_MODEL"],
        temperature=0,
        streaming=False,
        seed=0,
    )

    # WhatsApp Business LLM
    app.wablass_llm = ChatOpenAI(
        api_key=app.config["OPENAI_API_KEY"],
        model=app.config["OPENAI_MODEL"],
        temperature=0,
        streaming=True,
    )
    app.config['STREAM_SYSTEM_PROMPT'] = STREAM_SYSTEM_PREPROMPT.content
    app.config['WABLASS_SYSTEM_PROMPT'] = WABLASS_SYSTEM_PREPROMPT.content
    app.stream_agent = RunnableWithMessageHistory(
        runnable=app.streaming_llm,
        get_session_history=get_history,
    )

    # WhatsApp agent - NO HISTORY
    app.wablass_agent = app.wablass_llm

    # Embeddings + Vector DB
    app.emb_model = OpenAIEmbeddings(
        api_key=app.config["OPENAI_API_KEY"],
        model=app.config["OPENAI_EMBEDDING_MODEL"],
    )
    app.chroma_client = HttpClient(
        host=app.config["CHROMA_HOST"],
        port=int(app.config["CHROMA_PORT"]),
    )
    app.vector_db = Chroma(
        client=app.chroma_client,
        collection_name=app.config["CHROMA_COLLECTION_NAME"],
        embedding_function=app.emb_model,
    )

    def _client_fingerprint() -> str:
        fwd = request.headers.get("X-Forwarded-For") or ""
        ip = fwd.split(",")[0].strip() if fwd else (request.remote_addr or "0.0.0.0")
        ua = request.headers.get("User-Agent", "")
        h = hashlib.blake2b(digest_size=16)
        h.update(f"{ip}|{ua}".encode("utf-8"))
        return h.hexdigest()

    @app.before_request
    def ensure_session_id():
        g.session_id = _client_fingerprint()

    @app.route("/")
    def serve_index():
        prompts = []
        path = Path(app.root_path) / "data" / "default_prompts.json"
        try:
            if path.exists():
                prompts = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            # Not logging a novel here. Just enough context if it blows up elsewhere.
            raise ValueError(f"Invalid JSON in {path}: {e}") from e
        return render_template("index.html", default_prompts=prompts)
    @app.route("/reset-conversation")
    def reset_conversation():
        """Reset conversation history and redirect to home"""
        try:
            history = get_history(g.session_id)
            history.clear()
        except Exception as e:
            print(f"Reset conversation error: {e}")

        return redirect(url_for('serve_index'))

    # CLI commands and HTTP routes
    register_commands(app)
    app.register_blueprint(wablas_bp)
    app.register_blueprint(stream_bp)

    return app
