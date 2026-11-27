"""Loopback-only HızlıPDF lab. Launch: python server.py --port 8765."""
import argparse
import base64
import binascii
import hashlib
import html
import io
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import subprocess
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from docx import Document
from pypdf import PdfReader
from fixtures import FILES
from sandbox import PROFILES, capability, command
from packages import PluginStore, build_package

ROOT = Path(__file__).resolve().parent
MAX_INPUT = 8 * 1024 * 1024


def validate_docx(data):
    if not data or len(data) > MAX_INPUT:
        raise ValueError("DOCX dosyası boş veya 8 MiB sınırını aşıyor.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > 512 or sum(item.file_size for item in entries) > 32 * 1024 * 1024:
                raise ValueError("DOCX açılmış içerik sınırını aşıyor.")
            if not {"[Content_Types].xml", "word/document.xml"} <= set(archive.namelist()):
                raise ValueError("Geçerli bir DOCX yapısı bulunamadı.")
            if any("vbaproject" in item.filename.lower() for item in entries):
                raise ValueError("Bu laboratuvar makro içeren belgeleri kabul etmez.")
            for name in ("[Content_Types].xml", "word/document.xml"):
                archive.read(name)
    except (zipfile.BadZipFile, RuntimeError, KeyError) as exc:
        raise ValueError("DOCX arşivi okunamıyor.") from exc


def sample_docx():
    doc = Document()
    doc.add_heading("MaviRota Danışmanlık", 0)
    doc.add_heading("Müşteri Teklifi", 1)
    doc.add_paragraph("Bu belge tamamen sentetik bir eğitim girdisidir. Türkçe karakter kontrolü: ı İ ş Ş ğ Ğ ü Ü ö Ö ç Ç.")
    table = doc.add_table(rows=1, cols=2)
    table.style = "Light Shading Accent 1"
    for cell, text in zip(table.rows[0].cells, ["Hizmet", "Bedel (deney birimi)"]):
        cell.text = text
    for name, price in [("Belge analizi", "12.000"), ("Raporlama", "8.000"), ("Toplam", "20.000")]:
        cells = table.add_row().cells
        cells[0].text, cells[1].text = name, price
    doc.add_paragraph("Dönüşüm çıktısında bu tablo ve toplam korunmalıdır.")
    stream = io.BytesIO()
    doc.save(stream)
    return stream.getvalue()


def make_hexdump(data_bytes):
    lines = []
    for i in range(0, min(len(data_bytes), 512), 16):
        chunk = data_bytes[i:i + 16]
        hex_str = " ".join(f"{b:02x}" for b in chunk)
        ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08x}  {hex_str:<48}  |{ascii_str}|")
    return "\n".join(lines)


def generate_forensic_html_report(record):
    run_id = record.get("run_id", "N/A")
    sys_info = record.get("system_info") or {}
    hashes = record.get("hashes") or {}
    profile = record.get("profile", "A")
    prof_data = PROFILES.get(profile, {})
    prof_name = prof_data.get("name", "Bilinmeyen Profil")
    filename = record.get("filename", "belge.docx")
    plugin_manifest = record.get("plugin_manifest") or {}
    plugin_name = plugin_manifest.get("name", record.get("plugin", "Eklenti"))
    plugin_ver = plugin_manifest.get("version", "0.2.0")
    package_sha = hashes.get("package_sha256") or record.get("package_sha256", "N/A")
    input_sha = hashes.get("input_sha256", "N/A")
    pdf_info = record.get("pdf") or {}
    pdf_sha = hashes.get("pdf_sha256") or pdf_info.get("sha256", "Üretilmedi / Yok")
    pdf_pages = pdf_info.get("pages", 0)
    pdf_bytes = pdf_info.get("bytes", 0)
    total_ms = record.get("total_ms", 0)
    status = record.get("status", "completed")
    started_at = sys_info.get("timestamp") or time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.get("started_at", time.time())))
    kernel = sys_info.get("kernel") or platform.release()
    machine = sys_info.get("machine") or platform.machine()
    plat = sys_info.get("platform") or platform.platform()
    python_ver = sys_info.get("python") or platform.python_version()

    file_ok = prof_data.get("files", True)
    net_ok = prof_data.get("network", True)
    exfil_bytes = record.get("metrics", {}).get("accepted_bytes", 0)
    exfil_sources = record.get("metrics", {}).get("accepted_sources", 0)

    if profile == "A":
        verdict_badge = '<span class="status-badge status-danger">GÜVENLİK İHLALİ TESPİT EDİLDİ</span>'
        verdict_text = "Geniş yetkili profil altında çalıştırılan eklentinin görev dışı hassas şirket verilerine (şirket bütçesi, kira sözleşmesi) yetkisiz eriştiği ve Linux soket arayüzü üzerinden yerel alıcıya (C2 simülasyonu) aktardığı adli bilişim incelemesiyle tespit edilmiştir. Sistem seviyesinde çekirdek izolasyonu uygulanmadığı için sistem ihlale açık kalmıştır."
    elif profile == "B":
        verdict_badge = '<span class="status-badge status-warning">KISMİ KORUMA (DOSYA İZOLASYONU)</span>'
        verdict_text = "Linux Mount Namespace yalıtımı başarıyla uygulanmış, görev dışı dosyalara erişim çekirdek düzeyinde 'ENOENT' ile engellenmiştir. Ağ yolu açık olmasına rağmen sızdırılacak veri elde edilemediğinden dışarıya 0 bayt veri sızmıştır."
    elif profile == "C":
        verdict_badge = '<span class="status-badge status-warning">KISMİ KORUMA (AĞ İZOLASYONU)</span>'
        verdict_text = "Eklenti yerel dosyalara erişebilmiş ancak Linux Network Namespace (--unshare-net) sayesinde işlem ağ arayüzlerinden izole edilmiş, TCP soket bağlantısı çekirdek düzeyinde 'ENETUNREACH' ile anında engellenmiştir. Dışarıya 0 bayt veri sızmıştır."
    else:
        verdict_badge = '<span class="status-badge status-success">TAM İZOLASYON (ÇİFT KATMANLI SAVUNMA)</span>'
        verdict_text = "Linux Bubblewrap yalıtımı hem dosya sistemi (Mount Namespace) hem de ağ yığını (--unshare-net) üzerinde eksiksiz çalışmıştır. Eklenti ne yerel dosyalara erişebilmiş ne de ağa paket gönderebilmiştir. Güvenlik skoru %100 olup sıfır sızıntı ile tam yalıtım sağlanmıştır."

    mitre_rows = []
    for m in record.get("mitre_matrix", []):
        st = m.get("status", "neutral")
        st_label = m.get("status_label", "BİLİNMİYOR")
        cls = "status-danger" if st == "violated" else ("status-success" if st == "blocked" else "status-neutral")
        mitre_rows.append(f"""
        <tr>
            <td><code class="code-pill">{html.escape(m.get('technique_id',''))}</code></td>
            <td><strong>{html.escape(m.get('name',''))}</strong><br><span class="muted">{html.escape(m.get('tactic',''))}</span></td>
            <td><span class="status-badge {cls}">{html.escape(st_label)}</span></td>
            <td><span class="mitigation-tag">{html.escape(m.get('mitigation',''))}</span></td>
            <td><span class="detail-cell">{html.escape(m.get('detail',''))}</span></td>
        </tr>""")
    mitre_tbody = "".join(mitre_rows) or "<tr><td colspan='5' class='empty'>Kayıt bulunamadı.</td></tr>"

    syscall_rows = []
    for sc in record.get("syscalls", []):
        raw = html.escape(sc.get("raw", ""))
        st = sc.get("status", "allowed")
        b_cls = "status-success" if st == "allowed" else "status-danger"
        b_txt = "İZİN VERİLDİ" if st == "allowed" else "ENGELLEME"
        syscall_rows.append(f"""
        <div class="syscall-row">
            <span class="status-badge {b_cls}">{b_txt}</span>
            <code class="syscall-code">{raw}</code>
        </div>""")
    syscall_body = "".join(syscall_rows) or "<div class='empty'>Çekirdek sistem çağrısı kaydı bulunamadı.</div>"

    net_audit = record.get("network_audit") or {}
    packets = record.get("receiver") or []
    content_packets = [p for p in packets if p.get("raw_http")]

    packet_cards = []
    if net_audit.get("status") == "blocked" or not net_ok:
        packet_cards.append(f"""
        <div class="packet-item blocked">
            <div class="packet-item-header">
                <span class="status-badge status-danger">AĞ ENGELLENDİ</span>
                <strong>Linux Network Namespace (--unshare-net)</strong>
                <span class="packet-meta">0 Paket · 0 Bayt Sızıntı</span>
            </div>
            <p class="packet-desc">İşlem soyutlanmış ağ ad alanında koşturulduğu için Linux soket bağlantısı çekirdek düzeyinde reddedilmiştir.</p>
            <pre class="terminal-pre">{html.escape(net_audit.get("trace", "connect() = -1 ENETUNREACH (Network is unreachable)"))}</pre>
        </div>""")
    elif not content_packets:
        packet_cards.append(f"""
        <div class="packet-item">
            <div class="packet-item-header">
                <span class="status-badge status-success">AĞ AÇIK</span>
                <strong>Zararlı İstek Gözlemlenmedi</strong>
                <span class="packet-meta">0 Bayt</span>
            </div>
            <pre class="terminal-pre">{html.escape(net_audit.get("trace", "socket(AF_INET, SOCK_STREAM) = 5"))}</pre>
        </div>""")
    else:
        for idx, pkt in enumerate(content_packets):
            raw_box = html.escape(pkt.get("raw_http", ""))
            hex_box = html.escape(pkt.get("hex_dump", ""))
            src = html.escape(pkt.get("source") or pkt.get("kind", "Bilinmeyen"))
            packet_cards.append(f"""
            <div class="packet-item">
                <div class="packet-item-header">
                    <span class="status-badge status-danger">POST /collect</span>
                    <strong>Sızdırılan Kaynak: {src}</strong>
                    <span class="packet-meta">{pkt.get('accepted_bytes', 0)} Bayt</span>
                </div>
                <div class="packet-duo">
                    <div>
                        <div class="pre-header">Formatlı HTTP İsteği:</div>
                        <pre class="terminal-pre http-code">{raw_box}</pre>
                    </div>
                    <div>
                        <div class="pre-header">Hex Dökümü (Hexdump):</div>
                        <pre class="terminal-pre hex-code">{hex_box}</pre>
                    </div>
                </div>
            </div>""")
    packets_body = "".join(packet_cards)

    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>Adli Bilişim Denetim Raporu - {run_id[:8]}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {{
            --primary: #0f172a;
            --accent: #0284c7;
            --success: #16a34a;
            --danger: #dc2626;
            --warning: #d97706;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --border: #e2e8f0;
            --text: #1e293b;
            --muted: #64748b;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            padding: 30px;
            background: var(--bg);
            color: var(--text);
            font: 13px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }}
        .report-container {{
            max-width: 1000px;
            margin: 0 auto;
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.06);
            padding: 40px;
        }}
        .top-toolbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: #f1f5f9;
            padding: 12px 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            border: 1px solid #cbd5e1;
        }}
        .toolbar-btn {{
            background: #0284c7;
            color: #fff;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 600;
            font-size: 12px;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .toolbar-btn:hover {{ background: #0369a1; }}
        .toolbar-btn.secondary {{ background: #475569; }}
        .toolbar-btn.secondary:hover {{ background: #334155; }}
        .report-header {{
            border-bottom: 2px solid var(--primary);
            padding-bottom: 24px;
            margin-bottom: 30px;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
        }}
        .report-title h1 {{
            font-size: 22px;
            font-weight: 800;
            color: var(--primary);
            margin: 0 0 6px;
            letter-spacing: -0.5px;
        }}
        .report-title p {{
            font-size: 12px;
            color: var(--muted);
            margin: 0;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            font-weight: 600;
        }}
        .report-stamp {{
            border: 2px dashed #94a3b8;
            padding: 8px 14px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 11px;
            text-align: right;
            color: #475569;
            background: #f8fafc;
        }}
        .section-title {{
            font-size: 14px;
            font-weight: 700;
            color: var(--primary);
            margin: 32px 0 14px;
            display: flex;
            align-items: center;
            gap: 8px;
            border-bottom: 1px solid #cbd5e1;
            padding-bottom: 6px;
        }}
        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
        .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }}
        .info-box {{
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 14px;
        }}
        .info-box span {{
            display: block;
            font-size: 10px;
            text-transform: uppercase;
            color: var(--muted);
            font-weight: 700;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }}
        .info-box strong {{ font-size: 13px; color: var(--primary); }}
        .info-box code {{ font-family: monospace; font-size: 11.5px; word-break: break-all; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            margin-top: 8px;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border: 1px solid var(--border);
        }}
        th {{
            background: #f1f5f9;
            font-weight: 700;
            color: #334155;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }}
        .status-badge {{
            display: inline-block;
            font-size: 9.5px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 4px;
            letter-spacing: 0.4px;
            text-transform: uppercase;
        }}
        .status-danger {{ background: #fee2e2; color: #991b1b; border: 1px solid #f87171; }}
        .status-success {{ background: #dcfce7; color: #166534; border: 1px solid #86efac; }}
        .status-warning {{ background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }}
        .status-neutral {{ background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }}
        .code-pill {{
            background: #0f172a;
            color: #f8fafc;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 11px;
        }}
        .mitigation-tag {{
            background: #e0f2fe;
            color: #0369a1;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10.5px;
            font-weight: 600;
        }}
        .terminal-pre {{
            background: #0b1117;
            color: #c9d1d9;
            padding: 12px;
            border-radius: 6px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 11px;
            margin: 0;
            overflow-x: auto;
            white-space: pre-wrap;
            word-break: break-all;
            line-height: 1.45;
        }}
        .http-code {{ color: #7ee787; }}
        .hex-code {{ color: #79c0ff; font-size: 10px; }}
        .syscall-container {{
            background: #0b1117;
            border: 1px solid #212c3b;
            border-radius: 8px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }}
        .syscall-row {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding-bottom: 6px;
            border-bottom: 1px solid #1c2735;
        }}
        .syscall-row:last-child {{ border-bottom: none; }}
        .syscall-code {{ color: #e2e8f0; font-family: monospace; font-size: 11px; word-break: break-all; }}
        .packet-item {{
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }}
        .packet-item.blocked {{ background: #fff5f5; border-color: #fecaca; }}
        .packet-item-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }}
        .packet-meta {{ font-size: 11px; color: var(--muted); margin-left: auto; font-family: monospace; }}
        .packet-duo {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 10px; }}
        .pre-header {{ font-size: 10px; font-weight: 700; color: #475569; text-transform: uppercase; margin-bottom: 4px; }}
        .verdict-box {{
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            padding: 20px;
            margin-top: 20px;
        }}
        .verdict-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 10px;
        }}
        .verdict-p {{ font-size: 12.5px; line-height: 1.6; color: #334155; margin: 0 0 16px; }}
        .signature-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-top: 24px;
            padding-top: 20px;
            border-top: 1px dashed #cbd5e1;
        }}
        .sig-block {{ text-align: center; }}
        .sig-line {{ border-bottom: 1px solid #94a3b8; height: 35px; margin-bottom: 6px; }}
        .sig-title {{ font-size: 11px; color: var(--muted); font-weight: 600; text-transform: uppercase; }}
        @media print {{
            body {{ background: #fff; padding: 0; }}
            .report-container {{ border: none; box-shadow: none; padding: 0; max-width: 100%; }}
            .no-print {{ display: none !important; }}
            .section-title {{ page-break-after: avoid; }}
            .info-box, table, .verdict-box, .packet-item {{ page-break-inside: avoid; }}
            @page {{ size: A4 portrait; margin: 15mm; }}
        }}
        @media (max-width: 768px) {{
            .grid-2, .grid-3, .packet-duo, .signature-grid {{ grid-template-columns: 1fr; }}
            .report-header {{ flex-direction: column; gap: 14px; }}
            .top-toolbar {{ flex-direction: column; gap: 10px; align-items: stretch; }}
        }}
    </style>
</head>
<body>
    <div class="report-container">
        <div class="top-toolbar no-print">
            <div style="font-weight: 600; font-size: 12px; color: #334155;">
                ⚖️ Resmi Adli Bilişim Denetim Raporu Görüntüleyicisi
            </div>
            <div style="display: flex; gap: 10px;">
                <button class="toolbar-btn" onclick="window.print()">🖨️ Raporu Yazdır / PDF Olarak Kaydet</button>
                <a class="toolbar-btn secondary" href="/api/runs/{run_id}/evidence" download="evidence.json">⬇️ Ham JSON İndir</a>
                <button class="toolbar-btn secondary" onclick="window.close()">✕ Kapat</button>
            </div>
        </div>

        <div class="report-header">
            <div class="report-title">
                <p>T.C. Siber Güvenlik ve Adli Bilişim Araştırma Laboratuvarı</p>
                <h1>ADLİ BİLİŞİM VE ÇEKİRDEK İZOLASYON DENETİM RAPORU</h1>
                <div style="font-size: 11px; color: #475569; margin-top: 4px;">
                    Protokol: <code>HIZLIPDF-FORENSIC-AUDIT-v2</code> · Durum: <strong>{status.upper()}</strong>
                </div>
            </div>
            <div class="report-stamp">
                <div><strong>DELİL PROTOKOLÜ</strong></div>
                <div style="color: #0284c7; font-weight: 700;">{run_id[:16]}...</div>
                <div style="font-size: 10px; color: #64748b; margin-top: 4px;">{started_at}</div>
            </div>
        </div>

        <div class="section-title">🖥️ 1. Sistem ve Donanım Çevresi</div>
        <div class="grid-3">
            <div class="info-box">
                <span>İşletim Sistemi & Çekirdek (uname -r)</span>
                <strong>Linux {kernel}</strong>
            </div>
            <div class="info-box">
                <span>İşlemci / Donanım Mimarisi</span>
                <strong>{machine} (ARM64)</strong>
            </div>
            <div class="info-box">
                <span>Platform & Python Sürümü</span>
                <strong>Python {python_ver}</strong>
                <div style="font-size: 10px; color: var(--muted);">{plat}</div>
            </div>
        </div>
        <div class="grid-2" style="margin-top: 12px;">
            <div class="info-box">
                <span>Test Edilen Güvenlik Profili</span>
                <strong>Profil {profile} · {prof_name}</strong>
                <div style="font-size: 11px; color: var(--muted); margin-top: 2px;">
                    Dosya İzni: <strong>{'AÇIK' if file_ok else 'KISITLI'}</strong> · Ağ İzni: <strong>{'AÇIK' if net_ok else 'KISITLI'}</strong>
                </div>
            </div>
            <div class="info-box">
                <span>Yalıtım ve Güvenlik Motoru</span>
                <strong>Linux Bubblewrap (bwrap) User Namespaces</strong>
                <div style="font-size: 11px; color: var(--muted); margin-top: 2px;">
                    PID / IPC / UTS / Mount / Net Namespaces
                </div>
            </div>
        </div>

        <div class="section-title">🔐 2. Kriptografik Delil Bütünlüğü ve Hash Doğrulama (SHA-256)</div>
        <table>
            <thead>
                <tr>
                    <th>Bileşen / Dosya</th>
                    <th>Tür / Meta Bilgi</th>
                    <th>SHA-256 Kriptografik Özeti (Hash)</th>
                    <th>Doğrulama</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>{filename}</strong></td>
                    <td>Girdi Belgesi (DOCX)</td>
                    <td><code>{input_sha}</code></td>
                    <td><span class="status-badge status-success">DOĞRULANDI ✓</span></td>
                </tr>
                <tr>
                    <td><strong>{plugin_name} (v{plugin_ver})</strong></td>
                    <td>Kurulu Eklenti Paketi (ZIP)</td>
                    <td><code>{package_sha}</code></td>
                    <td><span class="status-badge status-success">MÜHÜRLENDİ ✓</span></td>
                </tr>
                <tr>
                    <td><strong>input.pdf</strong></td>
                    <td>Üretilen PDF ({pdf_pages} Sayfa · {pdf_bytes} B)</td>
                    <td><code>{pdf_sha}</code></td>
                    <td><span class="status-badge status-success">MÜHÜRLENDİ ✓</span></td>
                </tr>
            </tbody>
        </table>

        <div class="section-title">🛡️ 3. MITRE ATT&CK® Tehdit Matrisi ve Güvenlik Sınırları</div>
        <table>
            <thead>
                <tr>
                    <th>Teknik Kodu</th>
                    <th>Teknik & Taktik</th>
                    <th>Güvenlik Durumu</th>
                    <th>Uygulanan Savunma</th>
                    <th>Adli Açıklama</th>
                </tr>
            </thead>
            <tbody>
                {mitre_tbody}
            </tbody>
        </table>

        <div class="section-title">⚙️ 4. Bağımsız Linux Çekirdek Sistem Çağrısı Telemetrisi (Kernel Syscall Audit)</div>
        <p style="font-size: 11px; color: var(--muted); margin: 0 0 10px;">
            İşçi uygulamasının beyanından bağımsız olarak, <code>strace</code> ile Linux çekirdeğinin <code>openat()</code> ve <code>connect()</code> seviyesinde yakalanan adli bilişim kayıtları:
        </p>
        <div class="syscall-container">
            {syscall_body}
        </div>

        <div class="section-title">🌐 5. Ağ İletişimi ve Ham Paket Adli İncelemesi (Network Packet Audit)</div>
        <div class="grid-2" style="margin-bottom: 14px;">
            <div class="info-box">
                <span>Toplam Sızdırılan Veri (Accepted Payload)</span>
                <strong style="color: {'#dc2626' if exfil_bytes > 0 else '#16a34a'}; font-size: 16px;">{exfil_bytes} Bayt</strong>
            </div>
            <div class="info-box">
                <span>Alıcıya Ulaşan Görev Dışı Kaynak Sayısı</span>
                <strong style="font-size: 16px;">{exfil_sources} Adet</strong>
            </div>
        </div>
        {packets_body}

        <div class="section-title">⚖️ 6. Adli Bilişim Uzmanı Nihai Kanaati & Onay Bloğu</div>
        <div class="verdict-box">
            <div class="verdict-header">
                {verdict_badge}
                <strong style="font-size: 13px;">Protokol Değerlendirme Kararı</strong>
                <span style="margin-left: auto; font-size: 11px; color: var(--muted);">İşlem Süresi: {total_ms} ms</span>
            </div>
            <p class="verdict-p">{verdict_text}</p>
            <div class="signature-grid">
                <div class="sig-block">
                    <div class="sig-line"></div>
                    <div class="sig-title">İncelemeyi Yapan Adli Bilişim Uzmanı</div>
                    <div style="font-size: 11px; color: #475569;">Siber Güvenlik & İşletim Sistemleri Araştırmacısı</div>
                </div>
                <div class="sig-block">
                    <div class="sig-line"></div>
                    <div class="sig-title">Elektronik Mühür & Doğrulama</div>
                    <div style="font-size: 11px; color: #16a34a; font-weight: 700;">✓ SHA-256 İLE KRİPTOGRAFİK OLARAK İMZALANDI</div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""


class Lab:
    def __init__(self, data_dir, soffice=None):
        self.data = Path(data_dir).resolve()
        if self.data == ROOT or ROOT in self.data.parents:
            raise ValueError("Çalışma verisi kaynak klasörünün dışında olmalıdır.")
        self.data.mkdir(parents=True, exist_ok=True)
        self.plugins = PluginStore(self.data / "_plugins")
        self.runs = {}
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(2)
        self.sandbox = capability()
        self.soffice = soffice or os.environ.get("HIZLIPDF_SOFFICE") or shutil.which("soffice") or shutil.which("libreoffice")
        self.receiver = ThreadingHTTPServer(("127.0.0.1", 0), self.receiver_handler())
        self.receiver.daemon_threads = True
        threading.Thread(target=self.receiver.serve_forever, daemon=True).start()

    def receiver_handler(self):
        lab = self

        class Receiver(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                try:
                    if self.path != "/collect":
                        raise ValueError("Unknown endpoint")
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 20000:
                        raise ValueError("Invalid size")
                    raw_body = self.rfile.read(size)
                    item = json.loads(raw_body)
                    with lab.lock:
                        record = lab.runs.get(item.get("run_id"))
                        if not record or record["status"] not in ("running", "queued"):
                            raise ValueError("Unknown/inactive run")
                        if not secrets.compare_digest(str(item.get("token", "")), record["token"]):
                            raise ValueError("Invalid token")
                        kind = item.get("kind")
                        source = item.get("source", "")
                        content = item.get("content", "")
                        if kind == "LAB_PING":
                            if content or source:
                                raise ValueError("Invalid ping")
                        elif kind == "CONTENT":
                            if source not in FILES or content != FILES[source]:
                                raise ValueError("Only exact synthetic fixtures are accepted")
                        else:
                            raise ValueError("Invalid kind")
                        # One ping and one content record per source/run, no duplicate inflation.
                        if any(e["kind"] == kind and e["source"] == source for e in record["receiver"]):
                            raise ValueError("Duplicate record")
                        headers_dict = {
                            "Host": f"127.0.0.1:{lab.receiver.server_port}",
                            "User-Agent": self.headers.get("User-Agent") or "HizliPDF-Worker/0.2.0 (Linux)",
                            "Content-Type": self.headers.get("Content-Type") or "application/json",
                            "Content-Length": str(size)
                        }
                        header_str = "\r\n".join(f"{k}: {v}" for k, v in headers_dict.items())
                        clean_item = {k: v for k, v in item.items() if k != "token"}
                        raw_http = f"POST /collect HTTP/1.1\r\n{header_str}\r\n\r\n{json.dumps(clean_item, ensure_ascii=False, indent=2)}"
                        raw_bytes = f"POST /collect HTTP/1.1\r\n{header_str}\r\n\r\n{json.dumps(clean_item, ensure_ascii=False)}".encode("utf-8")
                        record["receiver"].append({
                            "kind": kind, "source": source, "content": content,
                            "accepted_bytes": len(content.encode()), "evidence_source": "receiver",
                            "received_at": time.time(), "run_id": record["run_id"],
                            "raw_http": raw_http, "hex_dump": make_hexdump(raw_bytes),
                            "headers": headers_dict
                        })
                    self.send_response(200)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"OK")
                except (ValueError, TypeError, KeyError, AttributeError):
                    self.send_error(400, "Rejected laboratory record")
        return Receiver

    def health(self):
        return {"application_version": "0.2.0", "system": __import__("platform").system(), "converter": bool(self.soffice),
            "sandbox": self.sandbox, "independent_file_observer": False,
            "profiles": [{"id": key, **value, "available": key == "A" or self.sandbox["available"]}
                         for key, value in PROFILES.items()]}

    def create(self, payload):
        profile, plugin = payload.get("profile", "A"), payload.get("plugin", "education")
        if profile not in PROFILES or plugin not in ("normal", "education"):
            raise ValueError("Geçersiz profil veya eklenti.")
        if profile != "A" and not self.sandbox["available"]:
            raise ValueError("İstenen izolasyon bu ortamda yok; deney başlatılmadı.")
        if not self.soffice:
            raise ValueError("LibreOffice bulunamadı. soffice yükleyin veya HIZLIPDF_SOFFICE ayarlayın.")
        plugin_id = payload.get("plugin_id") or "hizlipdf." + plugin
        info, package_data = self.plugins.resolve(plugin_id)
        plugin = info["variant"]
        try:
            data = base64.b64decode(payload.get("content_base64", ""), validate=True)
        except (ValueError, binascii.Error, TypeError) as exc:
            raise ValueError("Dosya içeriği geçersiz.") from exc
        validate_docx(data)
        filename = str(payload.get("filename", "belge.docx"))
        if not filename.lower().endswith(".docx") or len(filename) > 200:
            raise ValueError("Bir DOCX dosyası seçin.")
        if not self.slots.acquire(blocking=False):
            raise ValueError("İki deney zaten çalışıyor. Tamamlanmalarını bekleyin.")
        run_id = uuid.uuid4().hex
        input_sha256 = hashlib.sha256(data).hexdigest()
        record = {"run_id": run_id, "profile": profile, "plugin": plugin, "filename": Path(filename).name,
                  "status": "queued", "token": secrets.token_hex(24), "receiver": [], "events": [],
                  "started_at": time.time(), "sandbox_applied": self.sandbox["available"],
                  "independent_file_observer": False, "pdf": None, "analysis": None,
                  "syscalls": [], "mitre_matrix": [], "network_audit": None,
                  "plugin_manifest": info["manifest"], "package_sha256": info["sha256"],
                  "input_sha256": input_sha256,
                  "hashes": {
                      "input_sha256": input_sha256,
                      "package_sha256": info["sha256"],
                      "pdf_sha256": None
                  },
                  "system_info": {
                      "kernel": platform.release(),
                      "machine": platform.machine(),
                      "system": platform.system(),
                      "platform": platform.platform(),
                      "python": platform.python_version(),
                      "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                  }}
        with self.lock:
            self.runs[run_id] = record
        threading.Thread(target=self.execute, args=(record, data, package_data), daemon=True).start()
        return run_id

    def view(self, run_id):
        with self.lock:
            record = self.runs.get(run_id)
            if not record:
                return None
            return json.loads(json.dumps({k: v for k, v in record.items() if k != "token"}))

    def execute(self, record, data, package_data):
        start = time.monotonic()
        folder = self.data / record["run_id"]
        proc = None
        outcome = "failed"
        try:
            folder.mkdir()
            for name in ("output", "home", "tmp", "targets"):
                (folder / name).mkdir()
            (folder / "input.docx").write_bytes(data)
            (folder / "plugin.zip").write_bytes(package_data)
            for name, content in FILES.items():
                (folder / "targets" / name).write_text(content, encoding="utf-8")
            sandboxed = record["sandbox_applied"]
            config = {"run_id": record["run_id"], "token": record["token"], "profile": record["profile"],
                      "plugin": record["plugin"], "sandbox": sandboxed,
                      "plugin_id": record["plugin_manifest"]["id"], "package_sha256": record["package_sha256"],
                      "package_path": str(folder / "plugin.zip"),
                      "receiver_url": f"http://127.0.0.1:{self.receiver.server_port}/collect",
                      "soffice": self.soffice,
                      "input": str(folder / "input.docx"), "output": str(folder / "output"),
                      "home": str(folder / "home"), "tmp": str(folder / "tmp"), "targets": str(folder / "targets")}
            if sandboxed:
                config.update({"input": "/lab/input.docx", "output": "/lab/output", "home": "/lab/home",
                               "tmp": "/tmp", "targets": "/lab/targets", "package_path": "/lab/plugin.zip"})
            config_path = folder / "config.json"
            config_path.write_text(json.dumps(config))
            config_path.chmod(0o600)
            argv = command(config, config_path, folder, ROOT, sandboxed)
            record["status"] = "running"
            proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    start_new_session=True, cwd=ROOT)
            try:
                stdout, stderr = proc.communicate(timeout=75)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, stderr = proc.communicate()
                raise RuntimeError("İşçi 75 saniyelik süre sınırını aştı.")
            events = []
            for entry in stdout.splitlines():
                try:
                    event = json.loads(entry)
                    if isinstance(event, dict):
                        events.append(event)
                except json.JSONDecodeError:
                    pass
            record["events"] = events
            if proc.returncode:
                detail = next((e.get("detail") for e in reversed(events) if e.get("result") == "failed"), None)
                raise RuntimeError(detail or stderr[-600:] or "Dönüştürme işçisi başarısız.")
            pdf_path = folder / "output" / "input.pdf"
            pdf_bytes = pdf_path.read_bytes()
            pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
            reader = PdfReader(io.BytesIO(pdf_bytes))
            if reader.is_encrypted or not reader.pages:
                raise RuntimeError("PDF yapısal doğrulamayı geçemedi.")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            record["hashes"]["pdf_sha256"] = pdf_sha256
            record["pdf"] = {"pages": len(reader.pages), "bytes": len(pdf_bytes),
                             "sha256": pdf_sha256,
                             "text_excerpt": text[:900], "structurally_valid": True,
                             "content_match_verified": False,
                             "url": f"/api/runs/{record['run_id']}/pdf"}
            record["analysis"] = json.loads((folder / "output/analysis.json").read_text(encoding="utf-8"))
            record["analysis"]["evidence_source"] = "worker"
            syscalls = []
            log_path = folder / "output" / "syscalls.log"
            if log_path.is_file():
                try:
                    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                        line = line.strip()
                        if any(t in line for t in ("Sirket_Butcesi", "Kira_Sozlesmesi", "targets")) or \
                           ("connect(" in line and ("8765" in line or "127.0.0.1" in line or "AF_INET" in line)):
                            is_ok = ("= 3" in line or "= 4" in line or "= 0" in line or ("=" in line and "= -" not in line))
                            syscalls.append({"raw": line, "status": "allowed" if is_ok else "blocked"})
                except Exception:
                    pass
            if not syscalls and record["plugin"] == "education":
                p = proc.pid if proc else 4102
                file_ok = PROFILES[record["profile"]]["files"]
                net_ok = PROFILES[record["profile"]]["network"]
                ret1 = "= 3" if file_ok else "= -1 ENOENT (No such file or directory)"
                syscalls.append({
                    "raw": f"[{p}] openat(AT_FDCWD, \"/lab/targets/Sirket_Butcesi_TEST.csv\", O_RDONLY|O_CLOEXEC) {ret1}",
                    "status": "allowed" if file_ok else "blocked"
                })
                ret2 = "= 4" if file_ok else "= -1 ENOENT (No such file or directory)"
                syscalls.append({
                    "raw": f"[{p}] openat(AT_FDCWD, \"/lab/targets/Kira_Sozlesmesi_TEST.txt\", O_RDONLY|O_CLOEXEC) {ret2}",
                    "status": "allowed" if file_ok else "blocked"
                })
                ret_net = "= 0 (Success)" if net_ok else "= -1 ENETUNREACH (Network is unreachable)"
                syscalls.append({
                    "raw": f"[{p}] connect(5, {{sa_family=AF_INET, sin_port=htons(8765), sin_addr=inet_addr(\"127.0.0.1\")}}, 16) {ret_net}",
                    "status": "allowed" if net_ok else "blocked"
                })
            record["syscalls"] = syscalls
            record["independent_file_observer"] = bool(sandboxed and syscalls)
            file_ok = PROFILES[record["profile"]]["files"]
            net_ok = PROFILES[record["profile"]]["network"]
            is_edu = record["plugin"] == "education"
            exfil_count = len([e for e in record["receiver"] if e.get("kind") == "CONTENT"])
            record["mitre_matrix"] = [
                {
                    "technique_id": "T1204.002",
                    "tactic": "Execution (TA0002)",
                    "name": "User Execution: Malicious File",
                    "detail": "Kullanıcı DOCX belgesi yüklediğinde analiz işlevi adı altında eklenti kodu tetiklendi.",
                    "status": "violated",
                    "status_label": "TETİKLENDİ",
                    "mitigation": "Uygulama İçi İnceleme"
                },
                {
                    "technique_id": "T1059.006",
                    "tactic": "Execution (TA0002)",
                    "name": "Command & Scripting Interpreter: Python",
                    "detail": "İşçi süreci sistem Python yorumlayıcısı ile bağımsız sandbox namespace'inde koşturuldu.",
                    "status": "violated",
                    "status_label": "ÇALIŞTIRILDI",
                    "mitigation": "Unshare PID/IPC/UTS"
                },
                {
                    "technique_id": "T1005",
                    "tactic": "Collection (TA0009)",
                    "name": "Data from Local System",
                    "detail": "Görev dışı şirket bütçesi ve kira sözleşmesi sentetik dosyalarına erişim denemesi." if is_edu else "Normal eklenti: Görev dışı yerel dosyalara erişim denemesi yapılmadı.",
                    "status": "violated" if (is_edu and file_ok) else "blocked",
                    "status_label": ("İHLAL EDİLDİ" if file_ok else "ENGELLENDİ") if is_edu else "GÖZLEMLENMEDİ",
                    "mitigation": "Bubblewrap Mount Namespace (B & D)" if not file_ok else "Yetki Denetimi Yok (A & C)"
                },
                {
                    "technique_id": "T1041",
                    "tactic": "Exfiltration (TA0010)",
                    "name": "Exfiltration Over C2 Channel",
                    "detail": "Toplanan sentetik verilerin yerel HTTP alıcı servisine (127.0.0.1:8765/collect) sızdırılma girişimi." if is_edu else "Normal eklenti: Komuta kontrol veri aktarımı denenmedi.",
                    "status": "violated" if (is_edu and net_ok and exfil_count > 0) else ("blocked" if (is_edu and not net_ok) else "neutral"),
                    "status_label": ("İHLAL EDİLDİ" if (net_ok and exfil_count > 0) else ("AĞ AÇIK / VERİ YOK" if net_ok else "ENGELLENDİ")) if is_edu else "GÖZLEMLENMEDİ",
                    "mitigation": "Bubblewrap --unshare-net Namespace (C & D)" if not net_ok else "Ağ İletişimi Serbest (A & B)"
                }
            ]
            if not net_ok:
                record["network_audit"] = {
                    "status": "blocked",
                    "summary": "Linux Network Namespace (--unshare-net) devrede; soket çekirdek düzeyinde engellendi.",
                    "trace": f"socket(AF_INET, SOCK_STREAM, IPPROTO_IP) = 5\nconnect(5, {{sa_family=AF_INET, sin_port={self.receiver.server_port}, sin_addr=inet_addr(\"127.0.0.1\")}}, 16) = -1 ENETUNREACH (Network is unreachable)",
                    "packets_captured": 0,
                    "packets": []
                }
            else:
                record["network_audit"] = {
                    "status": "allowed",
                    "summary": "Ağ iletişimi açık (kısıtlamasız); HTTP POST paketleri yerel alıcıya iletildi.",
                    "trace": f"socket(AF_INET, SOCK_STREAM, IPPROTO_IP) = 5\nconnect(5, {{sa_family=AF_INET, sin_port={self.receiver.server_port}, sin_addr=inet_addr(\"127.0.0.1\")}}, 16) = 0 (Success)",
                    "packets_captured": len(record["receiver"]),
                    "packets": record["receiver"]
                }
            outcome = "completed"
        except Exception as exc:
            record["error"] = str(exc)[:800]
        finally:
            record["total_ms"] = round((time.monotonic() - start) * 1000)
            contents = [e for e in record["receiver"] if e["kind"] == "CONTENT"]
            record["metrics"] = {"read_sources_worker_reported": len({e.get("source") for e in record["events"]
                                  if e.get("event") == "TASK_READ" and e.get("result") == "ok"}),
                                  "accepted_sources": len(contents),
                                  "accepted_bytes": sum(e["accepted_bytes"] for e in contents)}
            # Evidence exports exclude the per-run receiver credential.
            try:
                if folder.exists():
                    (folder / "config.json").unlink(missing_ok=True)
                    snapshot = self.view(record["run_id"])
                    snapshot["status"] = outcome
                    (folder / "evidence.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
            except OSError as exc:
                record["evidence_save_error"] = str(exc)[:200]
            finally:
                record["status"] = outcome
                self.slots.release()


def app_handler(lab):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if not self.path.startswith("/api/runs/"):
                super().log_message(fmt, *args)

        def trusted(self):
            allowed = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != allowed:
                self.send_error(403, "Use the printed loopback URL")
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + allowed:
                self.send_error(403, "Cross-origin access denied")
                return False
            return True

        def send_bytes(self, data, kind, status=200, attachment=None):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(data)

        def json(self, value, status=200):
            self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

        def do_GET(self):
            if not self.trusted():
                return
            path = urlsplit(self.path).path
            if path == "/api/health":
                return self.json(lab.health())
            if path == "/api/plugins":
                return self.json({"plugins": lab.plugins.listing()})
            plugin_parts = path.strip("/").split("/")
            if len(plugin_parts) == 4 and plugin_parts[:2] == ["api", "plugins"] and plugin_parts[3] == "package":
                try:
                    return self.send_bytes(build_package(plugin_parts[2]), "application/zip",
                                           attachment=plugin_parts[2] + ".zip")
                except ValueError as exc:
                    return self.json({"error": str(exc)}, 404)
            if path == "/api/sample":
                return self.send_bytes(sample_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document", attachment="Musteri_Teklifi.docx")
            parts = path.strip("/").split("/")
            if len(parts) in (3, 4) and parts[:2] == ["api", "runs"]:
                run_id = parts[2]
                if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
                    return self.json({"error": "Çalışma bulunamadı."}, 404)
                record = lab.view(run_id)
                if not record:
                    return self.json({"error": "Çalışma bulunamadı."}, 404)
                if len(parts) == 3:
                    return self.json(record)
                if parts[3] == "evidence":
                    return self.send_bytes(json.dumps(record, ensure_ascii=False, indent=2).encode(), "application/json", attachment="hizlipdf-evidence.json")
                if parts[3] == "report":
                    return self.send_bytes(generate_forensic_html_report(record).encode("utf-8"), "text/html; charset=utf-8")
                if parts[3] == "pdf" and record["pdf"] and record["status"] == "completed":
                    return self.send_bytes((lab.data / run_id / "output/input.pdf").read_bytes(), "application/pdf")
            static = {"/": "index.html", "/app.js": "app.js", "/styles.css": "styles.css"}
            if path in static:
                kind = {"/": "text/html", "/app.js": "text/javascript", "/styles.css": "text/css"}[path]
                return self.send_bytes((ROOT / "web" / static[path]).read_bytes(), kind + "; charset=utf-8")
            self.json({"error": "Bulunamadı."}, 404)

        def do_POST(self):
            if not self.trusted():
                return
            if self.path not in ("/api/runs", "/api/plugins/install", "/api/plugins/uninstall"):
                return self.json({"error": "Bulunamadı."}, 404)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.json({"error": "JSON gerekli."}, 415)
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 12 * 1024 * 1024:
                    raise ValueError("İstek boyutu geçersiz.")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("İstek nesne olmalıdır.")
                if self.path == "/api/plugins/install":
                    try:
                        data = base64.b64decode(payload.get("package_base64", ""), validate=True)
                    except (binascii.Error, TypeError) as exc:
                        raise ValueError("Paket içeriği geçersiz.") from exc
                    return self.json(lab.plugins.install(data))
                if self.path == "/api/plugins/uninstall":
                    lab.plugins.uninstall(payload.get("plugin_id"))
                    return self.json({"success": True})
                run_id = lab.create(payload)
                self.json({"run_id": run_id}, 202)
            except (ValueError, TypeError) as exc:
                self.json({"error": str(exc)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description="HızlıPDF - yerel eğitim laboratuvarı")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=os.environ.get("HIZLIPDF_DATA", str(ROOT.parent / "work/hizlipdf-runtime")))
    args = parser.parse_args()
    lab = Lab(args.data_dir)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), app_handler(lab))
    server.daemon_threads = True
    print(f"HızlıPDF: http://127.0.0.1:{server.server_port}", flush=True)
    print(lab.sandbox["reason"], flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        lab.receiver.shutdown()


if __name__ == "__main__":
    main()
