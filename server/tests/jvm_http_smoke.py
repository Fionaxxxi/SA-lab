"""Run a previously compiled CoordinatorSmoke JVM class against a real loopback socket."""
import argparse
import json
import socket
import subprocess
import threading
import time
from pathlib import Path

import uvicorn

from server.gateway.fixtures import demo_handlers
from server.gateway.service import create_app


def run():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--java", default="java")
    cli.add_argument("--classpath", required=True)
    cli.add_argument("--evidence", required=True, type=Path)
    args = cli.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    log = args.evidence / "coordinator.jsonl"
    if log.exists():
        raise SystemExit(f"Use a fresh evidence directory: {log}")

    gateway = create_app(token="fixture-token", model_version="modelset-demo", config_version="rules-demo",
                         dimension=2, handlers=demo_handlers(), demo=True)
    requests = []

    async def measured(scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST":
            return await gateway(scope, receive, send)
        up = down = 0

        async def read():
            nonlocal up
            message = await receive()
            up += len(message.get("body", b""))
            return message

        async def write(message):
            nonlocal down
            down += len(message.get("body", b""))
            await send(message)

        await gateway(scope, read, write)
        requests.append((scope["path"].split("/")[4], up, down))

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(measured, log_level="error", access_log=False, lifespan="off", ws="none"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            limit = time.monotonic() + 10
            while not server.started:
                if time.monotonic() >= limit or not thread.is_alive():
                    raise RuntimeError("Uvicorn did not start")
                time.sleep(0.02)
            subprocess.run(
                [args.java, "-cp", args.classpath, "com.example.interviewfeedback.application.CoordinatorSmokeKt",
                 f"http://127.0.0.1:{port}", str(args.evidence)], check=True, timeout=30,
            )
        finally:
            server.should_exit = True
            thread.join(5)

    events = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
    remote = [(e["module_id"], e["bytes_up"], e["bytes_down"]) for e in events if e["executor"] == "REMOTE"]
    assert len(remote) == 6, remote
    assert remote == requests, (remote, requests)
    assert all(up > 0 and down > 0 for _, up, down in requests)
    assert [(event["status"], event["event"]) for event in events if event["sample_id"] == "interrupted"] == [
        ("CREATED", "TASK_SUBMITTED"), ("INTERRUPTED", "TASK_TERMINAL"),
    ]
    (args.evidence / "gateway-body-bytes.json").write_text(json.dumps(requests, indent=2) + "\n", "utf-8")
    print("6 real HTTP calls: JVM request/response body bytes match ASGI capture OK")


if __name__ == "__main__":
    run()
