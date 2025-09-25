
import click
import asyncio
from .service import FilterService


def register_commands(app):
    @app.cli.command('test-rag')
    @click.option('--top-k', '-k', default=15, show_default=True,
                  help="Number of top results to return from RAG.")
    @click.option('--query-type', '-t', default='all', show_default=True,
                  help="Filter document types (e.g., TEXT, IMAGE, or 'all').")
    @click.option('--year', '-y', default='2025', show_default=True,
                  help="Filter by year (2024/2025).")
    def test_rag(top_k, query_type, year):
        """
        Test RAG pipeline with FilterService using your new architecture.
        """
        queries = [
            "Apa Profil kelulusan teknik industri ?",
            "Bagaimana struktur kurikulum prodi sarjana teknik mesin?",
            "Siapa sekretaris prodi teknik mesin?",
            "Apa prasyarat mata kuliah desain 1?",
            "Apa kompetensi utama dari lulusan teknik mesin?"
        ]

        async def main_logic():
            try:
                # Use the new service pattern  
                from flask import current_app
                filter_service = FilterService(current_app.vector_db, current_app.agent)

                click.secho(f"🚀 Starting RAG tests for {len(queries)} queries...", bold=True)
                click.echo(f"   → top_k={top_k}, query_type={query_type}, year={year}")

                for idx, query in enumerate(queries, 1):
                    click.echo("\n" + "="*80)
                    click.secho(f"({idx}/{len(queries)}) QUERY:", fg="cyan", bold=True)
                    click.echo(f"   {query}")
                    click.echo("-"*80)

                    try:
                        result = await filter_service.get_rag(
                            query=query,
                            top_k=top_k,
                            query_types=query_type,
                            year=year
                        )

                        context = result.get('context', '')
                        click.secho("Context snippet:", bold=True)
                        click.echo(context[:200].replace("\n", " ") + "…")

                        img_paths = result.get('image_paths', [])
                        csv_paths = result.get('csv_paths', [])
                        metas = result.get('metadatas', [])

                        click.secho(f"Image paths ({len(img_paths)}): {img_paths}", fg="yellow")
                        click.secho(f"CSV paths ({len(csv_paths)}): {csv_paths}", fg="yellow")
                        click.secho(f"Metadatas returned: {len(metas)} items", fg="green")

                    except Exception as e:
                        click.secho(f"❌ RAG query failed: {e}", fg="red")
                        continue

                click.echo("\n" + "="*80)
                click.secho("✅ RAG evaluation complete.", fg="green", bold=True)

            except Exception as e:
                click.secho(f"❌ Failed to initialize FilterService: {e}", fg="red")

        asyncio.run(main_logic())

    @app.cli.command('test-stream')
    @click.option('--query', '-q', default='What is DTMI?', show_default=True,
                  help="Query to test streaming with.")
    def test_streaming(query):
        """Test ChatOpenAI streaming without RAG pipeline."""
        try:
            click.secho(f"🔄 Testing streaming with query: {query}", bold=True)

            # Test streaming directly
            stream_agent = app.stream_agent
            from langchain_core.messages import SystemMessage, HumanMessage

            messages = [
                SystemMessage(content="You are a helpful assistant for DTMI UGM queries."),
                HumanMessage(content=query)
            ]

            click.echo("Streaming response:")
            click.echo("-" * 40)

            content = ""
            for chunk in stream_agent.stream(messages):
                if hasattr(chunk, 'content') and chunk.content:
                    content += chunk.content
                    click.echo(chunk.content, nl=False)

            click.echo("\n" + "-" * 40)
            click.secho("✅ Streaming test successful!", fg="green", bold=True)
            click.echo(f"Total content length: {len(content)} chars")

        except Exception as e:
            click.secho(f"❌ Streaming test failed: {e}", fg="red")

    @app.cli.command('ping-db')
    def ping_db():
        """Ping ChromaDB and ensure collection exists."""
        collection_name = app.config['COLLECTION_NAME']
        client = app.chroma_client  # Use lazy client
        click.secho("Pinging ChromaDB server...", fg="yellow")
        try:
            heartbeat = client.heartbeat()
            click.secho("✅ Success! ChromaDB server is responsive.", fg="green")
            collections = client.list_collections()
            collection_names = [col.name for col in collections]

            if collection_name in collection_names:
                click.secho(f"Collection '{collection_name}' already exists.", fg="green")
            else:
                client.create_collection(name=collection_name)
                click.secho(f"Collection '{collection_name}' created.", fg="yellow")

        except Exception as e:
            click.secho("❌ FAILED to connect to ChromaDB server.", fg="red")
            click.echo(f"   Error: {e}")

    @app.cli.command("info-db")
    def info_db():
        """Check connection to the collection and show document count."""
        db: Chroma = app.vector_db
        collection = db._collection  # This is the actual chromadb.Collection object

        click.secho(f"Checking collection '{collection.name}'...", fg="yellow")
        try:
            count = collection.count()
            click.secho(f"✅ Success! Connected to collection '{collection.name}'.", fg="green")
            click.echo(f"   Collection contains {count} documents.")
        except Exception as e:
            click.secho(f"❌ FAILED to get info for collection '{collection.name}'.", fg="red")
            click.echo(f"   Error: {e}")

    @app.cli.command('list-col')
    def list_collections():
        """List all collections in ChromaDB."""
        client = app.chroma_client

        click.secho("Fetching ChromaDB collections...", fg="yellow")
        try:
            collections = client.list_collections()
            if not collections:
                click.secho("⚠️  No collections found.", fg="red")
                return
            click.secho(f"✅ Found {len(collections)} collection(s):", fg="green")
            for col in collections:
                click.echo(f"  • {col.name}")
        except Exception as e:
            click.secho("❌ Failed to list collections.", fg="red")
            click.echo(f"   Error: {e}")

    @app.cli.command("routes")
    @click.option("--format", type=click.Choice(["plain", "md"]), default="plain",
                  help="Output format: plain text or Markdown table.")
    def list_routes(format):
        """List all registered routes/endpoints."""
        def clean_methods(methods):
            return sorted(m for m in methods if m not in ("HEAD", "OPTIONS"))

        routes = []
        for rule in app.url_map.iter_rules():
            routes.append({
                "blueprint": rule.endpoint.split(".", 1)[0] if "." in rule.endpoint else "main",
                "endpoint": rule.endpoint,
                "methods": clean_methods(rule.methods),
                "path": rule.rule,
            })

        routes.sort(key=lambda r: (r["blueprint"], r["path"]))

        if format == "md":
            click.echo(f"Found {len(routes)} routes.\n")
            click.echo("| Blueprint | Methods | Path | Endpoint |")
            click.echo("|----------|---------|------|----------|")
            for r in routes:
                methods = ",".join(r["methods"])
                click.echo(f"| {r['blueprint']} | {methods} | `{r['path']}` | {r['endpoint']} |")
            return

        # plain format
        click.echo(f"Found {len(routes)} routes.")
        click.echo("-" * 80)
        current_bp = None
        for r in routes:
            if r["blueprint"] != current_bp:
                current_bp = r["blueprint"]
                click.echo(f"\n{current_bp.upper()}:", nl=True)
            methods = ",".join(r["methods"])
            click.echo(f"  {methods:<10} {r['path']:<35} → {r['endpoint']}")
