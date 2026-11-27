"""Turn recorded lab events into narrowly scoped, evidence-based outcomes."""
import errno
import re

from fixtures import FILES

OPEN = re.compile(r'^openat\(AT_FDCWD, "/lab/targets/([^"/]+)", O_RDONLY(?:\|[A-Z_]+)*\)')
CONNECT = re.compile(
    r'^connect\((\d+), \{sa_family=AF_INET, sin_port=htons\((\d+)\), '
    r'sin_addr=inet_addr\("127\.0\.0\.1"\)\}, \d+\)'
)
PID = re.compile(r'^(?:\[pid\s+(\d+)\]|(\d+))\s+')
RESUMED = re.compile(r'^<\.\.\. (openat|connect|getsockopt|close|poll|ppoll) resumed>\s*')
CONNECT_FD = re.compile(r'^connect\((\d+),')
CLOSE = re.compile(r'^close\((\d+)\)')
POLL = re.compile(r'^p?poll\(\[\{fd=(\d+), events=([A-Z_|]+)\}\], 1,')
POLL_READY = re.compile(r'\)\s+=\s+1\b')
SO_ERROR = re.compile(
    r'^getsockopt\((\d+), SOL_SOCKET, SO_ERROR, \[([A-Z][A-Z0-9_]*|\d+)\], \[4(?:\s*=>\s*4)?\]\)'
)
RETURN = re.compile(r'^\s+=\s+(-?\d+)(?:\s+([A-Z][A-Z0-9_]+)\b|\s|$)')
FILE_ERRORS = {"ENOENT", "EACCES", "EPERM"}
NETWORK_ERRORS = {"ENETUNREACH", "EHOSTUNREACH", "ECONNREFUSED", "EACCES", "EPERM"}


def completed_calls(stream):
    unfinished = {}
    for raw in stream:
        raw = raw.strip()
        prefix = PID.match(raw)
        pid = (prefix.group(1) or prefix.group(2)) if prefix else None
        call = raw[prefix.end():] if prefix else raw
        if call.endswith("<unfinished ...>"):
            unfinished[pid] = (call.removesuffix("<unfinished ...>").rstrip(), raw)
            continue
        resumed = RESUMED.match(call)
        if resumed:
            earlier, earlier_raw = unfinished.pop(pid, ("", ""))
            if not earlier.startswith(resumed.group(1) + "("):
                continue
            tail = call[resumed.end():]
            call = earlier + (" " if tail.startswith("=") else "") + tail
            raw = earlier_raw + "\n" + raw
        yield pid, call, raw


def read_syscalls(path, port):
    """Extract lab file opens and connection results for the fixed receiver."""
    if path.is_symlink() or not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8", errors="replace") as stream:
            return read_lab_calls(completed_calls(stream), port)
    except OSError:
        return []


def read_lab_calls(lines, port):
    calls = []
    connecting = {}
    destination = f"127.0.0.1:{port}"
    for pid, call, raw in lines:
        if match := CLOSE.match(call):
            connecting.pop((pid, match[1]), None)
            continue
        if match := POLL.match(call):
            attempt = connecting.get((pid, match[1]))
            if attempt and "POLLOUT" in match[2].split("|") and POLL_READY.search(call):
                attempt["ready"] = True
            continue
        if match := SO_ERROR.match(call):
            key = (pid, match[1])
            attempt = connecting.get(key)
            result = RETURN.match(call[match.end():])
            if attempt is None or result is None or result[1] != "0":
                continue
            connecting.pop(key)
            value = match[2]
            # A zero error settles the connection only after observed writability.
            if value == "0" and not attempt["ready"]:
                continue
            error = None
            if value != "0":
                error = errno.errorcode.get(int(value), value) if value.isdigit() else value
            calls.append({"raw": raw, "kind": "so_error", "source": destination,
                          "status": "error" if error else "allowed", "errno": error,
                          "attempt": attempt["id"]})
            continue

        key = None
        if fd := CONNECT_FD.match(call):
            key = (pid, fd[1])
            # A new connection on this descriptor cannot resolve the old one.
            connecting.pop(key, None)
            match = CONNECT.match(call)
            if not match or match[2] != str(port):
                continue
            kind, source = "connect", destination
        else:
            match = OPEN.match(call)
            if not match or match[1] not in FILES:
                continue
            kind, source = "openat", match[1]

        if result := RETURN.match(call[match.end():]):
            code, error = int(result[1]), result[2]
            status = "allowed" if code >= 0 else ("pending" if error == "EINPROGRESS" else "error")
            entry = {"raw": raw, "kind": kind, "source": source, "status": status, "errno": error}
            if key is not None:
                entry["attempt"] = len(calls)
                if status == "pending":
                    connecting[key] = {"id": entry["attempt"], "ready": False}
            calls.append(entry)
    return calls


def assess(record, completed):
    calls = record.get("syscalls") or []
    file_calls = [call for call in calls if call["kind"] == "openat"]
    net_calls = [call for call in calls if call["kind"] == "connect"]
    resolved = {call["attempt"]: call for call in calls if call["kind"] == "so_error"}
    net_results = [resolved.get(call.get("attempt"), call) if call["status"] == "pending" else call
                   for call in net_calls]
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
    elif any(call["status"] == "allowed" for call in net_results):
        network_status = "reachable"
        network_summary = "Yerel alıcıya başarılı bir soket bağlantısı gözlemlendi. HTTP kabul kaydı yok."
    elif controls.get("before") and controls.get("after") and net_results and all(
        call["status"] == "error" and call["errno"] in NETWORK_ERRORS for call in net_results
    ):
        network_status = "unreachable"
        network_summary = "Alıcı deneyin öncesinde ve sonrasında yanıt verdi. Çekirdek kayıtları işçinin yerel alıcıya bağlantı girişimlerinin başarısız olduğunu gösterdi."
    elif net_calls:
        network_summary = "Yerel alıcıya bağlantı girişimi gözlemlendi. Nihai sonuç doğrulanmadı."

    if normal and not file_calls and not net_calls and not receiver:
        file_status = network_status = "not_attempted"
        file_summary = network_summary = "Normal eklenti ek deney adımını çalıştırmadığını bildirdi."

    file_audit = {"status": file_status, "summary": file_summary,
                  "opened_sources": sorted(opened), "unavailable_sources": sorted(unavailable)}
    network_audit = {"status": network_status, "summary": network_summary,
                     "requests_accepted": len(receiver), "attempts": len(net_calls),
                     "resolved_with_so_error": len(resolved)}
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
