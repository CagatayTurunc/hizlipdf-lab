"""Turn recorded lab events into narrowly scoped, evidence-based outcomes."""
import re

from fixtures import FILES

OPEN = re.compile(r'^openat\(AT_FDCWD, "/lab/targets/([^"/]+)", O_RDONLY(?:\|[A-Z_]+)*\)')
CONNECT = re.compile(
    r'^connect\(\d+, \{sa_family=AF_INET, sin_port=htons\((\d+)\), '
    r'sin_addr=inet_addr\("127\.0\.0\.1"\)\}, \d+\)'
)
RETURN = re.compile(r'^\s+=\s+(-?\d+)(?:\s+([A-Z][A-Z0-9_]+)\b|\s|$)')
FILE_ERRORS = {"ENOENT", "EACCES", "EPERM"}
NETWORK_ERRORS = {"ENETUNREACH", "EHOSTUNREACH", "ECONNREFUSED", "EACCES", "EPERM"}


def read_syscalls(path, port):
    """Read only completed calls for the lab fixtures and the current loopback receiver."""
    if path.is_symlink() or not path.is_file():
        return []
    calls = []
    pending = {}
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            for raw in stream:
                raw = raw.strip()
                prefix = re.match(r'^(?:\[pid\s+(\d+)\]|(\d+))\s+', raw)
                pid = (prefix.group(1) or prefix.group(2)) if prefix else None
                call = raw[prefix.end():] if prefix else raw
                if call.endswith("<unfinished ...>"):
                    pending[pid] = (call.removesuffix("<unfinished ...>").rstrip(), raw)
                    continue
                resumed = re.match(r'^<\.\.\. (openat|connect) resumed>\s*', call)
                if resumed:
                    earlier, earlier_raw = pending.pop(pid, ("", ""))
                    if not earlier.startswith(resumed.group(1) + "("):
                        continue
                    tail = call[resumed.end():]
                    call = earlier + (" " if tail.startswith("=") else "") + tail
                    raw = earlier_raw + "\n" + raw
                match = OPEN.match(call)
                if match and match.group(1) in FILES:
                    kind, source = "openat", match.group(1)
                else:
                    match = CONNECT.match(call)
                    if not match or match.group(1) != str(port):
                        continue
                    kind, source = "connect", f"127.0.0.1:{port}"
                result = RETURN.match(call[match.end():])
                if result:
                    code, error = int(result.group(1)), result.group(2)
                    status = "allowed" if code >= 0 else ("pending" if error == "EINPROGRESS" else "error")
                    calls.append({"raw": raw, "kind": kind, "source": source, "status": status, "errno": error})
    except OSError:
        return []
    return calls


def assess(record, completed):
    calls = record.get("syscalls") or []
    file_calls = [call for call in calls if call["kind"] == "openat"]
    net_calls = [call for call in calls if call["kind"] == "connect"]
    receiver = record.get("receiver") or []
    controls = record.get("receiver_health") or {}
    normal = record.get("plugin") == "normal" and any(
        event.get("event") == "EXTRA_ACTIONS" and event.get("result") == "not_attempted"
        for event in record.get("events", [])
    )

    opened = {call["source"] for call in file_calls if call["status"] == "allowed"}
    unavailable = {call["source"] for call in file_calls if call["errno"] in FILE_ERRORS} - opened
    file_status = "unverified"
    file_summary = "İki sentetik dosya için kesin bir açma sonucu yok."
    if opened == FILES.keys():
        file_status = "opened"
        file_summary = "İki sentetik dosya için başarılı openat() gözlemlendi."
    elif unavailable == FILES.keys():
        file_status = "unavailable"
        file_summary = "İki sentetik dosya için openat() başarısız oldu. Hata kodları sistem çağrısı kaydında."

    network_status = "unverified"
    network_summary = "Yerel alıcıya bağlantının sonucu doğrulanmadı."
    if receiver:
        network_status = "reachable"
        network_summary = "Yerel alıcı bu çalışmaya ait HTTP isteğini kabul etti."
    elif any(call["status"] == "allowed" for call in net_calls):
        network_status = "reachable"
        network_summary = "Yerel alıcıya başarılı connect() gözlemlendi. HTTP kabul kaydı yok."
    elif controls.get("before") and controls.get("after") and net_calls and all(
        call["errno"] in NETWORK_ERRORS for call in net_calls
    ):
        network_status = "unreachable"
        network_summary = "Alıcı deneyin öncesinde ve sonrasında yanıt verdi. İşçinin yerel alıcıya connect() çağrıları başarısız oldu."
    elif net_calls:
        network_summary = "Yerel alıcı için bağlantı kayıtları var. Bağlantı kısıtı doğrulanmadı."

    if normal and not file_calls and not net_calls and not receiver:
        file_status = network_status = "not_attempted"
        file_summary = network_summary = "Normal eklenti ek deney adımını çalıştırmadığını bildirdi."

    file_audit = {"status": file_status, "summary": file_summary,
                  "opened_sources": sorted(opened), "unavailable_sources": sorted(unavailable)}
    network_audit = {"status": network_status, "summary": network_summary,
                     "requests_accepted": len(receiver)}
    if not completed:
        verdict = {"status": "unverified", "label": "Doğrulanmadı",
                   "summary": "Çalışma tamamlanmadı. Mevcut gözlemler aşağıda yer alır."}
    elif normal and file_status == network_status == "not_attempted":
        verdict = {"status": "not_attempted", "label": "Denenmedi", "summary": file_summary}
    elif "unverified" in (file_status, network_status):
        verdict = {"status": "unverified", "label": "Doğrulanmadı",
                   "summary": f"{file_summary} {network_summary}"}
    else:
        verdict = {"status": "observed", "label": "Deney sonuçları gözlemlendi",
                   "summary": f"{file_summary} {network_summary}"}
    return file_audit, network_audit, verdict


def mitre_mapping(file_audit, network_audit, contents):
    file_status = file_audit["status"]
    net_status = network_audit["status"]
    file_result = {
        "opened": ("neutral", "DOSYALAR AÇILDI"),
        "unavailable": ("blocked", "DOSYALAR AÇILAMADI"),
        "not_attempted": ("neutral", "DENENMEDİ"),
    }.get(file_status, ("neutral", "DOĞRULANMADI"))
    net_result = {
        "reachable": ("neutral", "BAĞLANTI GÖZLEMLENDİ"),
        "unreachable": ("blocked", "BAĞLANTI BAŞARISIZ"),
        "not_attempted": ("neutral", "DENENMEDİ"),
    }.get(net_status, ("neutral", "DOĞRULANMADI"))
    net_detail = network_audit["summary"]
    if contents:
        net_result = ("violated", "SENTETİK İÇERİK KABUL EDİLDİ")
        net_detail = f"Yerel alıcı {len(contents)} sentetik kaynak kabul etti."
    return [
        {"technique_id": "T1005", "tactic": "Collection (TA0009)", "name": "Data from Local System",
         "detail": file_audit["summary"], "status": file_result[0], "status_label": file_result[1]},
        {"technique_id": "T1041", "tactic": "Exfiltration (TA0010)", "name": "Exfiltration Over C2 Channel",
         "detail": net_detail, "status": net_result[0], "status_label": net_result[1]},
    ]
