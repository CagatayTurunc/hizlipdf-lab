"""Analyze body paragraphs, including table cells; no headers/footers or external fetches."""
import re
import xml.etree.ElementTree as ET
import zipfile

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def analyze_docx(path):
    with zipfile.ZipFile(path) as archive:
        member = archive.getinfo("word/document.xml")
        if member.file_size > 32 * 1024 * 1024:
            raise ValueError("Belge analiz boyutu sınırını aşıyor.")
        xml = archive.read(member)
    if b"<!DOCTYPE" in xml.upper():
        raise ValueError("DOCTYPE içeren belge desteklenmiyor.")
    root = ET.fromstring(xml)
    body = root.find("w:body", NS)
    if body is None:
        raise ValueError("Belge gövdesi bulunamadı.")
    texts, headings = [], []
    for paragraph in body.iter("{" + NS["w"] + "}p"):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", NS)).strip()
        if not text:
            continue
        texts.append(text)
        style = paragraph.find("w:pPr/w:pStyle", NS)
        style_name = style.get("{" + NS["w"] + "}val", "") if style is not None else ""
        if re.fullmatch(r"Heading[1-9]|Title|Subtitle", style_name, flags=re.I):
            headings.append(text[:300])
    return {"word_count": len(re.findall(r"\b\w+(?:['’\-]\w+)*\b", "\n".join(texts))),
            "paragraph_count": len(texts), "table_count": len(body.findall(".//w:tbl", NS)),
            "headings": headings[:100], "heading_count": len(headings),
            "scope": "Belge gövdesi ve tablo hücreleri; boş paragraflar hariç. Başlıklar Title/Subtitle/Heading1-9 stillerinden alınır.",
            "word_method": "Unicode sözcük ve sayı grupları; Word uygulamasının sayacıyla birebir eşitlik iddiası yoktur."}
