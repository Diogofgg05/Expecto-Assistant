"""Capture real Expecto browser UI as reproducible PNG + MP4 previews.

Runs the checked-out frontend in Chromium with *synthetic, explicitly labeled*
example data. No private memory/database, Ollama, microphone or network providers.
Do not use these clips as performance, voice-quality or AI-accuracy evidence.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "previews"
WIDTH, HEIGHT = 1280, 720

MEMORY = [
    {"id": "demo-01", "category": "project", "content": "Expecto — desenvolvimento do assistente holográfico e dos seus motores locais.", "created_at": "2026-10-28T17:00:00"},
    {"id": "demo-02", "category": "preference", "content": "Interface com holograma central e comandos de linguagem natural, sem menus permanentes.", "created_at": "2026-10-28T17:01:00"},
    {"id": "demo-03", "category": "experience", "content": "Exemplo de memória persistente. Estes dados foram criados apenas para o preview.", "created_at": "2026-10-28T17:02:00"},
]
RESEARCH = {
    "topic": "Sistemas locais de inteligência artificial",
    "warning": "FONTES FICTÍCIAS PARA DEMONSTRAÇÃO — não foi realizada pesquisa na Internet.",
    "documents": [
        {"title": "Arquitetura modular — exemplo", "content": "Pesquisa híbrida, classificação de tarefas e verificação são módulos independentes com limites próprios.", "source_type": "demo", "evidence_level": "illustrative"},
        {"title": "Privacidade local — exemplo", "content": "O processamento local minimiza a transmissão de dados; cada fonte real requer autorização e validação.", "source_type": "demo", "evidence_level": "illustrative"},
        {"title": "Métricas — exemplo", "content": "Tempos de resposta, memória utilizada e consumo devem ser medidos em hardware real.", "source_type": "demo", "evidence_level": "illustrative"},
    ],
}
DIAGNOSTICS = {
    "ollama": {"available": False, "selected": "hermes3", "selected_installed": False, "models": []},
    "memory_count": "EXEMPLO", "episodes_6months": "DEMO",
    "episodic_capture": False, "memory_months": 6,
    "knowledge_count": 0, "research_jobs": 0,
    "semantic_indexed": 0, "extracted_knowledge": 0, "extraction_active": False,
    "temporal_facts": 0, "relation_links": 0, "consolidation": {},
    "private_mode": True, "encrypted_backups_enabled": False,
    "active_database_encrypted": False, "research_provider": "Desativado",
}


class DemoHTTP(SimpleHTTPRequestHandler):
    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/api/config":
            data = json.dumps({"voice_output": False}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if route == "/":
            self.path = "/web/index.html"
        elif route.startswith("/static/"):
            self.path = "/web/" + route[len("/static/"):]
        else:
            self.send_error(404, "Only local demonstration frontend is available")
            return
        super().do_GET()

    def log_message(self, _format, *_args):
        return


def open_page(browser, address, *, video_dir=None):
    opts = {"viewport": {"width": WIDTH, "height": HEIGHT}, "device_scale_factor": 1,
            "locale": "pt-PT", "color_scheme": "dark"}
    if video_dir:
        opts["record_video_dir"] = str(video_dir)
        opts["record_video_size"] = {"width": WIDTH, "height": HEIGHT}
    ctx = browser.new_context(**opts)
    page = ctx.new_page()
    page.goto(address, wait_until="load", timeout=30000)
    page.wait_for_function("typeof window.AuraUI !== 'undefined' && typeof window.AuraOrb !== 'undefined'")
    page.wait_for_timeout(750)
    return ctx, page


def panel(page, name, data):
    page.evaluate("({name, data}) => window.AuraUI.openPanel(name, data)",
                  {"name": name, "data": data})
    page.wait_for_timeout(760)


def show_listening(page):
    page.evaluate("""() => {
        const app = document.getElementById('app');
        app.classList.remove('thinking', 'speaking');
        app.classList.add('listening');
        window.AuraOrb.setMode('listening');
        document.getElementById('aura-presence').textContent = 'A OUVIR · PRÉ-VISUALIZAÇÃO';
        const transcript = document.getElementById('live-transcript');
        transcript.textContent = 'EXEMPLO VISUAL · ESTADO DO MICROFONE\nNenhum áudio foi capturado nesta demonstração.';
        transcript.classList.add('visible');
    }""")
    page.wait_for_timeout(450)


def convert_video(webm: Path, destination: Path):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-i", str(webm), "-an", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "31", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         "-vf", "fps=20", str(destination)],
        check=True, timeout=90,
    )
    if not destination.is_file() or destination.stat().st_size < 1000:
        raise RuntimeError(f"MP4 não foi produzido: {destination}")


def record(browser, address, tmp: Path, filename: str, actions):
    ctx, page = open_page(browser, address, video_dir=tmp)
    try:
        actions(page)
        video = page.video
    finally:
        ctx.close()
    if not video:
        raise RuntimeError("Chromium did not produce video")
    convert_video(Path(video.path()), OUTPUT / filename)


def render():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    handler = partial(DemoHTTP, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{server.server_port}/"
    try:
        with tempfile.TemporaryDirectory(prefix="expecto_previews_") as workspace:
            temp = Path(workspace)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                try:
                    shots = [
                        ("21-interface-inicial-2026.png", lambda page: None),
                        ("22-memoria-demonstracao-2026.png",
                         lambda page: panel(page, "memory", MEMORY)),
                        ("23-patronum-demonstracao-2026.png",
                         lambda page: (page.evaluate(
                             "document.getElementById('app').classList.add('patronum')"),
                             panel(page, "patronum", {
                                 "ollama_available": False, "memories": 3,
                                 "documents": 0, "conversations_6months": 0,
                                 "recommendations": ["EXEMPLO: analisar tarefas pendentes com autorização."]
                             }))),
                        ("24-diagnosticos-demonstracao-2026.png",
                         lambda page: panel(page, "diagnostics", DIAGNOSTICS)),
                        ("25-pesquisa-demonstracao-2026.png",
                         lambda page: panel(page, "research", RESEARCH)),
                        ("26-voz-estado-demonstracao-2026.png",
                         lambda page: show_listening(page)),
                    ]
                    for filename, action in shots:
                        ctx, page = open_page(browser, address)
                        try:
                            action(page)
                            page.screenshot(path=str(OUTPUT / filename), animations="disabled")
                        finally:
                            ctx.close()
                    record(
                        browser, address, temp, "27-holograma-em-movimento.mp4",
                        lambda page: page.wait_for_timeout(4200),
                    )
                    def cycle(page):
                        panel(page, "memory", MEMORY)
                        page.wait_for_timeout(950)
                        page.evaluate("window.AuraUI.closeAll()")
                        page.wait_for_timeout(450)
                        panel(page, "research", RESEARCH)
                        page.wait_for_timeout(1250)
                        page.evaluate("window.AuraUI.closeAll()")
                        page.wait_for_timeout(300)
                        show_listening(page)
                        page.wait_for_timeout(800)
                    record(browser, address, temp, "28-paineis-dinamicos.mp4", cycle)
                finally:
                    browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print("Previews reais da interface com dados fictícios:")
    for f in sorted(OUTPUT.iterdir()):
        if f.name[:2] in {"21", "22", "23", "24", "25", "26", "27", "28"}:
            print(f" - {f.name}: {f.stat().st_size} bytes")


if __name__ == "__main__":
    render()
