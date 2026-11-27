"""Read the lab mount and network namespace from Linux procfs."""
from pathlib import Path

TARGET_MOUNT = "/lab/targets"


def read_target_mount(path=Path("/proc/self/mountinfo")):
    try:
        lines = path.read_text(encoding="utf-8", errors="surrogateescape").splitlines()
    except OSError:
        return None
    if not lines:
        return None

    matches = []
    for line in lines:
        head, separator, _ = line.partition(" - ")
        fields = head.split()
        if not separator or len(fields) < 6:
            return None
        mount_id, mount_point, options = fields[0], fields[4], fields[5].split(",")
        if mount_point == TARGET_MOUNT:
            matches.append((mount_id, options))
    if len(matches) != 1:
        return {"present": bool(matches), "id": None, "read_only": None}

    mount_id, options = matches[0]
    mode = True if "ro" in options else False if "rw" in options else None
    return {"present": True, "id": mount_id, "read_only": mode}


def read_network_namespace():
    try:
        info = Path("/proc/self/ns/net").stat()
    except OSError:
        return None
    return {"id": f"net:[{info.st_ino}]", "device": info.st_dev}


def isolation_evidence(events, receiver_network):
    observation = next((event for event in events if event.get("event") == "ISOLATION_OBSERVED"), {})
    worker_network = observation.get("worker_network")
    relation = "unverified"
    if worker_network and receiver_network:
        relation = "shared" if worker_network == receiver_network else "separate"
    return {
        "target_mount": observation.get("target_mount"),
        "worker_network": worker_network,
        "receiver_network": receiver_network,
        "network_relation": relation,
    }
